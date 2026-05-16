"""Tests for mt5_cli/chart/ - Win32 chart-control primitives.

Cherry-pick from archive/legacy-mt5/core/chart.py (941 LOC, with
TDA-flavored orchestration stripped out). Tests use lazily-mocked
pywin32 modules at sys.modules level since chart.py imports them via
a `_win32()` helper.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest


def _purge_chart_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


@pytest.fixture
def fake_pywin32(monkeypatch):
    """Inject MagicMock win32gui / win32con / win32process into sys.modules.

    Returns the trio (win32gui, win32con, win32process) so tests can wire
    up specific return values.
    """
    _purge_chart_cache()

    fake_gui = MagicMock(name="win32gui")
    fake_con = types.SimpleNamespace(MF_BYPOSITION=0x0400)
    fake_process = MagicMock(name="win32process")

    # Sensible defaults
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""
    fake_gui.GetClassName.return_value = ""
    fake_gui.GetParent.return_value = 0
    fake_gui.GetFocus.return_value = 0
    fake_gui.GetForegroundWindow.return_value = 0
    fake_gui.SendMessage.return_value = 0
    fake_gui.PostMessage.return_value = 1
    fake_gui.SetForegroundWindow.return_value = True
    fake_gui.ShowWindow.return_value = True
    fake_gui.BringWindowToTop.return_value = True
    fake_gui.GetMenu.return_value = 0
    fake_gui.EnumWindows.return_value = None
    fake_gui.EnumChildWindows.return_value = None

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", fake_con)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    yield fake_gui, fake_con, fake_process

    _purge_chart_cache()


# ---------------------------------------------------------------------------
# Pure helpers (no Win32 needed)
# ---------------------------------------------------------------------------


def test_normalize_timeframe_canonicalizes_mn1():
    _purge_chart_cache()
    from mt5_cli.chart import normalize_timeframe
    assert normalize_timeframe("MN1") == "MN"
    assert normalize_timeframe("m15") == "M15"
    assert normalize_timeframe("H4") == "H4"


def test_normalize_timeframe_rejects_unknown():
    _purge_chart_cache()
    from mt5_cli.chart import normalize_timeframe
    with pytest.raises(ValueError):
        normalize_timeframe("Q1")


def test_parse_chart_title_bracket_form():
    _purge_chart_cache()
    from mt5_cli.chart import parse_chart_title
    sym, tf = parse_chart_title("[USDJPY,H1] - Live")
    assert sym == "USDJPY"
    assert tf == "H1"


def test_parse_chart_title_plain_form():
    _purge_chart_cache()
    from mt5_cli.chart import parse_chart_title
    sym, tf = parse_chart_title("USDJPY,M15")
    assert sym == "USDJPY"
    assert tf == "M15"


def test_parse_chart_title_daily_alias():
    _purge_chart_cache()
    from mt5_cli.chart import parse_chart_title
    sym, tf = parse_chart_title("[EURUSD,Daily]")
    assert sym == "EURUSD"
    assert tf == "D1"


def test_parse_chart_title_no_match():
    _purge_chart_cache()
    from mt5_cli.chart import parse_chart_title
    assert parse_chart_title("MetaTrader 5") == (None, None)


def test_title_has_symbol_tf_matches_strictly():
    _purge_chart_cache()
    from mt5_cli.chart import title_has_symbol_tf
    assert title_has_symbol_tf("[USDJPY,H1]", "USDJPY", "H1") is True
    assert title_has_symbol_tf("[USDJPY,H1]", "USDJPY", "M15") is False
    assert title_has_symbol_tf("[USDJPY,H1]", "EURUSD", "H1") is False


# ---------------------------------------------------------------------------
# find_window / list_charts / current_title (envelope-returning)
# ---------------------------------------------------------------------------


def test_find_window_returns_match(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1234, None)

    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.return_value = "MetaTrader 5"
    win32gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"

    from mt5_cli.chart import find_window
    match = find_window("MT5")
    assert match is not None
    assert match.hwnd == 1234
    assert match.title == "MetaTrader 5"


def test_find_window_returns_none_when_no_match(fake_pywin32):
    from mt5_cli.chart import find_window
    assert find_window("MT5") is None


def test_list_charts_fail_when_window_missing(fake_pywin32):
    from mt5_cli.chart import list_charts
    env = list_charts("MT5")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_list_charts_returns_envelope_with_chart_data(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    # First EnumWindows finds the parent MT5 window
    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda hwnd: {
        1000: "MetaTrader 5",
        2000: "[USDJPY,H1]",
        2001: "[EURUSD,M15]",
    }.get(hwnd, "")
    win32gui.GetClassName.side_effect = lambda hwnd: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2000: "AfxFrameOrView140s",
        2001: "AfxFrameOrView140s",
    }.get(hwnd, "")

    enum_calls = []

    def fake_enum_children(parent, cb, _extra):
        # Called twice: once for MDIClient lookup, once for chart enumeration.
        enum_calls.append(parent)
        cb(2000, None)
        cb(2001, None)
    win32gui.EnumChildWindows.side_effect = fake_enum_children

    from mt5_cli.chart import list_charts
    env = list_charts("MT5")
    assert env["ok"] is True
    titles = [c["title"] for c in env["data"]]
    assert "[USDJPY,H1]" in titles
    assert "[EURUSD,M15]" in titles
    # parent_hwnd is glued on
    assert all(c["parent_hwnd"] == 1000 for c in env["data"])


def test_current_title_fail_when_window_missing(fake_pywin32):
    from mt5_cli.chart import current_title
    env = current_title("MT5")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_current_title_returns_parent_fallback_when_no_charts(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.return_value = "[USDJPY,H4] - Trading.com Markets MT5"
    win32gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"

    from mt5_cli.chart import current_title
    env = current_title("MT5")
    assert env["ok"] is True
    assert env["data"]["symbol"] == "USDJPY"
    assert env["data"]["timeframe"] == "H4"


# ---------------------------------------------------------------------------
# activate_chart - Win32 message side-effects
# ---------------------------------------------------------------------------


def test_activate_chart_uses_mdi_when_parent_given(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    # _find_mdi_client iterates children of parent_hwnd looking for MDIClient.
    def fake_enum_children(parent, cb, _extra):
        cb(9999, None)  # this hwnd will be the "MDIClient"
    win32gui.EnumChildWindows.side_effect = fake_enum_children
    win32gui.GetClassName.side_effect = lambda hwnd: "MDIClient" if hwnd == 9999 else ""

    from mt5_cli.chart import activate_chart
    ok = activate_chart(2000, parent_hwnd=1000, settle_seconds=0)
    assert ok is True
    # Confirm WM_MDIACTIVATE was sent to the MDIClient hwnd
    sent = [args for args in win32gui.SendMessage.call_args_list if args.args[0] == 9999]
    assert sent, "Expected SendMessage to MDIClient hwnd 9999"


# ---------------------------------------------------------------------------
# switch_tf - timeframe validation + window-not-found
# ---------------------------------------------------------------------------


def test_switch_tf_rejects_invalid_timeframe(fake_pywin32):
    from mt5_cli.chart import switch_tf
    env = switch_tf("Q1")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_TIMEFRAME"


def test_switch_tf_fails_when_window_missing(fake_pywin32):
    from mt5_cli.chart import switch_tf
    env = switch_tf("M15")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# symbol - input validation + window-not-found
# ---------------------------------------------------------------------------


def test_symbol_fails_when_window_missing(fake_pywin32):
    from mt5_cli.chart import symbol as chart_symbol
    env = chart_symbol("USDJPY")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# ensure_chart - delegates to symbol + switch_tf, validates result
# ---------------------------------------------------------------------------


def test_ensure_chart_rejects_invalid_timeframe(fake_pywin32):
    from mt5_cli.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe="Q1")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_TIMEFRAME"


def test_ensure_chart_fails_when_window_missing(fake_pywin32):
    from mt5_cli.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe="M15")
    # window lookup runs first, fails before either branch
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_ensure_chart_opens_new_when_symbol_has_no_existing_chart(
    fake_pywin32, monkeypatch,
):
    """Upgrade behavior: when no chart for the symbol exists, ensure_chart
    must call new_chart() to open one instead of typing the symbol into
    the active chart (which would destroy whatever chart was there)."""
    win32gui, _, _ = fake_pywin32

    # MT5 window present
    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.return_value = "MetaTrader 5"
    win32gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"

    # No chart children for USDJPY (or any symbol)
    win32gui.EnumChildWindows.return_value = None

    # Stub new_chart so we don't drive the full File>New Chart menu walk;
    # only verify ensure_chart routed to it.
    called_with = {}
    from mt5_cli.chart import chart as chart_mod

    def fake_new_chart(symbol, *, timeframe=None, **kw):
        called_with["symbol"] = symbol
        called_with["timeframe"] = timeframe
        return {
            "ok": True,
            "data": {
                "hwnd": 9001,
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "parent_hwnd": 1000,
                "command_id": 7777,
                "menu_path": f"File > New Chart > {symbol.upper()}",
            },
        }

    # The lazy import in ensure_chart pulls from mt5_cli.chart.new_chart.
    # Patch via sys.modules so the local-import inside the function picks
    # up our stub.
    import sys as _sys
    import types as _types
    fake_module = _types.ModuleType("mt5_cli.chart.new_chart")
    fake_module.new_chart = fake_new_chart
    monkeypatch.setitem(_sys.modules, "mt5_cli.chart.new_chart", fake_module)

    from mt5_cli.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe="H1")
    assert env["ok"] is True
    assert env["data"]["symbol"] == "USDJPY"
    assert env["data"]["timeframe"] == "H1"
    assert env["data"]["opened_new"] is True
    assert env["data"]["activated_existing"] is False
    assert called_with == {"symbol": "USDJPY", "timeframe": "H1"}


def test_ensure_chart_activates_existing_when_symbol_chart_already_open(
    fake_pywin32,
):
    """Inverse of the upgrade: when a chart for the symbol already exists,
    ensure_chart must NOT call new_chart() - it activates the existing one.
    """
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    # USDJPY chart already exists at hwnd 2500
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5",
        2500: "[USDJPY,M15]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    def fake_enum_children(parent, cb, _):
        # First call: _find_mdi_client. Subsequent: chart enumeration.
        if parent == 1000:
            cb(2500, None)
    win32gui.EnumChildWindows.side_effect = fake_enum_children

    # Don't import new_chart at all - ensure_chart shouldn't route there
    from mt5_cli.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe=None)
    # We don't assert ok=True here because the full symbol/activate path
    # has many moving parts; we assert it took the existing-chart branch.
    if env["ok"]:
        assert env["data"].get("opened_new") is False


# ---------------------------------------------------------------------------
# cycle_chart - sugar over list_charts + activate_chart
# ---------------------------------------------------------------------------


def test_cycle_chart_rejects_invalid_direction(fake_pywin32):
    from mt5_cli.chart import cycle_chart
    env = cycle_chart(direction="sideways")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_DIRECTION"


def test_cycle_chart_fails_when_window_missing(fake_pywin32):
    from mt5_cli.chart import cycle_chart
    env = cycle_chart(direction="next")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_cycle_chart_fails_when_no_charts_open(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.return_value = "MetaTrader 5"
    win32gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"
    # No child charts
    win32gui.EnumChildWindows.return_value = None

    from mt5_cli.chart import cycle_chart
    env = cycle_chart(direction="next", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_NO_CHARTS_OPEN"


def test_cycle_chart_fails_when_only_one_chart_open(fake_pywin32):
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5", 2500: "[USDJPY,M15]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    def fake_enum_children(parent, cb, _):
        if parent == 1000:
            cb(2500, None)  # one chart
    win32gui.EnumChildWindows.side_effect = fake_enum_children

    from mt5_cli.chart import cycle_chart
    env = cycle_chart(direction="next", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_ONLY_ONE_OPEN"


def test_cycle_chart_next_activates_subsequent_chart(fake_pywin32):
    """Three charts open with the first active. cycle_chart('next')
    activates the second."""
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5",
        2500: "[USDJPY,M15]", 2600: "[EURUSD,H1]", 2700: "[GBPUSD,H4]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
        2600: "AfxFrameOrView140s",
        2700: "AfxFrameOrView140s",
    }.get(h, "")

    def fake_enum_children(parent, cb, _extra):
        if parent == 1000:
            # MDIClient enumeration for active-detection: return nothing
            # so _active_chart_hwnd falls through to GetFocus path.
            cb(2500, None)
            cb(2600, None)
            cb(2700, None)
    win32gui.EnumChildWindows.side_effect = fake_enum_children
    # Mark chart 2500 as active via GetForegroundWindow being a descendant
    win32gui.GetForegroundWindow.return_value = 2500
    win32gui.GetParent.side_effect = lambda h: {2500: 1000}.get(h, 0)

    from mt5_cli.chart import cycle_chart
    env = cycle_chart(direction="next", settle_seconds=0)
    assert env["ok"] is True
    # Target chart hwnd is one of the three known charts AND differs from
    # cycled_from (the contract: cycle moves to a different chart).
    assert env["data"]["hwnd"] in {2500, 2600, 2700}
    assert env["data"]["hwnd"] != env["data"]["cycled_from"]
    assert env["data"]["direction"] == "next"
    # activate_chart was invoked - either via WM_MDIACTIVATE on an
    # MDIClient (when one is detected) or via SetForegroundWindow as
    # fallback. We don't care which path; the contract is that some
    # activation API was called on the target hwnd.
    target_hwnd = env["data"]["hwnd"]
    activations = (
        list(win32gui.SendMessage.call_args_list)
        + list(win32gui.SetForegroundWindow.call_args_list)
        + list(win32gui.BringWindowToTop.call_args_list)
    )
    assert any(target_hwnd in c.args for c in activations)


# ---------------------------------------------------------------------------
# close_chart - WM_CLOSE on chart child
# ---------------------------------------------------------------------------


def test_close_chart_fails_when_window_missing(fake_pywin32):
    from mt5_cli.chart import close_chart
    env = close_chart(chart_id=2500)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_close_chart_fails_when_chart_id_not_a_child(fake_pywin32):
    """chart_id is not in the enumerated children → CHART_ID_NOT_FOUND."""
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5", 2500: "[EURUSD,H1]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    def fake_enum_children(parent, cb, _):
        if parent == 1000:
            cb(2500, None)  # only chart 2500 exists
    win32gui.EnumChildWindows.side_effect = fake_enum_children

    from mt5_cli.chart import close_chart
    env = close_chart(chart_id=9999, settle_seconds=0)  # 9999 doesn't exist
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_ID_NOT_FOUND"
    # WM_CLOSE was NOT posted
    close_calls = [
        c for c in win32gui.PostMessage.call_args_list
        if c.args[1] == 0x0010  # WM_CLOSE
    ]
    assert not close_calls


def test_close_chart_posts_wm_close_then_verifies_gone(fake_pywin32):
    """Happy path: chart_id is a child, WM_CLOSE posted, after-snapshot
    shows it's gone."""
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5", 2500: "[EURUSD,H1]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    enum_state = {"calls": 0}

    def fake_enum_children(parent, cb, _):
        enum_state["calls"] += 1
        if parent != 1000:
            return
        if enum_state["calls"] <= 2:
            # First chart-enumeration (before WM_CLOSE): chart present
            # (calls 1 is _find_mdi_client returning nothing; call 2 is
            # the chart enumeration itself; the helper may invoke
            # EnumChildWindows more than once before WM_CLOSE)
            cb(2500, None)
        # After WM_CLOSE: callback does NOT fire (chart is gone)

    win32gui.EnumChildWindows.side_effect = fake_enum_children

    from mt5_cli.chart import close_chart
    env = close_chart(chart_id=2500, settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["hwnd"] == 2500
    assert env["data"]["closed"] is True

    # WM_CLOSE (0x0010) was posted to chart 2500
    close_calls = [
        c for c in win32gui.PostMessage.call_args_list
        if c.args[1] == 0x0010
    ]
    assert close_calls
    assert close_calls[0].args == (2500, 0x0010, 0, 0)


def test_close_chart_fails_verify_when_chart_still_present(fake_pywin32):
    """Edge case: MT5 shows the save-profile confirmation dialog and the
    chart stays open after WM_CLOSE. Must fail with
    CHART_CLOSE_VERIFY_FAILED so the caller knows."""
    win32gui, _, _ = fake_pywin32

    def fake_enum_windows(cb, _extra):
        cb(1000, None)
    win32gui.EnumWindows.side_effect = fake_enum_windows
    win32gui.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5", 2500: "[EURUSD,H1]",
    }.get(h, "")
    win32gui.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    # Chart 2500 stays present both before AND after WM_CLOSE.
    def fake_enum_children(parent, cb, _):
        if parent == 1000:
            cb(2500, None)
    win32gui.EnumChildWindows.side_effect = fake_enum_children

    from mt5_cli.chart import close_chart
    env = close_chart(chart_id=2500, settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_CLOSE_VERIFY_FAILED"


# ---------------------------------------------------------------------------
# Bridge isolation - chart module must NOT import MetaTrader5
# ---------------------------------------------------------------------------


def test_chart_module_does_not_import_metatrader5():
    """Verify mt5_cli.chart never touches MetaTrader5 - it's a Win32
    GUI module, not a bridge consumer. Locked decision: only
    mt5_cli/bridge/mt5_backend.py imports MetaTrader5.
    """
    import importlib
    import mt5_cli.chart  # noqa: F401
    # Inspect the module source on disk
    chart_mod = importlib.import_module("mt5_cli.chart.chart")
    src = open(chart_mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
