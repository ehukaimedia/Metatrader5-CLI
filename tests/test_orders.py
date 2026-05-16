"""
test_orders.py — TDD for mt5_universal/orders/orders.py

Cherry-pick of 6 functions: list_pending, place_market, place_limit,
dryrun, cancel, poll_fill.

Deliberate divergences from legacy (per spec):
- risk_pct parameter dropped from place_market / place_limit / dryrun signatures.
- _resolve_filling always returns ORDER_FILLING_FOK ("auto" hardcoded; broker
  profile lands in Task 2.8).
- _resolve_pending_filling for "auto" also returns FOK (not ORDER_FILLING_RETURN
  as legacy did — plan says FOK/IOC only, no RETURN for pending).
- expiry parameter dropped from place_limit (ORDER_TIME_SPECIFIED not needed).
- risk.check_order called keyword-only (new API); never positionally.
- compute_volume_from_risk_pct returns ok({"volume":...}) envelope — but that
  path is not exercised in orders (risk_pct param removed from this slice).
- _finalize_order error wraps mt5_retcode in data={"mt5_retcode": ...}.
"""
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Cache-safe fixture
# ---------------------------------------------------------------------------

_MODULES_TO_PURGE = (
    "mt5_universal.bridge",
    "mt5_universal.bridge.mt5_backend",
    "mt5_universal.risk",
    "mt5_universal.risk.risk",
    "mt5_universal.orders",
    "mt5_universal.orders.orders",
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

    # Filling / order type constants
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.ORDER_TYPE_BUY_LIMIT = 2
    fake.ORDER_TYPE_SELL_LIMIT = 3
    fake.ORDER_TYPE_BUY_STOP = 4
    fake.ORDER_TYPE_SELL_STOP = 5

    # Trade action constants
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_PENDING = 5
    fake.TRADE_ACTION_SLTP = 6
    fake.TRADE_ACTION_MODIFY = 7
    fake.TRADE_ACTION_REMOVE = 8

    # Retcode constants — MUST be real ints so retcode comparisons work
    fake.TRADE_RETCODE_DONE = 10009
    fake.TRADE_RETCODE_PLACED = 10008
    fake.TRADE_RETCODE_INVALID_FILL = 10030

    # Timeframe constants (required by bridge __init__ import)
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
# Default config + mock factories
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> dict:
    """Return a base config that passes all risk gates unless overridden."""
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


def _acct(trade_mode=0, equity=10000.0, margin_free=9000.0) -> MagicMock:
    return MagicMock(trade_mode=trade_mode, equity=equity, margin_free=margin_free)


def _tick(bid=1.1000, ask=1.1001) -> MagicMock:
    return MagicMock(bid=bid, ask=ask)


def _sym_info(point=0.0001, trade_tick_value=1.0,
              volume_min=0.01, volume_max=100.0, volume_step=0.01,
              filling_mode=1) -> MagicMock:
    return MagicMock(
        point=point, trade_tick_value=trade_tick_value,
        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
        filling_mode=filling_mode,
    )


def _make_pending_order(
    ticket=111, symbol="EURUSD", order_type=2, volume_initial=0.1,
    volume_current=0.1, price_open=1.1050, price_current=1.1050,
    sl=1.0950, tp=0.0, magic=88888, comment="", state=1,
    type_filling=0, type_time=1, time_setup=0, time_expiration=0,
) -> MagicMock:
    return MagicMock(
        ticket=ticket,
        symbol=symbol,
        type=order_type,
        volume_initial=volume_initial,
        volume_current=volume_current,
        price_open=price_open,
        price_current=price_current,
        sl=sl,
        tp=tp,
        magic=magic,
        comment=comment,
        state=state,
        type_filling=type_filling,
        type_time=type_time,
        time_setup=time_setup,
        time_expiration=time_expiration,
    )


def _make_send_result(retcode=10009, order=222) -> MagicMock:
    r = MagicMock()
    r.retcode = retcode
    r.order = order
    r.comment = ""
    r.time = 0
    return r


def _setup_happy_path(mocked_mt5):
    """Wire defaults so all risk gates pass."""
    mocked_mt5.account_info.return_value = _acct(trade_mode=0, equity=10000.0, margin_free=9000.0)
    mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
    mocked_mt5.symbol_info.return_value = _sym_info(point=0.0001)
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.positions_get.return_value = []
    mocked_mt5.history_deals_get.return_value = []


def _reset_rl():
    """Reset the rate limiter between tests (import after mock is in place)."""
    from mt5_universal.risk.risk import _reset_rate_limiter
    _reset_rate_limiter()


# ---------------------------------------------------------------------------
# list_pending tests
# ---------------------------------------------------------------------------

class TestListPending:

    def test_list_pending_returns_envelope_with_empty_list(self, mocked_mt5):
        """orders_get returns [] → ok envelope with empty data list."""
        mocked_mt5.orders_get.return_value = []
        from mt5_universal.orders.orders import list_pending
        result = list_pending(cfg=_cfg())
        assert result["ok"] is True
        assert result["data"] == []

    def test_list_pending_returns_none_fails(self, mocked_mt5):
        """orders_get returns None → fail envelope."""
        mocked_mt5.orders_get.return_value = None
        from mt5_universal.orders.orders import list_pending
        result = list_pending(cfg=_cfg())
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_NO_DATA"

    def test_list_pending_filters_by_symbol(self, mocked_mt5):
        """When symbol is passed, only orders for that symbol are returned."""
        eu_order = _make_pending_order(ticket=1, symbol="EURUSD")
        mocked_mt5.orders_get.return_value = [eu_order]
        from mt5_universal.orders.orders import list_pending
        result = list_pending(symbol="EURUSD", cfg=_cfg())
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["symbol"] == "EURUSD"

    def test_list_pending_filters_by_strategy_id(self, mocked_mt5):
        """strategy_id filters by resolved magic number."""
        # cfg maps "alpha" → magic 50000
        cfg = _cfg(strategy_ids={"alpha": 50000})
        alpha_order = _make_pending_order(ticket=10, magic=50000)
        other_order = _make_pending_order(ticket=11, magic=88888)
        mocked_mt5.orders_get.return_value = [alpha_order, other_order]
        from mt5_universal.orders.orders import list_pending
        result = list_pending(strategy_id="alpha", cfg=cfg)
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["ticket"] == 10

    def test_list_pending_marks_agent_magic(self, mocked_mt5):
        """Order in [100000, 180000) → is_agent_magic=True."""
        agent_magic = 150000  # in [100000, 180000)
        order = _make_pending_order(ticket=99, magic=agent_magic)
        mocked_mt5.orders_get.return_value = [order]
        from mt5_universal.orders.orders import list_pending
        result = list_pending(cfg=_cfg())
        assert result["ok"] is True
        assert result["data"][0]["is_agent_magic"] is True

    def test_list_pending_non_agent_magic_marked_false(self, mocked_mt5):
        """Order with magic 88888 (< 100000) → is_agent_magic=False."""
        order = _make_pending_order(ticket=50, magic=88888)
        mocked_mt5.orders_get.return_value = [order]
        from mt5_universal.orders.orders import list_pending
        result = list_pending(cfg=_cfg())
        assert result["ok"] is True
        assert result["data"][0]["is_agent_magic"] is False

    def test_list_pending_requires_cfg_when_strategy_id_given(self, mocked_mt5):
        """strategy_id without cfg → fail(RISK_INVALID_INPUT)."""
        from mt5_universal.orders.orders import list_pending
        result = list_pending(strategy_id="alpha", cfg=None)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"


# ---------------------------------------------------------------------------
# dryrun tests
# ---------------------------------------------------------------------------

class TestDryrun:

    def test_dryrun_passes_risk_then_calls_order_check_not_order_send(self, mocked_mt5):
        """dryrun must call order_check and NOT order_send."""
        _setup_happy_path(mocked_mt5)
        check_result = MagicMock()
        check_result.retcode = 0
        check_result.margin = 100.0
        check_result.margin_free = 8900.0
        check_result.margin_level = 90.0
        check_result.profit = 0.0
        mocked_mt5.order_check.return_value = check_result
        _reset_rl()
        from mt5_universal.orders.orders import dryrun
        result = dryrun(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        assert result["data"]["dry_run"] is True
        mocked_mt5.order_check.assert_called_once()
        mocked_mt5.order_send.assert_not_called()

    def test_dryrun_returns_risk_error_when_gate_blocks(self, mocked_mt5):
        """When risk gate blocks, dryrun returns the fail envelope immediately."""
        _setup_happy_path(mocked_mt5)
        # Force max_lot_per_order=0 to trip gate 4
        _reset_rl()
        from mt5_universal.orders.orders import dryrun
        result = dryrun(
            symbol="EURUSD", side="buy", volume=1.0,
            sl=1.0900, cfg=_cfg(max_lot_per_order=0.5), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        mocked_mt5.order_check.assert_not_called()

    def test_dryrun_market_order_uses_TRADE_ACTION_DEAL(self, mocked_mt5):
        """Market dryrun sends a request with action=TRADE_ACTION_DEAL."""
        _setup_happy_path(mocked_mt5)
        check_result = MagicMock()
        check_result.retcode = 0
        check_result.margin = 50.0
        check_result.margin_free = 8950.0
        check_result.margin_level = 90.0
        check_result.profit = 0.0
        mocked_mt5.order_check.return_value = check_result
        _reset_rl()
        from mt5_universal.orders.orders import dryrun
        dryrun(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, order_type="market", cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_check.call_args[0][0]
        assert call_args["action"] == 1  # TRADE_ACTION_DEAL

    def test_dryrun_limit_order_uses_TRADE_ACTION_PENDING_and_takes_price(self, mocked_mt5):
        """Limit dryrun sends action=TRADE_ACTION_PENDING and uses explicit price."""
        _setup_happy_path(mocked_mt5)
        check_result = MagicMock()
        check_result.retcode = 0
        check_result.margin = 50.0
        check_result.margin_free = 8950.0
        check_result.margin_level = 90.0
        check_result.profit = 0.0
        mocked_mt5.order_check.return_value = check_result
        _reset_rl()
        from mt5_universal.orders.orders import dryrun
        result = dryrun(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0800, order_type="limit", price=1.1050,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        call_args = mocked_mt5.order_check.call_args[0][0]
        assert call_args["action"] == 5  # TRADE_ACTION_PENDING
        assert call_args["price"] == 1.1050

    def test_dryrun_requires_price_for_pending(self, mocked_mt5):
        """limit/stop dryrun without --price → fail(MT5_INVALID_PARAMS)."""
        _setup_happy_path(mocked_mt5)
        _reset_rl()
        from mt5_universal.orders.orders import dryrun
        result = dryrun(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, order_type="limit", price=None,
            cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_PARAMS"


# ---------------------------------------------------------------------------
# place_market tests
# ---------------------------------------------------------------------------

class TestPlaceMarket:

    def test_place_market_buy_returns_envelope_with_ticket(self, mocked_mt5):
        """Happy path: place_market buy → ok envelope with ticket key."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=555)
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        result = place_market(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        assert result["data"]["ticket"] == 555

    def test_place_market_blocks_when_risk_gate_fails(self, mocked_mt5):
        """Risk gate failure → fail envelope; order_send NOT called."""
        _setup_happy_path(mocked_mt5)
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        result = place_market(
            symbol="EURUSD", side="buy", volume=5.0,
            sl=1.0900, cfg=_cfg(max_lot_per_order=2.0), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        mocked_mt5.order_send.assert_not_called()

    def test_place_market_calls_order_send_with_TRADE_ACTION_DEAL(self, mocked_mt5):
        """place_market sends request with action=TRADE_ACTION_DEAL."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=600)
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        place_market(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 1  # TRADE_ACTION_DEAL

    def test_place_market_uses_FOK_filling(self, mocked_mt5):
        """place_market should use ORDER_FILLING_FOK."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=601)
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        place_market(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == 1  # ORDER_FILLING_FOK

    def test_place_market_sell_uses_bid_price(self, mocked_mt5):
        """Sell order entry price uses bid, not ask."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1005)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=602)
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        place_market(
            symbol="EURUSD", side="sell", volume=0.1,
            sl=1.1100, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["price"] == 1.1000  # bid

    def test_place_market_order_rejected_returns_fail(self, mocked_mt5):
        """Broker rejects order → fail(MT5_ORDER_REJECTED)."""
        _setup_happy_path(mocked_mt5)
        send_result = _make_send_result(retcode=10006)  # TRADE_RETCODE_REJECT
        send_result.comment = "No money"
        mocked_mt5.order_send.return_value = send_result
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        result = place_market(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_ORDER_REJECTED"

    def test_place_market_none_result_returns_fail(self, mocked_mt5):
        """order_send returns None → fail(MT5_ORDER_REJECTED)."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = None
        _reset_rl()
        from mt5_universal.orders.orders import place_market
        result = place_market(
            symbol="EURUSD", side="buy", volume=0.1,
            sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_ORDER_REJECTED"


# ---------------------------------------------------------------------------
# place_limit tests
# ---------------------------------------------------------------------------

class TestPlaceLimit:

    def test_place_limit_uses_pending_filling_and_TRADE_ACTION_PENDING(self, mocked_mt5):
        """place_limit sends action=TRADE_ACTION_PENDING with FOK filling."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=700)
        _reset_rl()
        from mt5_universal.orders.orders import place_limit
        result = place_limit(
            symbol="EURUSD", side="buy", price=1.1050,
            volume=0.1, sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 5   # TRADE_ACTION_PENDING
        assert call_args["type_filling"] == 1  # ORDER_FILLING_FOK (hardcoded)

    def test_place_limit_blocks_when_risk_gate_fails(self, mocked_mt5):
        """Risk gate failure on limit → fail envelope; order_send NOT called."""
        _setup_happy_path(mocked_mt5)
        _reset_rl()
        from mt5_universal.orders.orders import place_limit
        result = place_limit(
            symbol="EURUSD", side="buy", price=1.1050,
            volume=5.0, sl=1.0900,
            cfg=_cfg(max_lot_per_order=2.0), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        mocked_mt5.order_send.assert_not_called()

    def test_place_limit_sell_uses_sell_limit_type(self, mocked_mt5):
        """Sell limit → ORDER_TYPE_SELL_LIMIT in request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=701)
        _reset_rl()
        from mt5_universal.orders.orders import place_limit
        place_limit(
            symbol="EURUSD", side="sell", price=1.1200,
            volume=0.1, sl=1.1300, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["type"] == 3  # ORDER_TYPE_SELL_LIMIT

    def test_place_limit_buy_uses_buy_limit_type(self, mocked_mt5):
        """Buy limit → ORDER_TYPE_BUY_LIMIT in request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=702)
        _reset_rl()
        from mt5_universal.orders.orders import place_limit
        place_limit(
            symbol="EURUSD", side="buy", price=1.0900,
            volume=0.1, sl=1.0800, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["type"] == 2  # ORDER_TYPE_BUY_LIMIT


# ---------------------------------------------------------------------------
# cancel tests
# ---------------------------------------------------------------------------

class TestCancel:

    def test_cancel_calls_order_send_with_TRADE_ACTION_REMOVE(self, mocked_mt5):
        """cancel sends action=TRADE_ACTION_REMOVE."""
        _setup_happy_path(mocked_mt5)
        pending = _make_pending_order(ticket=800, symbol="EURUSD")
        mocked_mt5.orders_get.return_value = [pending]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=800)
        from mt5_universal.orders.orders import cancel
        result = cancel(800, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["ticket"] == 800
        assert result["data"]["cancelled"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 8  # TRADE_ACTION_REMOVE

    def test_cancel_requires_live_intent_on_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        from mt5_universal.orders.orders import cancel
        result = cancel(900, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        mocked_mt5.order_send.assert_not_called()

    def test_cancel_ticket_not_found(self, mocked_mt5):
        """orders_get returns empty → MT5_TICKET_NOT_FOUND."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.orders_get.return_value = []
        # is_live_intent=True so live gate passes (account is DEMO)
        from mt5_universal.orders.orders import cancel
        result = cancel(999, is_live_intent=True)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_TICKET_NOT_FOUND"


# ---------------------------------------------------------------------------
# poll_fill tests
# ---------------------------------------------------------------------------

class TestPollFill:

    def test_poll_fill_returns_filled_when_position_appears(self, mocked_mt5):
        """positions_get returns a match → filled=True."""
        pos = MagicMock()
        pos.ticket = 111
        mocked_mt5.positions_get.return_value = [pos]
        from mt5_universal.orders.orders import poll_fill
        result = poll_fill(111, timeout_ms=500)
        assert result["ok"] is True
        assert result["data"]["filled"] is True
        assert result["data"]["ticket"] == 111

    def test_poll_fill_returns_timeout_when_no_fill(self, mocked_mt5):
        """No position ever appears AND pending stays → filled=False (timeout)."""
        pending = _make_pending_order(ticket=222)
        mocked_mt5.positions_get.return_value = []
        mocked_mt5.orders_get.return_value = [pending]  # still pending
        from mt5_universal.orders.orders import poll_fill
        result = poll_fill(222, timeout_ms=100)  # short timeout
        assert result["ok"] is True
        assert result["data"]["filled"] is False
        assert result["data"]["ticket"] == 222

    def test_poll_fill_returns_not_filled_when_order_vanishes(self, mocked_mt5):
        """Pending order disappears (rejected/cancelled) before fill → filled=False."""
        mocked_mt5.positions_get.return_value = []
        mocked_mt5.orders_get.return_value = []  # order gone (not filled, just gone)
        from mt5_universal.orders.orders import poll_fill
        result = poll_fill(333, timeout_ms=500)
        assert result["ok"] is True
        assert result["data"]["filled"] is False


# ---------------------------------------------------------------------------
# _normalize_side / invalid side rejection tests (Fix 1)
# ---------------------------------------------------------------------------

def test_place_market_rejects_invalid_side(mocked_mt5):
    from mt5_universal.orders import place_market
    cfg = _cfg()
    env = place_market(symbol="USDJPY", side="long", volume=0.01, sl=149.5,
                      cfg=cfg, is_live_intent=False)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    mocked_mt5.order_send.assert_not_called()


def test_place_limit_rejects_invalid_side(mocked_mt5):
    from mt5_universal.orders import place_limit
    cfg = _cfg()
    env = place_limit(symbol="USDJPY", side="LONG", price=150.0, volume=0.01,
                     sl=149.5, cfg=cfg, is_live_intent=False)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    mocked_mt5.order_send.assert_not_called()


def test_dryrun_rejects_invalid_side(mocked_mt5):
    from mt5_universal.orders import dryrun
    cfg = _cfg()
    env = dryrun(symbol="USDJPY", side="short", volume=0.01, sl=149.5,
                cfg=cfg, is_live_intent=False)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    mocked_mt5.order_check.assert_not_called()


def test_place_market_accepts_uppercase_BUY(mocked_mt5):
    """Case-insensitive — 'BUY' normalizes to 'buy' and proceeds."""
    from mt5_universal.orders import place_market
    _setup_happy_path(mocked_mt5)
    mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=999)
    _reset_rl()
    cfg = _cfg()
    env = place_market(symbol="EURUSD", side="BUY", volume=0.01, sl=1.0900,
                      cfg=cfg, is_live_intent=False)
    assert env["ok"] is True


# ---------------------------------------------------------------------------
# place_stop tests
# ---------------------------------------------------------------------------

class TestPlaceStop:

    def test_place_stop_buy_sends_TRADE_ACTION_PENDING_with_BUY_STOP(self, mocked_mt5):
        """Buy stop → TRADE_ACTION_PENDING + ORDER_TYPE_BUY_STOP in request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=1001)
        _reset_rl()
        from mt5_universal.orders.orders import place_stop
        result = place_stop(
            symbol="USDJPY", side="buy", price=151.0,
            volume=0.1, sl=149.0, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 5   # TRADE_ACTION_PENDING
        assert call_args["type"] == 4     # ORDER_TYPE_BUY_STOP

    def test_place_stop_sell_sends_SELL_STOP(self, mocked_mt5):
        """Sell stop → ORDER_TYPE_SELL_STOP in request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=1002)
        _reset_rl()
        from mt5_universal.orders.orders import place_stop
        result = place_stop(
            symbol="USDJPY", side="sell", price=148.0,
            volume=0.1, sl=150.0, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["type"] == 5     # ORDER_TYPE_SELL_STOP

    def test_place_stop_blocks_when_risk_gate_fails(self, mocked_mt5):
        """Risk gate failure → fail envelope; order_send NOT called."""
        _setup_happy_path(mocked_mt5)
        _reset_rl()
        from mt5_universal.orders.orders import place_stop
        result = place_stop(
            symbol="USDJPY", side="buy", price=151.0,
            volume=5.0, sl=149.0,
            cfg=_cfg(max_lot_per_order=2.0), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        mocked_mt5.order_send.assert_not_called()

    def test_place_stop_rejects_invalid_side(self, mocked_mt5):
        """Invalid side string → MT5_INVALID_PARAMS before any MT5 call."""
        _setup_happy_path(mocked_mt5)
        _reset_rl()
        from mt5_universal.orders.orders import place_stop
        result = place_stop(
            symbol="USDJPY", side="long", price=151.0,
            volume=0.1, sl=149.0, cfg=_cfg(), is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_PARAMS"
        mocked_mt5.order_send.assert_not_called()

    def test_place_stop_price_appears_in_request(self, mocked_mt5):
        """The stop trigger price must be included in the order_send request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10008, order=1003)
        _reset_rl()
        from mt5_universal.orders.orders import place_stop
        # sl=1.0900 is >5 pts below current ask (1.1001), so risk gate passes.
        # price=1.1200 is the stop trigger above current market.
        place_stop(
            symbol="EURUSD", side="buy", price=1.1200,
            volume=0.1, sl=1.0900, cfg=_cfg(), is_live_intent=False,
        )
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["price"] == 1.1200


# ---------------------------------------------------------------------------
# modify tests
# ---------------------------------------------------------------------------

def _make_position(ticket=12345, symbol="USDJPY", pos_type=0,
                   sl=149.0, tp=151.0, volume=0.1, magic=88888) -> MagicMock:
    """Return a mock MT5 position object."""
    return MagicMock(
        ticket=ticket,
        symbol=symbol,
        type=pos_type,
        sl=sl,
        tp=tp,
        volume=volume,
        magic=magic,
    )


def _make_pending_order_for_modify(
    ticket=54321, symbol="USDJPY", order_type=4,
    price_open=151.0, sl=149.0, tp=153.0,
    type_time=1, time_expiration=0, magic=88888,
) -> MagicMock:
    """Return a mock MT5 pending order with the fields modify needs."""
    return MagicMock(
        ticket=ticket,
        symbol=symbol,
        type=order_type,
        price_open=price_open,
        sl=sl,
        tp=tp,
        type_time=type_time,
        time_expiration=time_expiration,
        magic=magic,
    )


class TestModify:

    def test_modify_open_position_uses_TRADE_ACTION_SLTP(self, mocked_mt5):
        """Ticket found as position → TRADE_ACTION_SLTP in request."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=12345, symbol="USDJPY", sl=149.0, tp=151.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=12345)
        from mt5_universal.orders.orders import modify
        result = modify(12345, sl=148.5, tp=152.0, is_live_intent=False)
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 6   # TRADE_ACTION_SLTP
        assert call_args["position"] == 12345

    def test_modify_open_position_preserves_existing_tp_when_new_tp_None(self, mocked_mt5):
        """Caller passes tp=None → existing tp is preserved (not zeroed)."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=12345, symbol="USDJPY", sl=149.0, tp=153.5)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=12345)
        from mt5_universal.orders.orders import modify
        result = modify(12345, sl=148.0, tp=None, is_live_intent=False)
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["tp"] == 153.5   # preserved from existing position

    def test_modify_pending_order_uses_TRADE_ACTION_MODIFY(self, mocked_mt5):
        """Ticket found as pending order → TRADE_ACTION_MODIFY in request."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        pending = _make_pending_order_for_modify(ticket=54321)
        mocked_mt5.orders_get.return_value = [pending]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=54321)
        from mt5_universal.orders.orders import modify
        result = modify(54321, sl=148.0, tp=154.0, is_live_intent=False)
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["action"] == 7   # TRADE_ACTION_MODIFY
        assert call_args["order"] == 54321

    def test_modify_pending_order_preserves_existing_price_when_new_price_None(self, mocked_mt5):
        """Caller passes price=None → existing price_open is preserved."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        pending = _make_pending_order_for_modify(ticket=54321, price_open=151.5)
        mocked_mt5.orders_get.return_value = [pending]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=54321)
        from mt5_universal.orders.orders import modify
        result = modify(54321, price=None, is_live_intent=False)
        assert result["ok"] is True
        call_args = mocked_mt5.order_send.call_args[0][0]
        assert call_args["price"] == 151.5  # preserved from pending order

    def test_modify_returns_MT5_TICKET_NOT_FOUND_when_neither(self, mocked_mt5):
        """Ticket not found in positions or pending orders → MT5_TICKET_NOT_FOUND."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        mocked_mt5.orders_get.return_value = []
        from mt5_universal.orders.orders import modify
        result = modify(99999, sl=1.0, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_TICKET_NOT_FOUND"
        mocked_mt5.order_send.assert_not_called()

    def test_modify_requires_is_live_intent_for_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        from mt5_universal.orders.orders import modify
        result = modify(12345, sl=148.0, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        mocked_mt5.order_send.assert_not_called()

    def test_modify_returns_action_in_data_envelope(self, mocked_mt5):
        """ok data should include ticket and action key."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=12345, symbol="USDJPY", sl=149.0, tp=151.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=12345)
        from mt5_universal.orders.orders import modify
        result = modify(12345, sl=148.5, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["ticket"] == 12345
        assert result["data"]["action"] == "SLTP"


# ---------------------------------------------------------------------------
# cancel_all_pending tests
# ---------------------------------------------------------------------------

class TestCancelAllPending:

    def test_cancel_all_pending_cancels_each_ticket(self, mocked_mt5):
        """All tickets get cancelled; result has per_ticket list with ok=True."""
        _setup_happy_path(mocked_mt5)
        # orders_get returns pending list (first call for cancel_all_pending)
        pending_a = _make_pending_order(ticket=2001, symbol="EURUSD")
        pending_b = _make_pending_order(ticket=2002, symbol="EURUSD")
        # cancel() internally calls orders_get(ticket=...) to fetch order for REMOVE
        # We need multiple return values: first call returns pending list, subsequent
        # per-ticket lookups return [pending_x]
        mocked_mt5.orders_get.side_effect = [
            [pending_a, pending_b],  # cancel_all_pending's initial list call
            [pending_a],             # cancel(2001) lookup
            [pending_b],             # cancel(2002) lookup
        ]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=0)
        from mt5_universal.orders.orders import cancel_all_pending
        result = cancel_all_pending(is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["cancelled"] == 2
        assert result["data"]["failed"] == 0
        per_ticket = result["data"]["per_ticket"]
        assert len(per_ticket) == 2
        assert all(t["ok"] for t in per_ticket)

    def test_cancel_all_pending_filters_by_symbol(self, mocked_mt5):
        """Symbol argument passed to orders_get for filtering."""
        _setup_happy_path(mocked_mt5)
        pending = _make_pending_order(ticket=3001, symbol="GBPUSD")
        mocked_mt5.orders_get.side_effect = [
            [pending],    # initial list for cancel_all_pending(symbol="GBPUSD")
            [pending],    # cancel(3001) lookup
        ]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009, order=0)
        from mt5_universal.orders.orders import cancel_all_pending
        result = cancel_all_pending(symbol="GBPUSD", is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["cancelled"] == 1
        # Verify orders_get was called with symbol kwarg first
        first_call = mocked_mt5.orders_get.call_args_list[0]
        assert first_call == ((), {"symbol": "GBPUSD"}) or "GBPUSD" in str(first_call)

    def test_cancel_all_pending_fails_soft_on_individual_ticket_failures(self, mocked_mt5):
        """Individual cancel failure doesn't abort; both entries appear in per_ticket."""
        _setup_happy_path(mocked_mt5)
        pending_a = _make_pending_order(ticket=4001, symbol="EURUSD")
        pending_b = _make_pending_order(ticket=4002, symbol="EURUSD")
        fail_result = MagicMock()
        fail_result.retcode = 10006   # TRADE_RETCODE_REJECT — not DONE/PLACED
        fail_result.comment = "Reject"
        mocked_mt5.orders_get.side_effect = [
            [pending_a, pending_b],  # initial list
            [pending_a],             # cancel(4001) lookup
            [pending_b],             # cancel(4002) lookup
        ]
        mocked_mt5.order_send.side_effect = [
            _make_send_result(retcode=10009, order=0),  # 4001 succeeds
            fail_result,                                 # 4002 fails
        ]
        from mt5_universal.orders.orders import cancel_all_pending
        result = cancel_all_pending(is_live_intent=False)
        assert result["ok"] is True   # outer still ok
        assert result["data"]["cancelled"] == 1
        assert result["data"]["failed"] == 1
        per_ticket = result["data"]["per_ticket"]
        assert len(per_ticket) == 2
        ok_entries = [t for t in per_ticket if t["ok"]]
        fail_entries = [t for t in per_ticket if not t["ok"]]
        assert len(ok_entries) == 1
        assert len(fail_entries) == 1
        assert "error" in fail_entries[0]

    def test_cancel_all_pending_empty_returns_empty_list(self, mocked_mt5):
        """No pending orders → ok with empty per_ticket list and zero counts."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.orders_get.return_value = []
        from mt5_universal.orders.orders import cancel_all_pending
        result = cancel_all_pending(is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["per_ticket"] == []
        assert result["data"]["cancelled"] == 0
        assert result["data"]["failed"] == 0
