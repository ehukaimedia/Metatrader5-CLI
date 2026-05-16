"""
test_positions.py — TDD for mt5_universal/positions/positions.py

Cherry-pick of 5 functions: list, close, close_all, move_sl, breakeven.

Deliberate divergences from legacy (per spec):
- Uses ok()/fail() from mt5_universal.reports (not legacy _fail helper).
- fail() error wraps mt5_retcode in data={"mt5_retcode": ...}, not as kwarg.
- No risk.check_order — only _live_gate_check (account_info-based).
- No rate limiter involved; no _reset_rl() needed.
"""
import sys
from unittest.mock import MagicMock

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
    "mt5_universal.positions",
    "mt5_universal.positions.positions",
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
# Mock factories
# ---------------------------------------------------------------------------

def _acct(trade_mode=0) -> MagicMock:
    return MagicMock(trade_mode=trade_mode)


def _tick(bid=1.1000, ask=1.1001) -> MagicMock:
    return MagicMock(bid=bid, ask=ask)


def _sym_info(point=0.00001) -> MagicMock:
    return MagicMock(point=point)


def _make_position(
    ticket=100,
    symbol="EURUSD",
    pos_type=0,   # 0=BUY, 1=SELL
    volume=0.1,
    price_open=1.1000,
    sl=1.0900,
    tp=1.1200,
    profit=50.0,
    swap=-0.5,
    magic=88888,
    comment="test",
) -> MagicMock:
    pos = MagicMock()
    pos.ticket = ticket
    pos.symbol = symbol
    pos.type = pos_type
    pos.volume = volume
    pos.price_open = price_open
    pos.sl = sl
    pos.tp = tp
    pos.profit = profit
    pos.swap = swap
    pos.magic = magic
    pos.comment = comment
    return pos


def _make_send_result(retcode=10009, order=200) -> MagicMock:
    r = MagicMock()
    r.retcode = retcode
    r.order = order
    r.comment = ""
    return r


def _setup_happy_path(mocked_mt5):
    """Wire defaults: DEMO account, good tick data."""
    mocked_mt5.account_info.return_value = _acct(trade_mode=0)
    mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1001)
    mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)


# ---------------------------------------------------------------------------
# list tests
# ---------------------------------------------------------------------------

class TestList:

    def test_list_returns_envelope_with_empty_list(self, mocked_mt5):
        """positions_get returns [] → ok envelope with empty data list."""
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import list  # noqa: A004
        result = list()
        assert result["ok"] is True
        assert result["data"] == []

    def test_list_filters_by_symbol(self, mocked_mt5):
        """When symbol is passed, positions_get is called with symbol kwarg."""
        pos = _make_position(ticket=101, symbol="EURUSD")
        mocked_mt5.positions_get.return_value = [pos]
        from mt5_universal.positions.positions import list  # noqa: A004
        result = list(symbol="EURUSD")
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["symbol"] == "EURUSD"
        # Verify positions_get was called with symbol kwarg
        mocked_mt5.positions_get.assert_called_once_with(symbol="EURUSD")

    def test_list_includes_expected_fields(self, mocked_mt5):
        """pos_to_dict produces ticket, symbol, type, volume, open_price, profit, swap."""
        pos = _make_position(
            ticket=102, symbol="GBPUSD", pos_type=0,
            volume=0.2, price_open=1.2500, profit=30.0, swap=-1.0,
        )
        mocked_mt5.positions_get.return_value = [pos]
        from mt5_universal.positions.positions import list  # noqa: A004
        result = list()
        assert result["ok"] is True
        d = result["data"][0]
        assert d["ticket"] == 102
        assert d["symbol"] == "GBPUSD"
        assert d["type"] == "buy"
        assert d["volume"] == 0.2
        assert d["open_price"] == 1.2500
        assert d["profit"] == 30.0
        assert d["swap"] == -1.0

    def test_list_returns_fail_when_positions_get_returns_none(self, mocked_mt5):
        """positions_get returns None → fail(MT5_NO_DATA)."""
        mocked_mt5.positions_get.return_value = None
        from mt5_universal.positions.positions import list  # noqa: A004
        result = list()
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_NO_DATA"

    def test_list_sell_position_type_string(self, mocked_mt5):
        """A SELL position (type=1) should appear as type='sell' in dict."""
        pos = _make_position(ticket=103, pos_type=1)
        mocked_mt5.positions_get.return_value = [pos]
        from mt5_universal.positions.positions import list  # noqa: A004
        result = list()
        assert result["ok"] is True
        assert result["data"][0]["type"] == "sell"


# ---------------------------------------------------------------------------
# close tests
# ---------------------------------------------------------------------------

class TestClose:

    def test_close_buy_sends_opposite_sell_with_position_ticket(self, mocked_mt5):
        """Closing a BUY position sends ORDER_TYPE_SELL + position=ticket."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=200, pos_type=0, volume=0.1)  # BUY
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close
        result = close(200, is_live_intent=False)
        assert result["ok"] is True
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["type"] == 1       # ORDER_TYPE_SELL
        assert req["position"] == 200
        assert req["action"] == 1     # TRADE_ACTION_DEAL

    def test_close_sell_sends_opposite_buy_with_position_ticket(self, mocked_mt5):
        """Closing a SELL position sends ORDER_TYPE_BUY + position=ticket."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=201, pos_type=1, volume=0.1)  # SELL
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close
        result = close(201, is_live_intent=False)
        assert result["ok"] is True
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["type"] == 0       # ORDER_TYPE_BUY
        assert req["position"] == 201

    def test_close_partial_volume_sends_specified_volume(self, mocked_mt5):
        """close(ticket, volume=0.05) sends only 0.05 lots, not full position."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=202, pos_type=0, volume=0.1)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close
        close(202, volume=0.05, is_live_intent=False)
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["volume"] == 0.05

    def test_close_full_volume_when_volume_omitted(self, mocked_mt5):
        """close(ticket) with no volume uses full position volume."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=203, pos_type=0, volume=0.25)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close
        close(203, is_live_intent=False)
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["volume"] == 0.25

    def test_close_blocked_when_is_live_intent_false_on_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)  # REAL
        from mt5_universal.positions.positions import close
        result = close(204, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        mocked_mt5.order_send.assert_not_called()

    def test_close_returns_fail_when_position_not_found(self, mocked_mt5):
        """positions_get returns [] for ticket → MT5_TICKET_NOT_FOUND."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import close
        result = close(999, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_TICKET_NOT_FOUND"

    def test_close_returns_fail_when_order_send_rejected(self, mocked_mt5):
        """Broker rejects close → fail(MT5_ORDER_REJECTED)."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=205, pos_type=0, volume=0.1)
        mocked_mt5.positions_get.return_value = [pos]
        bad_result = _make_send_result(retcode=10006)
        bad_result.comment = "Broker rejected"
        mocked_mt5.order_send.return_value = bad_result
        from mt5_universal.positions.positions import close
        result = close(205, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_ORDER_REJECTED"

    def test_close_buy_uses_bid_price(self, mocked_mt5):
        """Closing a BUY uses bid (opposing sell price)."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.symbol_info_tick.return_value = _tick(bid=1.1000, ask=1.1005)
        pos = _make_position(ticket=206, pos_type=0, volume=0.1)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close
        close(206, is_live_intent=False)
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["price"] == 1.1000  # bid for BUY close


# ---------------------------------------------------------------------------
# close_all tests
# ---------------------------------------------------------------------------

class TestCloseAll:

    def test_close_all_calls_close_per_position(self, mocked_mt5):
        """close_all closes each position and returns a result per ticket."""
        _setup_happy_path(mocked_mt5)
        pos1 = _make_position(ticket=300, pos_type=0, volume=0.1, profit=10.0)
        pos2 = _make_position(ticket=301, pos_type=1, volume=0.2, profit=-5.0)
        mocked_mt5.positions_get.return_value = [pos1, pos2]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import close_all
        result = close_all(is_live_intent=False)
        assert result["ok"] is True
        assert len(result["data"]) == 2
        tickets = {entry["ticket"] for entry in result["data"]}
        assert tickets == {300, 301}

    def test_close_all_filters_by_symbol(self, mocked_mt5):
        """close_all(symbol='EURUSD') passes symbol kwarg to positions_get."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import close_all
        close_all(symbol="EURUSD", is_live_intent=False)
        # First call is the positions_get in close_all itself
        mocked_mt5.positions_get.assert_any_call(symbol="EURUSD")

    def test_close_all_continues_on_per_ticket_failure(self, mocked_mt5):
        """Fail-soft: if first close fails, second still runs."""
        _setup_happy_path(mocked_mt5)
        pos1 = _make_position(ticket=302, pos_type=0, volume=0.1, profit=0.0)
        pos2 = _make_position(ticket=303, pos_type=0, volume=0.1, profit=5.0)
        # Return both positions at first call, then per-ticket closes need
        # the individual position too.
        fail_result = _make_send_result(retcode=10006)
        fail_result.comment = "rejected"
        success_result = _make_send_result(retcode=10009)

        def positions_get_side_effect(**kwargs):
            ticket = kwargs.get("ticket")
            if ticket == 302:
                return [pos1]
            if ticket == 303:
                return [pos2]
            # No filter → return all (first close_all call)
            return [pos1, pos2]

        mocked_mt5.positions_get.side_effect = positions_get_side_effect
        mocked_mt5.order_send.side_effect = [fail_result, success_result]

        from mt5_universal.positions.positions import close_all
        result = close_all(is_live_intent=False)
        assert result["ok"] is True
        assert len(result["data"]) == 2
        results_by_ticket = {entry["ticket"]: entry for entry in result["data"]}
        assert results_by_ticket[302]["result"] == "error"
        assert results_by_ticket[303]["result"] == "closed"

    def test_close_all_empty_returns_empty_list(self, mocked_mt5):
        """No open positions → ok with empty data list."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import close_all
        result = close_all(is_live_intent=False)
        assert result["ok"] is True
        assert result["data"] == []

    def test_close_all_blocked_on_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)
        from mt5_universal.positions.positions import close_all
        result = close_all(is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"


# ---------------------------------------------------------------------------
# move_sl tests
# ---------------------------------------------------------------------------

class TestMoveSl:

    def test_move_sl_sends_TRADE_ACTION_SLTP_with_position_ticket(self, mocked_mt5):
        """move_sl sends action=TRADE_ACTION_SLTP with position=ticket."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=400, pos_type=0, sl=1.0900, tp=1.1200)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import move_sl
        result = move_sl(400, sl=1.0950, is_live_intent=False)
        assert result["ok"] is True
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["action"] == 6     # TRADE_ACTION_SLTP
        assert req["position"] == 400
        assert req["sl"] == 1.0950

    def test_move_sl_preserves_tp(self, mocked_mt5):
        """move_sl does not clobber the existing TP."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=401, pos_type=0, sl=1.0900, tp=1.1200)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import move_sl
        move_sl(401, sl=1.0950, is_live_intent=False)
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["tp"] == 1.1200   # preserved from position

    def test_move_sl_returns_fail_when_position_not_found(self, mocked_mt5):
        """positions_get returns [] for ticket → MT5_TICKET_NOT_FOUND."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import move_sl
        result = move_sl(999, sl=1.0950, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_TICKET_NOT_FOUND"

    def test_move_sl_blocked_on_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)
        from mt5_universal.positions.positions import move_sl
        result = move_sl(400, sl=1.0950, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"

    def test_move_sl_returns_sl_moved_on_success(self, mocked_mt5):
        """Successful move_sl returns result='sl_moved'."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=402, pos_type=0, sl=1.0900, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import move_sl
        result = move_sl(402, sl=1.0950, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["result"] == "sl_moved"
        assert result["data"]["ticket"] == 402


# ---------------------------------------------------------------------------
# breakeven tests
# ---------------------------------------------------------------------------

class TestBreakeven:

    def test_breakeven_buy_sets_sl_to_open_plus_buffer(self, mocked_mt5):
        """BUY position: new_sl = open_price + buffer_points * point."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=500, pos_type=0, price_open=1.1000, sl=1.0900, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import breakeven
        result = breakeven(500, buffer_points=10, is_live_intent=False)
        assert result["ok"] is True
        expected_sl = 1.1000 + 10 * 0.00001
        assert abs(result["data"]["sl_set_to"] - expected_sl) < 1e-9
        req = mocked_mt5.order_send.call_args[0][0]
        assert abs(req["sl"] - expected_sl) < 1e-9

    def test_breakeven_sell_sets_sl_to_open_minus_buffer(self, mocked_mt5):
        """SELL position: new_sl = open_price - buffer_points * point."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=501, pos_type=1, price_open=1.1000, sl=1.1100, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import breakeven
        result = breakeven(501, buffer_points=10, is_live_intent=False)
        assert result["ok"] is True
        expected_sl = 1.1000 - 10 * 0.00001
        assert abs(result["data"]["sl_set_to"] - expected_sl) < 1e-9
        req = mocked_mt5.order_send.call_args[0][0]
        assert abs(req["sl"] - expected_sl) < 1e-9

    def test_breakeven_zero_buffer_uses_open_price_exactly(self, mocked_mt5):
        """buffer_points=0 → SL set exactly to open_price for both BUY and SELL."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=502, pos_type=0, price_open=1.2345, sl=1.2200, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import breakeven
        result = breakeven(502, buffer_points=0, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["sl_set_to"] == 1.2345
        req = mocked_mt5.order_send.call_args[0][0]
        assert req["sl"] == 1.2345

    def test_breakeven_returns_fail_when_position_not_found(self, mocked_mt5):
        """positions_get returns [] for ticket → MT5_TICKET_NOT_FOUND."""
        _setup_happy_path(mocked_mt5)
        mocked_mt5.positions_get.return_value = []
        from mt5_universal.positions.positions import breakeven
        result = breakeven(999, buffer_points=5, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_TICKET_NOT_FOUND"

    def test_breakeven_returns_breakeven_set_result(self, mocked_mt5):
        """Successful breakeven returns result='breakeven_set' with sl_set_to."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=503, pos_type=0, price_open=1.1000, sl=1.0900, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)
        mocked_mt5.order_send.return_value = _make_send_result(retcode=10009)
        from mt5_universal.positions.positions import breakeven
        result = breakeven(503, buffer_points=5, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["result"] == "breakeven_set"
        assert "sl_set_to" in result["data"]
        assert result["data"]["ticket"] == 503

    def test_breakeven_blocked_on_real_account(self, mocked_mt5):
        """is_live_intent=False on REAL account → RISK_LIVE_GATE_BLOCKED."""
        mocked_mt5.account_info.return_value = _acct(trade_mode=2)
        from mt5_universal.positions.positions import breakeven
        result = breakeven(500, buffer_points=5, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"

    def test_breakeven_propagates_move_sl_failure(self, mocked_mt5):
        """If the underlying SLTP order_send fails, breakeven propagates the fail."""
        _setup_happy_path(mocked_mt5)
        pos = _make_position(ticket=504, pos_type=0, price_open=1.1000, sl=1.0900, tp=0.0)
        mocked_mt5.positions_get.return_value = [pos]
        mocked_mt5.symbol_info.return_value = _sym_info(point=0.00001)
        bad_result = _make_send_result(retcode=10006)
        bad_result.comment = "Rejected"
        mocked_mt5.order_send.return_value = bad_result
        from mt5_universal.positions.positions import breakeven
        result = breakeven(504, buffer_points=5, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_ORDER_REJECTED"
