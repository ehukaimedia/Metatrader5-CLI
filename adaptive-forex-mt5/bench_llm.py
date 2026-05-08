"""Benchmark candidate LLMs on a representative trading-reasoning prompt.

Sends the same realistic sniper-poc setup JSON to each model, asks for a
structured judgement, and measures latency + output validity.

Usage:
    python bench_llm.py                 # default models + 3 iterations
    python bench_llm.py --iters 1       # quick smoke test
    python bench_llm.py --models qwen3.6:27b  # single model
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"
ROOT = Path(__file__).parent
RESULTS_DIR = ROOT / "logs"
RESULTS_DIR.mkdir(exist_ok=True)


# Representative sniper-poc output shape, USDJPY bullish setup
SAMPLE_SETUP = {
    "symbol": "USDJPY",
    "status": "ready",
    "direction": "buy",
    "quality_score": 0.85,
    "structure": {
        "permission_timeframes": ["D1", "H4"],
        "setup_timeframe": "M15",
        "entry_timeframe": "M5",
        "bias": "bullish",
        "stage": "BULLISH BOS",
        "strong_level": {"price": 156.74, "kind": "HL", "side": "low"},
        "weak_target": {"price": 157.42, "kind": "LH", "side": "high"},
        "last_confirmed_event": {"type": "BOS", "direction": "bullish", "level": 156.92},
    },
    "poi": {
        "type": "fvg", "timeframe": "M1", "direction": "bullish",
        "lower": 156.85, "upper": 156.88, "mid": 156.865,
        "state": "open", "caused_structure_break": True,
        "mitigated": False, "poi_quality": "primary",
    },
    "liquidity": {
        "sweep_in_zone_creation": True,
        "opposing_liquidity_in_front": True,
        "liquidity_behind_zone": False,
        "poi_trap_risk": False,
        "nearest_target_liquidity": {"side": "buy_side", "level": 157.40},
    },
    "entry": {
        "model": "fvg_limit", "timeframe": "M5",
        "trigger": "M5 structure aligned",
        "entry_price": 156.87, "sl": 156.81, "tp": 157.05, "rr": 3.0,
        "confirmed": True,
    },
    "gates_passed": [
        "spread", "rollover", "valid_poi", "liquidity_sweep",
        "liquidity_trap", "fvg_age", "stop_distance", "rr",
        "entry_structure",
    ],
}


SYSTEM_PROMPT = """You are a trading setup quality reviewer. Given a sniper-poc setup contract, return a strict JSON object with these keys exactly:
- probability_score (number 0.0-1.0): your independent estimate of trade success probability
- top_concerns (array of short strings, max 3): the most material risks you see
- recommended_action (one of: "place", "skip", "wait"): what you would do
- reasoning (string, max 60 words): brief justification

Return ONLY the JSON object. No prose before or after."""


def build_prompt() -> str:
    return f"Setup contract:\n```json\n{json.dumps(SAMPLE_SETUP, indent=2)}\n```\n\nReview this setup and return your JSON judgement."


def http_post_json(url: str, payload: dict, timeout: float = 300.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post_stream(url: str, payload: dict, timeout: float = 300.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            if line.strip():
                yield json.loads(line.decode("utf-8"))


def ollama_alive() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def parse_json_in_text(s: str) -> dict | None:
    """Extract first JSON object from arbitrary text. Tolerant to ``` fences."""
    s = s.strip()
    if s.startswith("```"):
        # strip ```json ... ``` fences
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    # Find first { and last }
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = s[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def run_one(model: str, prompt: str, system: str, *, think: bool = False, num_predict: int = 600) -> dict:
    """Stream one completion. Return timing + raw + parsed.

    think=False disables Qwen 3.6 thinking traces -- the realistic agent hot-path mode.
    think=True is for "deep review" of past trades, much slower.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "think": think,
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }
    start = time.monotonic()
    first_response_at: float | None = None
    first_thinking_at: float | None = None
    response_chunks: list[str] = []
    thinking_chunks: list[str] = []
    eval_count = 0
    eval_duration_ns = 0
    error: str | None = None
    try:
        for evt in http_post_stream(f"{OLLAMA_URL}/api/generate", payload, timeout=600):
            if evt.get("response"):
                if first_response_at is None:
                    first_response_at = time.monotonic()
                response_chunks.append(evt["response"])
            if evt.get("thinking"):
                if first_thinking_at is None:
                    first_thinking_at = time.monotonic()
                thinking_chunks.append(evt["thinking"])
            if evt.get("done"):
                eval_count = evt.get("eval_count", 0)
                eval_duration_ns = evt.get("eval_duration", 0)
                break
    except Exception as e:
        error = str(e)
    end = time.monotonic()
    raw = "".join(response_chunks)
    thinking = "".join(thinking_chunks)
    parsed = parse_json_in_text(raw) if raw else None
    valid = bool(parsed and isinstance(parsed.get("probability_score"), (int, float))
                 and parsed.get("recommended_action") in {"place", "skip", "wait"})
    return {
        "model": model,
        "think": think,
        "ttft_response_s": (first_response_at - start) if first_response_at else None,
        "ttft_thinking_s": (first_thinking_at - start) if first_thinking_at else None,
        "total_s": end - start,
        "eval_count": eval_count,
        "tokens_per_sec": (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None,
        "valid_json": valid,
        "raw_chars": len(raw),
        "thinking_chars": len(thinking),
        "raw": raw,
        "thinking": thinking,
        "parsed": parsed,
        "error": error,
    }


def summarise(rows: list[dict]) -> list[dict]:
    """Aggregate per-(model, think-mode) stats."""
    by_key: dict[tuple, list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["model"], r["think"]), []).append(r)
    out = []
    for (model, think), runs in by_key.items():
        ttft_resp = [r["ttft_response_s"] for r in runs if r["ttft_response_s"] is not None]
        total = [r["total_s"] for r in runs if not r["error"]]
        tps = [r["tokens_per_sec"] for r in runs if r["tokens_per_sec"]]
        valid = sum(1 for r in runs if r["valid_json"])
        errors = [r["error"] for r in runs if r["error"]]
        out.append({
            "model": model,
            "think": think,
            "n": len(runs),
            "ttft_response_avg_s": round(sum(ttft_resp) / len(ttft_resp), 2) if ttft_resp else None,
            "total_avg_s": round(sum(total) / len(total), 2) if total else None,
            "tokens_per_sec_avg": round(sum(tps) / len(tps), 1) if tps else None,
            "valid_json": f"{valid}/{len(runs)}",
            "errors": errors[:1],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen3.6:27b", "qwen3.6:35b", "ehukai-gemma4:e2b"])
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--think", choices=["off", "on", "both"], default="off",
                    help="off=hot-path mode (default), on=deep review, both=run each model in both modes")
    ap.add_argument("--out", default=str(RESULTS_DIR / f"bench_llm_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"))
    args = ap.parse_args()

    if not ollama_alive():
        sys.exit("Ollama not reachable at http://localhost:11434 -- start the Ollama app first.")

    prompt = build_prompt()
    think_modes = {"off": [False], "on": [True], "both": [False, True]}[args.think]
    rows: list[dict] = []
    for model in args.models:
        for think in think_modes:
            label = f"{model} (think={'on' if think else 'off'})"
            print(f"\n=== {label} ===", flush=True)
            for i in range(args.iters):
                print(f"  iter {i + 1}/{args.iters} ...", end=" ", flush=True)
                r = run_one(model, prompt, SYSTEM_PROMPT, think=think)
                rows.append(r)
                if r["error"]:
                    print(f"ERROR {r['error']}", flush=True)
                else:
                    ttft = f"ttft_r={r['ttft_response_s']:.2f}s" if r["ttft_response_s"] else "ttft_r=?"
                    tps = f"{r['tokens_per_sec']:.1f}" if r["tokens_per_sec"] else "?"
                    thk = f" thinking={r['thinking_chars']}c" if r['thinking_chars'] else ""
                    print(f"{ttft} total={r['total_s']:.1f}s eval={r['eval_count']}t tps={tps} valid={r['valid_json']}{thk}", flush=True)

    summary = summarise(rows)
    Path(args.out).write_text(
        json.dumps({"prompt": prompt, "system": SYSTEM_PROMPT, "rows": rows, "summary": summary}, indent=2),
        encoding="utf-8",
    )
    print("\n=== SUMMARY ===")
    print(f"{'model':<28} {'think':>5} {'ttft_r':>7} {'total':>7} {'tok/s':>6} {'json':>5}")
    for s in summary:
        think_str = "on" if s["think"] else "off"
        print(f"{s['model']:<28} {think_str:>5} {str(s['ttft_response_avg_s']):>7} {str(s['total_avg_s']):>7} {str(s['tokens_per_sec_avg']):>6} {s['valid_json']:>5}")
    print(f"\nFull results -> {args.out}")


if __name__ == "__main__":
    main()
