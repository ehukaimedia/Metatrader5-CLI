"""Tests for mt5_universal/chart/ - Win32 chart-control primitives.

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
        if name.startswith("mt5_universal.chart"):
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
    from mt5_universal.chart import normalize_timeframe
    assert normalize_timeframe("MN1") == "MN"
    assert normalize_timeframe("m15") == "M15"
    assert normalize_timeframe("H4") == "H4"


def test_normalize_timeframe_rejects_unknown():
    _purge_chart_cache()
    from mt5_universal.chart import normalize_timeframe
    with pytest.raises(ValueError):
        normalize_timeframe("Q1")


def test_parse_chart_title_bracket_form():
    _purge_chart_cache()
    from mt5_universal.chart import parse_chart_title
    sym, tf = parse_chart_title("[USDJPY,H1] - Live")
    assert sym == "USDJPY"
    assert tf == "H1"


def test_parse_chart_title_plain_form():
    _purge_chart_cache()
    from mt5_universal.chart import parse_chart_title
    sym, tf = parse_chart_title("USDJPY,M15")
    assert sym == "USDJPY"
    assert tf == "M15"


def test_parse_chart_title_daily_alias():
    _purge_chart_cache()
    from mt5_universal.chart import parse_chart_title
    sym, tf = parse_chart_title("[EURUSD,Daily]")
    assert sym == "EURUSD"
    assert tf == "D1"


def test_parse_chart_title_no_match():
    _purge_chart_cache()
    from mt5_universal.chart import parse_chart_title
    assert parse_chart_title("MetaTrader 5") == (None, None)


def test_title_has_symbol_tf_matches_strictly():
    _purge_chart_cache()
    from mt5_universal.chart import title_has_symbol_tf
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

    from mt5_universal.chart import find_window
    match = find_window("MT5")
    assert match is not None
    assert match.hwnd == 1234
    assert match.title == "MetaTrader 5"


def test_find_window_returns_none_when_no_match(fake_pywin32):
    from mt5_universal.chart import find_window
    assert find_window("MT5") is None


def test_list_charts_fail_when_window_missing(fake_pywin32):
    from mt5_universal.chart import list_charts
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

    from mt5_universal.chart import list_charts
    env = list_charts("MT5")
    assert env["ok"] is True
    titles = [c["title"] for c in env["data"]]
    assert "[USDJPY,H1]" in titles
    assert "[EURUSD,M15]" in titles
    # parent_hwnd is glued on
    assert all(c["parent_hwnd"] == 1000 for c in env["data"])


def test_current_title_fail_when_window_missing(fake_pywin32):
    from mt5_universal.chart import current_title
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

    from mt5_universal.chart import current_title
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

    from mt5_universal.chart import activate_chart
    ok = activate_chart(2000, parent_hwnd=1000, settle_seconds=0)
    assert ok is True
    # Confirm WM_MDIACTIVATE was sent to the MDIClient hwnd
    sent = [args for args in win32gui.SendMessage.call_args_list if args.args[0] == 9999]
    assert sent, "Expected SendMessage to MDIClient hwnd 9999"


# ---------------------------------------------------------------------------
# switch_tf - timeframe validation + window-not-found
# ---------------------------------------------------------------------------


def test_switch_tf_rejects_invalid_timeframe(fake_pywin32):
    from mt5_universal.chart import switch_tf
    env = switch_tf("Q1")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_TIMEFRAME"


def test_switch_tf_fails_when_window_missing(fake_pywin32):
    from mt5_universal.chart import switch_tf
    env = switch_tf("M15")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# symbol - input validation + window-not-found
# ---------------------------------------------------------------------------


def test_symbol_fails_when_window_missing(fake_pywin32):
    from mt5_universal.chart import symbol as chart_symbol
    env = chart_symbol("USDJPY")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# ensure_chart - delegates to symbol + switch_tf, validates result
# ---------------------------------------------------------------------------


def test_ensure_chart_rejects_invalid_timeframe(fake_pywin32):
    from mt5_universal.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe="Q1")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_TIMEFRAME"


def test_ensure_chart_fails_when_window_missing(fake_pywin32):
    from mt5_universal.chart import ensure_chart
    env = ensure_chart("USDJPY", timeframe="M15")
    # symbol() runs first, fails on missing window
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# Bridge isolation - chart module must NOT import MetaTrader5
# ---------------------------------------------------------------------------


def test_chart_module_does_not_import_metatrader5():
    """Verify mt5_universal.chart never touches MetaTrader5 - it's a Win32
    GUI module, not a bridge consumer. Locked decision: only
    mt5_universal/bridge/mt5_backend.py imports MetaTrader5.
    """
    import importlib
    import mt5_universal.chart  # noqa: F401
    # Inspect the module source on disk
    chart_mod = importlib.import_module("mt5_universal.chart.chart")
    src = open(chart_mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
