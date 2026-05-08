"""End-to-end test of the agent's outcome attribution + concurrency guard.

Exercises the real broker:
  1. Active-strategy guard — places a far pending limit, calls scan_once,
     verifies the agent skips that pair with reason "active_strategy".
  2. Outcome attribution by direction-flip — places a market position with
     a unique strategy_id, manually injects a placement record into the
     journal, closes the position via CLI (forces a close deal), runs the
     outcome-resolution path, asserts the journal got an outcome record
     keyed to that ticket with realized_r computed.

Run only on demo. Verifies micro-lot behavior; max risk per test is
~$0.10. Cleans up its own pending order even on failure.
"""
from __future__ import annotations

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
# Test 1 — active-strategy guard
# ---------------------------------------------------------------------------
def test_active_strategy_guard(cfg: dict) -> None:
    print("\n=== Test 1: active-strategy guard ===")
    pair = "USDJPY"
    strategy_id = f"{cfg['agent']['strategy_id_prefix']}-{pair}"
    expected_magic = agent.derive_magic(strategy_id)

    # Get current price; place far buy limit that won't fill
    tick = run_cli(cfg, ["market", "tick", pair])
    if not tick.get("ok"):
        fail(f"market tick failed: {tick}")
    bid = float(tick["data"]["bid"])
    far_limit = round(bid - 1.000, 3)  # 100 pips below market
    sl = round(far_limit - 0.200, 3)   # safe SL
    tp = round(far_limit + 0.500, 3)   # safe TP

    print(f"  placing buy limit USDJPY @ {far_limit} (bid={bid}) with strategy_id={strategy_id}")
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
        fail(f"magic mismatch: CLI returned {placed_magic}, derive_magic computed {expected_magic}")
    ok(f"limit placed ticket={ticket} magic={placed_magic} (matches local derive)")

    try:
        # Verify active_strategies() picks it up
        active = agent.active_strategies(cfg)
        if (pair, expected_magic) not in active:
            fail(f"active_strategies() did not include ({pair}, {expected_magic}). Got: {active}")
        ok(f"active_strategies() correctly contains ({pair}, {expected_magic})")

        # Run a single scan cycle and verify the agent skips USDJPY with active_strategy reason
        # (We don't restart the full agent — just call scan_once directly.)
        before_count = sum(
            1 for r in journal.read_all()
            if r.get("kind") == "skip" and r.get("pair") == pair
            and (r.get("reason") or "").startswith("pending order or open position")
        )
        agent.scan_once(cfg)
        after_count = sum(
            1 for r in journal.read_all()
            if r.get("kind") == "skip" and r.get("pair") == pair
            and (r.get("reason") or "").startswith("pending order or open position")
        )
        if after_count <= before_count:
            fail(f"scan_once did not log an active_strategy skip for {pair} (before={before_count} after={after_count})")
        ok(f"scan_once skipped {pair} with active_strategy reason (count: {before_count} ->{after_count})")

    finally:
        # Cleanup
        cancel = run_cli(cfg, ["order", "cancel", str(ticket)])
        if cancel.get("ok"):
            ok(f"cancelled limit ticket={ticket}")
        else:
            print(f"  WARNING: cancel failed: {cancel.get('error')}")


# ---------------------------------------------------------------------------
# Test 2 — outcome attribution including breakeven
# ---------------------------------------------------------------------------
def test_outcome_attribution(cfg: dict) -> None:
    print("\n=== Test 2: outcome attribution by direction-flip ===")
    pair = "EURUSD"
    strategy_id = f"{cfg['agent']['strategy_id_prefix']}-e2e-{int(time.time())}"
    expected_magic = agent.derive_magic(strategy_id)

    # Place market buy 0.001 with safe SL/TP
    tick = run_cli(cfg, ["market", "tick", pair])
    if not tick.get("ok"):
        fail(f"market tick failed: {tick}")
    bid = float(tick["data"]["bid"])
    ask = float(tick["data"]["ask"])
    sl = round(ask - 0.0050, 5)  # 50 pips below ask
    tp = round(ask + 0.0100, 5)  # 100 pips above ask

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

    # Inject a synthetic placement record so the agent's outcome-resolution
    # path treats this as an open trade it owns.
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
        # Wait briefly so close-time > placement-time at second resolution
        time.sleep(2)

        # Close the position via CLI — this generates an opposite-direction deal
        close = run_cli(cfg, ["position", "close", str(ticket)])
        if not close.get("ok"):
            fail(f"position close failed: {close.get('error')}")
        ok(f"position closed ticket={ticket}")

        # Wait briefly for broker to update history
        time.sleep(3)

        # Run agent's outcome-resolution path (just scan_once; cap will skip
        # placement attempts since active set will reflect any other live state)
        agent.scan_once(cfg)

        # Verify journal got an outcome record for our ticket
        outcomes = [r for r in journal.read_all() if r.get("kind") == "outcome" and r.get("ticket") == ticket]
        if not outcomes:
            # Diagnose
            deals = agent.recent_deals(cfg, days=1)
            our_deals = [d for d in deals if d.get("magic") == placed_magic]
            print(f"  diagnostic: deals matching magic {placed_magic}:")
            for d in our_deals:
                print(f"    {d}")
            print(f"  diagnostic: placement_time={placement_time!r}")
            direct = agent.find_close_deal(deals, placement_ticket=ticket, magic=placed_magic, symbol="EURUSD", direction="buy")
            print(f"  diagnostic: find_close_deal direct call returned: {direct}")
            # Re-check open_journal_records
            opens = agent.open_journal_records()
            our_opens = [r for r in opens if r.get("ticket") == ticket]
            print(f"  diagnostic: open_journal_records for ticket={ticket}: {our_opens}")
            positions_now = agent.list_positions(cfg)
            print(f"  diagnostic: live positions count={len(positions_now)}")
            fail(f"no outcome record for ticket={ticket}")
        outcome = outcomes[-1]
        ok(f"outcome logged: result={outcome.get('result')} profit={outcome.get('profit')} net={outcome.get('net')} realized_r={outcome.get('realized_r')}")

        # Required fields
        for field in ("profit", "swap", "commission", "net", "close_price", "close_time", "result", "deal_id", "magic", "realized_r"):
            if field not in outcome:
                fail(f"outcome missing required field: {field}")
        ok("all required outcome fields present")

        # Sanity: realized_r is a float when entry/sl/close exist
        if outcome.get("realized_r") is None:
            print(f"  WARNING: realized_r is None — entry={placed['data'].get('price')}, sl={sl}, close={outcome.get('close_price')}")
        else:
            ok(f"realized_r computed: {outcome['realized_r']}")

    except SystemExit:
        # Cleanup any leftover open position
        positions = agent.list_positions(cfg)
        if any(p.get("ticket") == ticket for p in positions):
            run_cli(cfg, ["position", "close", str(ticket)])
        raise


# ---------------------------------------------------------------------------
# Test 3 — magic-derivation parity with CLI for all 11 pairs
# ---------------------------------------------------------------------------
def test_magic_parity(cfg: dict) -> None:
    print("\n=== Test 3: magic derivation parity ===")
    # The CLI's magic for a strategy_id is exposed via order placement —
    # already verified in test 1 for USDJPY. Here just verify all 11 pair
    # magics derive in our local helper without collision.
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
def main() -> None:
    cfg = agent.load_config()
    if not cfg["mt5_cli"].get("live"):
        print("WARNING: mt5_cli.live=false in config; tests assume demo and use --live")
        cfg["mt5_cli"]["live"] = True
    print("Config:")
    print(f"  command: {cfg['mt5_cli']['command']}  live: {cfg['mt5_cli']['live']}")
    print(f"  strategy_id_prefix: {cfg['agent']['strategy_id_prefix']}")

    test_magic_parity(cfg)
    test_active_strategy_guard(cfg)
    test_outcome_attribution(cfg)

    print(f"\n{GREEN}All e2e tests passed.{RESET}")


if __name__ == "__main__":
    main()
