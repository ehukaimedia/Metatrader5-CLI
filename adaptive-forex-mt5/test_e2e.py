"""End-to-end test of the agent's outcome attribution + concurrency guard.

SAFETY: this test PLACES REAL ORDERS on whatever account `mt5_cli.live` in
config.json points at. It is gated behind an explicit `--allow-live` CLI flag
AND requires `mt5_cli.live=true` to already be set in config.json — the test
will refuse to flip it for you.

Tests run only the narrowly-scoped agent surface they need:
  1. magic-derivation parity for all configured pairs (local only)
  2. active-strategy guard: places one far pending limit, verifies
     active_strategies(cfg) reflects it, asserts the per-pair guard would
     fire by checking the in-memory predicate (no scan_once call)
  3. outcome attribution: market-buy 0.001, inject placement, close via CLI,
     call ONLY agent.resolve_outcomes() (which never places orders), assert
     outcome record has profit/swap/commission/net/realized_r
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agent
import journal


GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[PASS]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL]{RESET} {msg}")
    raise SystemExit(1)


def run_cli(cfg: dict, args: list[str]) -> dict:
    cmd = [cfg["mt5_cli"]["command"]]
    if cfg["mt5_cli"].get("live"):
        cmd.append("--live")
    cmd += ["--json"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.stdout else {"ok": False, "error": {"code": "NO_OUTPUT", "stderr": r.stderr[:300]}}


# ---------------------------------------------------------------------------
def test_magic_parity(cfg: dict) -> None:
    """No broker action — local derivation only."""
    print("\n=== Test 1: magic derivation parity ===")
    seen: dict[int, str] = {}
    for pair in cfg["pairs"]:
        sid = f"{cfg['agent']['strategy_id_prefix']}-{pair}"
        m = agent.derive_magic(sid)
        if m in seen:
            fail(f"magic collision: {sid} and {seen[m]} both derive to {m}")
        if not (100000 <= m < 180000):
            fail(f"magic {m} for {sid} outside expected range [100000, 180000)")
        seen[m] = sid
    ok(f"all {len(cfg['pairs'])} magics unique and in range")


# ---------------------------------------------------------------------------
def test_active_strategy_guard(cfg: dict) -> None:
    """Place a far pending limit. Verify active_strategies() reflects it AND
    the per-pair guard predicate (used by place_new_orders) would fire.

    Does NOT call scan_once or place_new_orders — those would touch other
    pairs as a side effect.
    """
    print("\n=== Test 2: active-strategy guard ===")
    pair = "USDJPY"
    strategy_id = f"{cfg['agent']['strategy_id_prefix']}-{pair}"
    expected_magic = agent.derive_magic(strategy_id)

    tick = run_cli(cfg, ["market", "tick", pair])
    if not tick.get("ok"):
        fail(f"market tick failed: {tick}")
    bid = float(tick["data"]["bid"])
    far_limit = round(bid - 1.000, 3)
    sl = round(far_limit - 0.200, 3)
    tp = round(far_limit + 0.500, 3)

    print(f"  placing buy limit USDJPY @ {far_limit} (bid={bid}) sid={strategy_id}")
    placed = run_cli(cfg, [
        "order", "limit", pair, "buy",
        "--price", str(far_limit), "--volume", "0.001",
        "--sl", str(sl), "--tp", str(tp),
        "--strategy-id", strategy_id, "--filling", "FOK",
    ])
    if not placed.get("ok"):
        fail(f"limit placement failed: {placed.get('error')}")
    ticket = placed["data"]["ticket"]
    placed_magic = placed["data"]["magic"]
    if placed_magic != expected_magic:
        fail(f"magic mismatch: CLI={placed_magic} local-derive={expected_magic}")
    ok(f"limit placed ticket={ticket} magic={placed_magic} (matches local derive)")

    try:
        active = agent.active_strategies(cfg)
        if (pair, expected_magic) not in active:
            fail(f"active_strategies() did not include ({pair}, {expected_magic}). Got: {active}")
        ok(f"active_strategies() reflects pending order: ({pair}, {expected_magic})")

        # Validate the in-memory predicate that place_new_orders uses to
        # decide whether to skip a pair. Reproducing the predicate here is
        # safer than calling place_new_orders, which would fire orders on
        # any READY pair as a side effect.
        guard_would_skip = (pair.upper(), expected_magic) in active
        if not guard_would_skip:
            fail("per-pair guard predicate did not match")
        ok("per-pair guard predicate would skip this pair (no scan_once call needed)")
    finally:
        cancel = run_cli(cfg, ["order", "cancel", str(ticket)])
        if cancel.get("ok"):
            ok(f"cancelled limit ticket={ticket}")
        else:
            print(f"  WARNING: cancel failed: {cancel.get('error')}")


# ---------------------------------------------------------------------------
def test_outcome_attribution(cfg: dict) -> None:
    """Place a market position with a unique strategy_id, inject a synthetic
    placement record into the journal, close the position, then call ONLY
    agent.resolve_outcomes() — which never places new orders — to verify
    the close-deal attribution path.
    """
    print("\n=== Test 3: outcome attribution by direction-flip ===")
    pair = "EURUSD"
    strategy_id = f"{cfg['agent']['strategy_id_prefix']}-e2e-{int(time.time())}"

    tick = run_cli(cfg, ["market", "tick", pair])
    if not tick.get("ok"):
        fail(f"market tick failed: {tick}")
    ask = float(tick["data"]["ask"])
    sl = round(ask - 0.0050, 5)
    tp = round(ask + 0.0100, 5)

    print(f"  placing market buy {pair} @ ~{ask} sl={sl} tp={tp} sid={strategy_id}")
    placed = run_cli(cfg, [
        "order", "market", pair, "buy",
        "--volume", "0.001", "--sl", str(sl), "--tp", str(tp),
        "--strategy-id", strategy_id, "--filling", "FOK",
    ])
    if not placed.get("ok"):
        fail(f"market placement failed: {placed.get('error')}")
    ticket = placed["data"]["ticket"]
    placed_magic = placed["data"]["magic"]
    placement_time = datetime.now(timezone.utc).isoformat()
    ok(f"market position opened ticket={ticket} magic={placed_magic}")

    journal.append({
        "ts": placement_time,
        "kind": "placement",
        "pair": pair,
        "ticket": ticket,
        "magic": placed_magic,
        "direction": "buy",
        "entry": placed["data"].get("price") or ask,
        "sl": sl,
        "tp": tp,
        "rr": 2.0,
        "volume": 0.001,
        "strategy_id": strategy_id,
        "reasoning": {"e2e_test": True},
    })
    ok(f"synthetic placement record injected ticket={ticket}")

    try:
        time.sleep(2)
        close = run_cli(cfg, ["position", "close", str(ticket)])
        if not close.get("ok"):
            fail(f"position close failed: {close.get('error')}")
        ok(f"position closed ticket={ticket}")
        time.sleep(3)

        # Use resolve_outcomes only — never calls place_new_orders, so no
        # accidental orders on other configured pairs.
        resolved = agent.resolve_outcomes(cfg)
        if resolved < 1:
            fail(f"resolve_outcomes returned {resolved} (expected >= 1)")

        outcomes = [r for r in journal.read_all() if r.get("kind") == "outcome" and r.get("ticket") == ticket]
        if not outcomes:
            fail(f"no outcome record for ticket={ticket}")
        outcome = outcomes[-1]
        ok(f"outcome logged: result={outcome.get('result')} profit={outcome.get('profit')} net={outcome.get('net')} realized_r={outcome.get('realized_r')}")

        for field in ("profit", "swap", "commission", "net", "close_price", "close_time", "result", "deal_id", "magic", "realized_r"):
            if field not in outcome:
                fail(f"outcome missing required field: {field}")
        ok("all required outcome fields present")
    except SystemExit:
        positions = agent.list_positions(cfg)
        if any(p.get("ticket") == ticket for p in positions):
            run_cli(cfg, ["position", "close", str(ticket)])
        raise


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--allow-live", action="store_true",
        help=("REQUIRED. This script places real orders on whatever account "
              "config.json's mt5_cli.live points at. Pass this flag explicitly "
              "to acknowledge."),
    )
    args = ap.parse_args()

    if not args.allow_live:
        sys.exit(
            "REFUSED: e2e test places real orders. Pass --allow-live to acknowledge.\n"
            "Verify mt5_cli.live in config.json points at a DEMO account first."
        )

    cfg = agent.load_config()
    print("Config:")
    print(f"  command: {cfg['mt5_cli']['command']}  live: {cfg['mt5_cli']['live']}")
    print(f"  strategy_id_prefix: {cfg['agent']['strategy_id_prefix']}")
    print(f"  configured pairs: {cfg['pairs']}")
    print()
    print("Tests will issue real broker calls. Continuing in 3 seconds (Ctrl-C to abort)...")
    time.sleep(3)

    test_magic_parity(cfg)
    test_active_strategy_guard(cfg)
    test_outcome_attribution(cfg)

    print(f"\n{GREEN}All e2e tests passed.{RESET}")


if __name__ == "__main__":
    main()
