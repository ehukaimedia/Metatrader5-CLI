"""
test_risk.py — TDD for mt5_cli/risk/risk.py

One test per gate in check_order (legacy order preserved).
Gate triggers follow the legacy implementation, NOT the task-table where they differ.

Deliberate divergences from legacy (per spec):
- compute_volume_from_risk_pct returns ok({"volume": ...}) envelope (not raw float).
- check_order returns ok(None) on success (not {"ok": True}).
- check_order errors use fail(code, msg) — no mt5_retcode field.
- Rate limiter uses time.monotonic() (unchanged from legacy).
- Gate 2 triggers on is_live_intent=False + REAL account (not True — task table wrong).
- Gate 11 triggers on daily_loss <= -max_daily_loss (not abs() — task table wrong).
"""
import sys
import time
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Cache-safe fixture — purge bridge + risk + account + history submodules
# ---------------------------------------------------------------------------

_MODULES_TO_PURGE = (
    "mt5_cli.bridge",
    "mt5_cli.bridge.mt5_backend",
    "mt5_cli.risk",
    "mt5_cli.risk.risk",
    "mt5_cli.account",
    "mt5_cli.account.account",
    "mt5_cli.history",
    "mt5_cli.history.history",
)


def _purge():
    for name in list(sys.modules):
        for prefix in _MODULES_TO_PURGE:
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)
                break


@pytest.fixture
def mocked_mt5(monkeypatch):
    _purge()

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True

    # Account trade mode constants
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    fake.ACCOUNT_TRADE_MODE_CONTEST = 1
    fake.ACCOUNT_TRADE_MODE_REAL = 2

    # Bridge-required constants
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_PENDING = 5
    fake.TRADE_ACTION_SLTP = 6
    fake.TRADE_ACTION_MODIFY = 7
    fake.TRADE_ACTION_REMOVE = 8
    fake.TIMEFRAME_M1 = 1
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_M30 = 30
    fake.TIMEFRAME_H1 = 16385
    fake.TIMEFRAME_H4 = 16388
    fake.TIMEFRAME_D1 = 16408
    fake.TIMEFRAME_W1 = 32769
    fake.TIMEFRAME_MN1 = 49153
    fake.COPY_TICKS_ALL = 0
    fake.POSITION_TYPE_BUY = 0
    fake.POSITION_TYPE_SELL = 1
    fake.ORDER_TIME_GTC = 1

    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    _purge()


# ---------------------------------------------------------------------------
# Default config (passes all gates by design)
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> dict:
    """Return a base config that passes all gates unless overridden."""
    base = {
        "magic": 88888,
        "strategy_ids": {},
        "live": True,
        "symbol_allowlist": [],
        "max_lot_per_order": 10.0,
        "min_sl_distance_points": 5,
        "max_spread_points": 50,
        "allow_hedging": True,
        "max_positions": 50,
        "min_free_margin_pct": 20.0,
        "max_daily_loss": 5000.0,
        "max_orders_per_minute": 10,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _acct(
    trade_mode=0,      # DEMO
    equity=10000.0,
    margin_free=8000.0,
) -> MagicMock:
    return MagicMock(
        trade_mode=trade_mode,
        equity=equity,
        margin_free=margin_free,
    )


def _tick(bid=1.1000, ask=1.1001) -> MagicMock:
    return MagicMock(bid=bid, ask=ask)


def _sym_info(point=0.0001, trade_tick_value=1.0,
              volume_min=0.01, volume_max=100.0, volume_step=0.01) -> MagicMock:
    return MagicMock(
        point=point,
        trade_tick_value=trade_tick_value,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
    )


def _pos(symbol="EURUSD", pos_type=0, profit=0.0) -> MagicMock:
    """pos_type: 0=BUY, 1=SELL (raw MT5 integers)."""
    return MagicMock(symbol=symbol, type=pos_type, profit=profit)


def _deal(profit=0.0, commission=0.0, swap=0.0) -> MagicMock:
    return MagicMock(profit=profit, commission=commission, swap=swap)


# ---------------------------------------------------------------------------
# Helper — reset the rate limiter before each test that touches it
# ---------------------------------------------------------------------------

def _reset_rl(mocked_mt5):
    """Import risk after mock is in place then reset the rate limiter."""
    from mt5_cli.risk.risk import _reset_rate_limiter
    _reset_rate_limiter()


# ---------------------------------------------------------------------------
# resolve_magic tests
# ---------------------------------------------------------------------------

class TestResolveMagic:

    def test_resolve_magic_default_when_no_strategy_id(self, mocked_mt5):
        """Returns cfg['magic'] when strategy_id is None."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(magic=88888)
        assert resolve_magic(None, cfg) == 88888

    def test_resolve_magic_default_when_empty_string(self, mocked_mt5):
        """Returns cfg['magic'] when strategy_id is empty string."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(magic=77777)
        assert resolve_magic("", cfg) == 77777

    def test_resolve_magic_explicit_map_lookup(self, mocked_mt5):
        """Returns the configured magic when strategy_id is in the map."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(strategy_ids={"alpha": 50000})
        assert resolve_magic("alpha", cfg) == 50000

    def test_resolve_magic_collision_guard_raises(self, mocked_mt5):
        """Raises ValueError when configured magic >= 100000 (auto-derive range collision)."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(strategy_ids={"alpha": 162538})
        with pytest.raises(ValueError, match="100000"):
            resolve_magic("alpha", cfg)

    def test_resolve_magic_sha256_derivation_in_range(self, mocked_mt5):
        """Auto-derive produces a magic in [100000, 180000)."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(strategy_ids={})  # "alpha" not in map
        magic = resolve_magic("alpha", cfg)
        assert 100000 <= magic < 180000

    def test_resolve_magic_deterministic(self, mocked_mt5):
        """Same strategy_id always produces the same magic."""
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(strategy_ids={})
        assert resolve_magic("alpha", cfg) == resolve_magic("alpha", cfg)

    def test_resolve_magic_sha256_known_value(self, mocked_mt5):
        """Verify exact SHA-256 derivation formula for a known input."""
        import hashlib
        from mt5_cli.risk.risk import resolve_magic
        cfg = _cfg(strategy_ids={})
        expected = int(hashlib.sha256(b"alpha").hexdigest()[:8], 16) % 80000 + 100000
        assert resolve_magic("alpha", cfg) == expected


# ---------------------------------------------------------------------------
# check_order — gate tests
# ---------------------------------------------------------------------------

class TestCheckOrderGates:

    def _setup_happy_path(self, mocked_mt5, cfg=None, override_positions=None):
        """Wire fake MT5 returns so all gates pass; individual tests override specific returns."""
        mocked_mt5.account_info.return_value = _acct(trade_mode=0, equity=10000.0, margin_free=9000.0)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        positions = override_positions if override_positions is not None else []
        mocked_mt5.positions_get.return_value = positions
        mocked_mt5.history_deals_get.return_value = []

    def test_check_order_gate_strategy_id_too_long(self, mocked_mt5):
        """Gate 1: strategy_id > 31 chars → RISK_STRATEGY_ID_TOO_LONG."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id="a" * 32,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_STRATEGY_ID_TOO_LONG"

    def test_check_order_gate_live_blocked(self, mocked_mt5):
        """Gate 2: REAL account + is_live_intent=False → RISK_LIVE_GATE_BLOCKED.
        NOTE: trigger is is_live_intent=False, not True — legacy line 239.
        """
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        mocked_mt5.symbol_info_tick.return_value = _tick()
        mocked_mt5.symbol_info.return_value = _sym_info()
        mocked_mt5.positions_get.return_value = []
        mocked_mt5.history_deals_get.return_value = []
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(), is_live_intent=False,  # False + REAL → blocked
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"

    def test_check_order_gate_live_passes_when_triple_lock_armed(self, mocked_mt5, monkeypatch):
        """Gate 2 triple lock: REAL + is_live_intent=True + cfg['live']=True +
        MT5_LIVE=1 → gate passes. All three must be armed."""
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        monkeypatch.setenv("MT5_LIVE", "1")
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(live=True), is_live_intent=True,  # all three armed
        )
        if not result["ok"]:
            assert result["error"]["code"] != "RISK_LIVE_GATE_BLOCKED"

    def test_check_order_gate_live_blocked_when_cfg_live_false(self, mocked_mt5, monkeypatch):
        """Gate 2 triple lock: REAL + is_live_intent=True + MT5_LIVE=1 +
        cfg['live']=False → BLOCKS. cfg["live"] must also be armed."""
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        monkeypatch.setenv("MT5_LIVE", "1")
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(live=False), is_live_intent=True,  # cfg["live"] not armed
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        assert 'cfg["live"]' in result["error"]["message"]

    def test_check_order_gate_live_blocked_when_env_unset(self, mocked_mt5, monkeypatch):
        """Gate 2 triple lock: REAL + is_live_intent=True + cfg['live']=True +
        MT5_LIVE unset → BLOCKS. MT5_LIVE=1 env must also be armed."""
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        monkeypatch.delenv("MT5_LIVE", raising=False)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(live=True), is_live_intent=True,  # env not armed
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        assert "MT5_LIVE" in result["error"]["message"]

    def test_check_order_gate_live_demo_passes_regardless(self, mocked_mt5, monkeypatch):
        """Gate 2 triple lock is REAL-account-only. DEMO passes with no arming."""
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=0)  # DEMO
        monkeypatch.delenv("MT5_LIVE", raising=False)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(live=False), is_live_intent=False,  # nothing armed
        )
        # DEMO accounts bypass the triple lock entirely
        if not result["ok"]:
            assert result["error"]["code"] != "RISK_LIVE_GATE_BLOCKED"

    def test_check_order_gate_symbol_not_allowed(self, mocked_mt5):
        """Gate 3: symbol not in allowlist → RISK_SYMBOL_NOT_ALLOWED."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="USDJPY", side="buy", volume=0.1,
            sl=149.0, strategy_id=None,
            cfg=_cfg(symbol_allowlist=["EURUSD"]), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_SYMBOL_NOT_ALLOWED"

    def test_check_order_gate_max_lot(self, mocked_mt5):
        """Gate 4: volume > max_lot_per_order → RISK_MAX_LOT_EXCEEDED."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=10.0,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(max_lot_per_order=2.5), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"

    def test_check_order_gate_no_sl(self, mocked_mt5):
        """Gate 5a: sl=None → RISK_NO_STOP_LOSS."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=None, strategy_id=None,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_gate_sl_distance(self, mocked_mt5):
        """Gate 5b: SL too close to entry → RISK_NO_STOP_LOSS (distance variant).
        Market order (entry_price=None): uses tick.ask as the reference price.
        ask=1.1001, sl=1.10009, distance=0.1 pts < min_sl_distance_points=5.
        """
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.10009,  # distance = |1.1001 - 1.10009| / 0.0001 = 1.0 pt < min 5
            strategy_id=None,
            cfg=_cfg(min_sl_distance_points=5), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_gate_sl_distance_pending_measures_from_trigger(self, mocked_mt5):
        """Gate 5b for PENDING orders: SL distance is measured from the
        caller-provided entry_price (trigger), NOT from current ask.

        This is the exact Codex P1 #2 case: a far-away pending order whose
        SL is close to the trigger but far from the ask.

        ask=1.1001 (current market), entry_price=1.2000 (limit trigger far
        above), sl=1.19995. SL-to-trigger distance = 0.5 pts < min 5,
        but SL-to-ask distance = 996.5 pts > min 5.

        Pre-fix: gate would compute from ask (996.5 pts) and PASS.
        Post-fix: gate computes from trigger (0.5 pts) and BLOCKS.
        """
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.19995,         # 0.5 pts below the trigger
            entry_price=1.2000, # pending trigger price (far above current ask)
            strategy_id=None,
            cfg=_cfg(min_sl_distance_points=5), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_gate_sl_distance_pending_passes_when_far(self, mocked_mt5):
        """Gate 5b for PENDING orders: SL far from trigger passes even
        when current ask is much closer or farther than the trigger.
        """
        self._setup_happy_path(mocked_mt5)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.1900,           # 100 pts below the trigger
            entry_price=1.2000,  # pending trigger
            strategy_id=None,
            cfg=_cfg(min_sl_distance_points=5), is_live_intent=False,
        )
        # Should not fail on SL distance specifically
        if not result["ok"]:
            assert result["error"]["code"] != "RISK_NO_STOP_LOSS"

    def test_check_order_gate_spread(self, mocked_mt5):
        """Gate 6: spread > max_spread_points → RISK_SPREAD_TOO_WIDE."""
        self._setup_happy_path(mocked_mt5)
        # spread = (ask - bid) / point = (1.1100 - 1.1000) / 0.0001 = 1000 pts
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1100)
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0000,  # far enough from ask=1.1100: 11000 pts > min 5
            strategy_id=None,
            cfg=_cfg(max_spread_points=50), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_SPREAD_TOO_WIDE"

    def test_check_order_gate_hedge_blocked(self, mocked_mt5):
        """Gate 7: opposing position exists + allow_hedging=False → RISK_HEDGE_BLOCKED."""
        self._setup_happy_path(mocked_mt5)
        # Existing SELL position on EURUSD; new order is BUY → hedge
        existing_sell = _pos(symbol="EURUSD", pos_type=1)  # SELL
        mocked_mt5.positions_get.return_value = [existing_sell]
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(allow_hedging=False), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_HEDGE_BLOCKED"

    def test_check_order_gate_max_positions(self, mocked_mt5):
        """Gate 8: positions_total >= max_positions → RISK_MAX_POSITIONS."""
        self._setup_happy_path(mocked_mt5)
        # 3 existing positions; max is 3
        positions = [_pos(symbol="GBPUSD") for _ in range(3)]
        mocked_mt5.positions_get.return_value = positions
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(allow_hedging=True, max_positions=3), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_POSITIONS"

    def test_check_order_gate_insufficient_margin(self, mocked_mt5):
        """Gate 9: free_margin / equity * 100 < min_free_margin_pct → RISK_INSUFFICIENT_MARGIN."""
        self._setup_happy_path(mocked_mt5)
        # equity=10000, margin_free=1000 → 10% < min 20%
        mocked_mt5.account_info.return_value = _acct(trade_mode=0, equity=10000.0, margin_free=1000.0)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(min_free_margin_pct=20.0), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INSUFFICIENT_MARGIN"

    def test_check_order_gate_daily_loss(self, mocked_mt5):
        """Gate 10: daily_loss <= -max_daily_loss → RISK_MAX_DAILY_LOSS.
        NOTE: trigger is negative daily_loss, not abs() — task table wrong, legacy correct.
        """
        self._setup_happy_path(mocked_mt5)
        # Simulate a -5000 realized loss today
        mocked_mt5.history_deals_get.return_value = [_deal(profit=-5000.0)]
        mocked_mt5.positions_get.return_value = []
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(max_daily_loss=5000.0), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_DAILY_LOSS"

    def test_check_order_gate_rate_limit(self, mocked_mt5):
        """Gate 11: fill the sliding window → RISK_RATE_LIMIT."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter, _rate_limiter
        _reset_rate_limiter()
        now = time.monotonic()
        # Pre-fill to max_orders_per_minute=3
        for _ in range(3):
            _rate_limiter.append(now)
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0990, strategy_id=None,
            cfg=_cfg(max_orders_per_minute=3), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_RATE_LIMIT"

    def test_check_order_passes_when_all_gates_clear(self, mocked_mt5):
        """Happy path: all gates pass → returns ok envelope."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900,  # ask=1.1001, distance=1010 pts >> min 5
            strategy_id=None,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True

    def test_check_order_consume_false_does_not_fill_slot(self, mocked_mt5):
        """consume_rate_limit=False skips slot consumption (dry-run safe)."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter, _rate_limiter
        _reset_rate_limiter()
        initial_len = len(_rate_limiter)
        check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, strategy_id=None,
            cfg=_cfg(), is_live_intent=False,
            consume_rate_limit=False,
        )
        assert len(_rate_limiter) == initial_len  # no slot added

    def test_check_order_no_mt5_retcode_in_error(self, mocked_mt5):
        """Error envelopes must NOT contain mt5_retcode (legacy divergence)."""
        self._setup_happy_path(mocked_mt5)
        from mt5_cli.risk.risk import check_order, _reset_rate_limiter
        _reset_rate_limiter()
        result = check_order(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=None, strategy_id=None,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert "mt5_retcode" not in result["error"]


# ---------------------------------------------------------------------------
# compute_volume_from_risk_pct tests
# ---------------------------------------------------------------------------

class TestComputeVolumeFromRiskPct:

    def test_compute_volume_basic(self, mocked_mt5):
        """Basic calculation returns ok envelope with a volume key."""
        mocked_mt5.symbol_info.return_value = _sym_info(
            point=0.0001, trade_tick_value=1.0,
            volume_min=0.01, volume_max=100.0, volume_step=0.01,
        )
        mocked_mt5.account_info.return_value = _acct(equity=10000.0)
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=1.0,
            entry_price=1.1001, sl_price=1.0901,
            cfg=_cfg(),
        )
        assert result["ok"] is True
        assert "volume" in result["data"]
        assert result["data"]["volume"] >= 0.01

    def test_compute_volume_invalid_pct_fails(self, mocked_mt5):
        """Negative risk_pct ... actually this guard isn't in legacy. Test zero-distance instead."""
        # Zero distance (entry == sl) → RISK_INVALID_INPUT
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        mocked_mt5.account_info.return_value = _acct(equity=10000.0)
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=1.0,
            entry_price=1.1001, sl_price=1.1001,  # zero distance
            cfg=_cfg(),
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_compute_volume_zero_distance_fails(self, mocked_mt5):
        """entry == sl_price → sl_distance_points=0 → RISK_INVALID_INPUT."""
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
        mocked_mt5.account_info.return_value = _acct(equity=10000.0)
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=2.0,
            entry_price=1.5000, sl_price=1.5000,  # zero distance
            cfg=_cfg(),
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_compute_volume_no_symbol_info(self, mocked_mt5):
        """symbol_info returns None → RISK_INVALID_INPUT."""
        mocked_mt5.symbol_info.return_value = None
        mocked_mt5.account_info.return_value = _acct()
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=1.0,
            entry_price=1.1001, sl_price=1.0901,
            cfg=_cfg(),
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_compute_volume_zero_point_fails(self, mocked_mt5):
        """point=0 → RISK_INVALID_INPUT (cannot compute SL distance)."""
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.0)
        mocked_mt5.account_info.return_value = _acct(equity=10000.0)
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=1.0,
            entry_price=1.1001, sl_price=1.0901,
            cfg=_cfg(),
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_compute_volume_clamps_to_volume_min(self, mocked_mt5):
        """Very tiny equity → computed lot < volume_min → clamped to volume_min."""
        mocked_mt5.symbol_info.return_value = _sym_info(
            point=0.0001, trade_tick_value=1.0,
            volume_min=0.01, volume_max=100.0, volume_step=0.01,
        )
        mocked_mt5.account_info.return_value = _acct(equity=1.0)  # tiny equity
        from mt5_cli.risk.risk import compute_volume_from_risk_pct
        result = compute_volume_from_risk_pct(
            symbol="EURUSD", risk_pct=0.01,
            entry_price=1.1001, sl_price=1.0001,  # big distance
            cfg=_cfg(),
        )
        assert result["ok"] is True
        assert result["data"]["volume"] >= 0.01  # clamped up to volume_min


# ---------------------------------------------------------------------------
# daily_loss tests
# ---------------------------------------------------------------------------

class TestDailyLoss:

    def test_daily_loss_returns_combined(self, mocked_mt5):
        """realized (deals) + floating (open positions) are summed."""
        mocked_mt5.history_deals_get.return_value = [
            _deal(profit=-200.0, commission=-5.0, swap=-1.0),
            _deal(profit=50.0, commission=0.0, swap=0.0),
        ]
        mocked_mt5.positions_get.return_value = [
            _pos(profit=-100.0),
            _pos(profit=30.0),
        ]
        from mt5_cli.risk.risk import daily_loss
        result = daily_loss(_cfg())
        # realized = -200 - 5 - 1 + 50 = -156; floating = -100 + 30 = -70; total = -226
        assert result == pytest.approx(-226.0)

    def test_daily_loss_zero_when_no_deals_or_positions(self, mocked_mt5):
        """No deals, no positions → 0.0."""
        mocked_mt5.history_deals_get.return_value = []
        mocked_mt5.positions_get.return_value = []
        from mt5_cli.risk.risk import daily_loss
        assert daily_loss(_cfg()) == 0.0

    def test_daily_loss_positive_on_winning_day(self, mocked_mt5):
        """Profitable day returns positive float."""
        mocked_mt5.history_deals_get.return_value = [_deal(profit=500.0)]
        mocked_mt5.positions_get.return_value = []
        from mt5_cli.risk.risk import daily_loss
        assert daily_loss(_cfg()) == pytest.approx(500.0)

    def test_daily_loss_includes_commission_and_swap(self, mocked_mt5):
        """Commission and swap are included in realized P&L."""
        mocked_mt5.history_deals_get.return_value = [
            _deal(profit=100.0, commission=-3.0, swap=-2.0)
        ]
        mocked_mt5.positions_get.return_value = []
        from mt5_cli.risk.risk import daily_loss
        assert daily_loss(_cfg()) == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# resolve_magic — default collision guard tests (Fix 2)
# ---------------------------------------------------------------------------

def test_resolve_magic_default_collision_guard_None_strategy_id(mocked_mt5):
    from mt5_cli.risk import resolve_magic
    cfg = {"magic": 150000}
    with pytest.raises(ValueError, match="must be < 100000"):
        resolve_magic(None, cfg)


def test_resolve_magic_default_collision_guard_empty_strategy_id(mocked_mt5):
    from mt5_cli.risk import resolve_magic
    cfg = {"magic": 162538}
    with pytest.raises(ValueError, match="must be < 100000"):
        resolve_magic("", cfg)
