"""Tests for mt5_universal/screenshot/ - mss-based capture primitives.

Cherry-pick from archive/legacy-mt5/core/screenshot.py with TDA
orchestration stripped. mss / pygetwindow / PIL are mocked at
sys.modules level so tests do not require a display or those packages
being installed on a CI runner.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _purge_screenshot_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_universal.screenshot"):
            sys.modules.pop(name, None)


@pytest.fixture
def fake_capture_deps(monkeypatch):
    """Inject mss / pygetwindow / win32gui mocks at sys.modules level."""
    _purge_screenshot_cache()

    fake_mss_pkg = types.ModuleType("mss")
    fake_mss_ctx = MagicMock(name="mss_context")
    fake_mss_ctx.monitors = [
        {"left": 0, "top": 0, "width": 1920, "height": 1080},  # all-monitors
        {"left": 0, "top": 0, "width": 1920, "height": 1080},  # primary
    ]
    fake_grab = MagicMock()
    fake_grab.rgb = b"x" * (10 * 10 * 3)
    fake_grab.size = (10, 10)
    fake_grab.width = 10
    fake_grab.height = 10
    fake_mss_ctx.grab.return_value = fake_grab

    fake_mss_class = MagicMock(name="mss_class")
    fake_mss_class.return_value.__enter__.return_value = fake_mss_ctx
    fake_mss_class.return_value.__exit__.return_value = False
    fake_mss_pkg.mss = fake_mss_class

    fake_mss_tools = types.ModuleType("mss.tools")
    fake_mss_tools.to_png = MagicMock(return_value=None)
    fake_mss_pkg.tools = fake_mss_tools

    fake_pygetwindow = types.ModuleType("pygetwindow")
    fake_pygetwindow.getAllWindows = MagicMock(return_value=[])
    fake_pygetwindow.getWindowsWithTitle = MagicMock(return_value=[])

    fake_win32gui = MagicMock(name="win32gui_screenshot")
    fake_win32gui.GetClassName.return_value = ""

    monkeypatch.setitem(sys.modules, "mss", fake_mss_pkg)
    monkeypatch.setitem(sys.modules, "mss.tools", fake_mss_tools)
    monkeypatch.setitem(sys.modules, "pygetwindow", fake_pygetwindow)
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32gui)

    yield {
        "mss_ctx": fake_mss_ctx,
        "mss_tools": fake_mss_tools,
        "pygetwindow": fake_pygetwindow,
        "win32gui": fake_win32gui,
    }

    _purge_screenshot_cache()


# ---------------------------------------------------------------------------
# Pure resolvers
# ---------------------------------------------------------------------------


def test_resolve_dir_falls_back_to_temp_when_no_directory_or_cfg():
    _purge_screenshot_cache()
    from mt5_universal.screenshot.screenshot import _resolve_dir
    result = _resolve_dir(None, None)
    # Should land under the system temp dir
    assert "mt5-cli" in str(result) and "screenshots" in str(result)


def test_resolve_dir_honors_explicit_directory(tmp_path):
    _purge_screenshot_cache()
    from mt5_universal.screenshot.screenshot import _resolve_dir
    result = _resolve_dir(str(tmp_path / "shots"), None)
    assert result == Path(str(tmp_path / "shots"))


def test_resolve_dir_reads_cfg_screenshot_output_dir(tmp_path):
    _purge_screenshot_cache()
    from mt5_universal.screenshot.screenshot import _resolve_dir
    cfg = {"screenshot_output_dir": str(tmp_path / "from_cfg")}
    result = _resolve_dir(None, cfg)
    assert result == Path(str(tmp_path / "from_cfg"))


def test_resolve_monitor_defaults_to_zero():
    _purge_screenshot_cache()
    from mt5_universal.screenshot.screenshot import _resolve_monitor
    assert _resolve_monitor(None, None) == 0
    assert _resolve_monitor(None, {"screenshot_monitor": 2}) == 2
    assert _resolve_monitor(3, None) == 3


# ---------------------------------------------------------------------------
# take()
# ---------------------------------------------------------------------------


def test_take_fails_closed_when_window_substring_not_found(fake_capture_deps, tmp_path):
    from mt5_universal.screenshot import take
    out = str(tmp_path / "shot.png")
    env = take(output_path=out, window_substring="MT5")
    assert env["ok"] is False
    assert env["error"]["code"] == "SCREENSHOT_WINDOW_NOT_FOUND"


def test_take_captures_monitor_when_window_substring_empty(fake_capture_deps, tmp_path):
    """With window_substring='', take() falls through to full-monitor capture."""
    from mt5_universal.screenshot import take
    out = str(tmp_path / "shot.png")
    env = take(output_path=out, window_substring="")
    assert env["ok"] is True
    assert env["data"]["path"] == out
    assert env["data"]["window_matched"] is False
    fake_capture_deps["mss_tools"].to_png.assert_called_once()


def test_take_captures_window_bounds_when_pygetwindow_matches(fake_capture_deps, tmp_path):
    fake_win = MagicMock(title="MetaTrader 5", left=100, top=50, width=800, height=600)
    fake_win._hWnd = 12345
    fake_capture_deps["pygetwindow"].getAllWindows.return_value = [fake_win]
    fake_capture_deps["win32gui"].GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"

    from mt5_universal.screenshot import take
    out = str(tmp_path / "shot.png")
    env = take(output_path=out, window_substring="MT5")
    assert env["ok"] is True
    assert env["data"]["window_matched"] is True
    # mss.grab() called with the window region (a dict, not a monitor entry)
    call_args = fake_capture_deps["mss_ctx"].grab.call_args
    region = call_args.args[0]
    assert region == {"left": 100, "top": 50, "width": 800, "height": 600}


def test_take_auto_generates_timestamped_path_when_output_none(fake_capture_deps, tmp_path):
    cfg = {"screenshot_output_dir": str(tmp_path)}
    from mt5_universal.screenshot import take
    env = take(window_substring="", cfg=cfg)
    assert env["ok"] is True
    assert env["data"]["path"].startswith(str(tmp_path))
    assert env["data"]["path"].endswith(".png")


# ---------------------------------------------------------------------------
# annotate()
# ---------------------------------------------------------------------------


def test_annotate_writes_text_overlay(fake_capture_deps, tmp_path, monkeypatch):
    fake_pil = types.ModuleType("PIL")
    fake_image_module = types.ModuleType("PIL.Image")
    fake_draw_module = types.ModuleType("PIL.ImageDraw")
    fake_image_instance = MagicMock(name="image")
    fake_image_module.open = MagicMock(return_value=fake_image_instance)
    fake_draw_instance = MagicMock(name="draw")
    fake_draw_module.Draw = MagicMock(return_value=fake_draw_instance)
    fake_pil.Image = fake_image_module
    fake_pil.ImageDraw = fake_draw_module
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image_module)
    monkeypatch.setitem(sys.modules, "PIL.ImageDraw", fake_draw_module)

    from mt5_universal.screenshot import annotate
    out = str(tmp_path / "out.png")
    env = annotate(input_path=str(tmp_path / "in.png"), output_path=out, text="hello")
    assert env["ok"] is True
    assert env["data"]["path"] == out
    fake_draw_instance.text.assert_called_once_with((10, 10), "hello", fill="white")
    fake_image_instance.save.assert_called_once_with(out)


# ---------------------------------------------------------------------------
# dom() smoke - exercise the open_panel=False path so we skip menu poking
# ---------------------------------------------------------------------------


def test_dom_with_panels_disabled_still_captures(fake_capture_deps, tmp_path):
    """open_panel=False + close_panel=False should just capture the active
    window (whatever it is). Useful for tests + agents that already have
    the DOM panel open via mt5 DOM commands.
    """
    fake_win = MagicMock(title="[USDJPY,M15] - Trading.com", left=0, top=0, width=400, height=300)
    fake_win._hWnd = 555
    fake_capture_deps["pygetwindow"].getAllWindows.return_value = [fake_win]
    fake_capture_deps["win32gui"].GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"

    # Make PIL postprocess succeed
    fake_pil = types.ModuleType("PIL")
    fake_image_module = types.ModuleType("PIL.Image")
    fake_image_instance = MagicMock(name="image")
    fake_image_instance.width = 400
    fake_image_instance.height = 300
    fake_image_instance.convert.return_value = fake_image_instance
    fake_image_instance.crop.return_value = fake_image_instance
    fake_image_instance.resize.return_value = fake_image_instance
    fake_image_instance.__enter__ = lambda self: fake_image_instance
    fake_image_instance.__exit__ = lambda self, *a: False
    fake_image_module.open = MagicMock(return_value=fake_image_instance)
    fake_pil.Image = fake_image_module

    import unittest.mock as um
    with um.patch.dict(sys.modules, {"PIL": fake_pil, "PIL.Image": fake_image_module}):
        from mt5_universal.screenshot import dom
        out = str(tmp_path / "dom.png")
        env = dom(
            symbol="USDJPY",
            output_path=out,
            open_panel=False,
            close_panel=False,
        )
        assert env["ok"] is True
        assert env["data"]["symbol"] == "USDJPY"
        assert env["data"]["panel_opened"] is False
        assert env["data"]["panel_closed"] is False


# ---------------------------------------------------------------------------
# Bridge isolation
# ---------------------------------------------------------------------------


def test_screenshot_module_does_not_import_metatrader5():
    """Screenshot is pure capture - never touches the MT5 SDK bridge."""
    import importlib
    import mt5_universal.screenshot  # noqa: F401
    mod = importlib.import_module("mt5_universal.screenshot.screenshot")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
