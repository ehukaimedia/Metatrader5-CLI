"""Python-side post-fill trade manager — replaces AdaptiveTrailEA for our magics.

Runs as a separate process. Each loop:
  1. Heartbeat upsert to state.db.
  2. List MT5 positions, filter to poc-magic set.
  3. For each: bootstrap if needed, then BE/Chandelier/modify state machine.

Confirm-before-promote idempotency: last_sl_set is only set after MT5 confirms
the modify. Pending modifies retry on next loop with the same idempotency key.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import journal
import state_db


HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "state.db"


def init_state(db_path: Path = DB_PATH) -> None:
    state_db.init(db_path)


def _cli(cfg: dict) -> list[str]:
    base = [cfg["mt5_cli"]["command"]]
    if cfg["mt5_cli"].get("live"):
        base.append("--live")
    return base


def _run(cfg: dict, args: list[str]) -> dict | None:
    cmd = _cli(cfg) + ["--json"] + args
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=cfg["mt5_cli"]["subprocess_timeout_seconds"],
        )
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def list_positions(cfg: dict) -> list[dict]:
    out = _run(cfg, ["position", "list"])
    if not out or not out.get("ok"):
        return []
    return out.get("data") or []


def loop_once(cfg: dict, db_path: Path = DB_PATH) -> None:
    """One iteration: heartbeat + scan-and-manage. Subsequent tasks fill in
    bootstrap / BE / Chandelier / modify."""
    state_db.heartbeat_upsert(db_path, "manager", pid=os.getpid())
    list_positions(cfg)


def run() -> None:
    cfg_path = HERE / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    init_state()
    interval = float(cfg.get("manager", {}).get("loop_seconds", 1))
    print(f"[trade_manager] starting · loop={interval}s · live={cfg['mt5_cli']['live']}")
    while True:
        try:
            loop_once(cfg)
        except Exception as e:
            journal.log_error("trade_manager", "loop", str(e))
        time.sleep(interval)


if __name__ == "__main__":
    run()
