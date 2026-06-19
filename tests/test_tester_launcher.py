"""Tests for mt5_cli/tester/launcher.py - terminal64 /config wrapper."""
import subprocess

import pytest

from mt5_cli.tester import launcher

_REAL_IS_TERMINAL_RUNNING = launcher.is_terminal_running


@pytest.fixture(autouse=True)
def _no_existing_terminal(monkeypatch):
    monkeypatch.setattr(launcher, "is_terminal_running", lambda terminal=None: False)


def test_locate_terminal_uses_env(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(fake))

    assert launcher.locate_terminal() == fake


def test_run_returns_fail_when_ini_missing(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)

    out = launcher.run(ini_path=tmp_path / "missing.ini", run_dir=tmp_path)

    assert out["ok"] is False
    assert out["error"]["code"] == "INI_NOT_FOUND"


def test_run_returns_fail_when_terminal_missing(monkeypatch, tmp_path):
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "locate_terminal", lambda: None)

    out = launcher.run(ini_path=ini, run_dir=tmp_path)

    assert out["ok"] is False
    assert out["error"]["code"] == "TERMINAL_NOT_FOUND"


def test_run_refuses_existing_terminal_by_default(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    captured = {}

    def fake_running(terminal=None):
        captured["terminal"] = terminal
        return True

    monkeypatch.setattr(launcher, "is_terminal_running", fake_running)

    out = launcher.run(ini_path=ini, run_dir=tmp_path)

    assert out["ok"] is False
    assert out["error"]["code"] == "TERMINAL_ALREADY_RUNNING"
    assert captured["terminal"] == fake


def test_is_terminal_running_checks_selected_terminal_path(monkeypatch, tmp_path):
    selected = tmp_path / "batch" / "terminal64.exe"
    selected.parent.mkdir()
    selected.write_bytes(b"")
    interactive = tmp_path / "interactive" / "terminal64.exe"
    interactive.parent.mkdir()
    interactive.write_bytes(b"")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        assert "Win32_Process" in cmd[-1]
        stdout = f"{interactive}\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert _REAL_IS_TERMINAL_RUNNING(selected) is False


def test_is_terminal_running_matches_selected_terminal_path(monkeypatch, tmp_path):
    selected = tmp_path / "batch" / "terminal64.exe"
    selected.parent.mkdir()
    selected.write_bytes(b"")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        assert "Win32_Process" in cmd[-1]
        stdout = f"{selected}\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert _REAL_IS_TERMINAL_RUNNING(selected) is True


def test_is_terminal_running_fails_closed_for_selected_terminal(monkeypatch, tmp_path):
    selected = tmp_path / "batch" / "terminal64.exe"
    selected.parent.mkdir()
    selected.write_bytes(b"")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert _REAL_IS_TERMINAL_RUNNING(selected) is True


def test_is_terminal_running_fails_closed_when_unscoped_inspection_fails(monkeypatch):
    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert _REAL_IS_TERMINAL_RUNNING() is True


def test_run_invokes_subprocess(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    rd = tmp_path / "run"
    rd.mkdir()

    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, "stdout", "stderr")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=rd, timeout=30)

    assert out["ok"] is True
    assert out["data"]["exit_code"] == 0
    assert out["data"]["stdout"] == "stdout"
    assert out["data"]["stderr"] == "stderr"
    assert out["data"]["run_dir"] == str(rd)
    assert any(arg.startswith("/config:") for arg in captured["cmd"])
    assert "/portable" not in captured["cmd"]
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 30


def test_run_can_allow_existing_terminal(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher, "is_terminal_running", lambda terminal=None: True)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path, allow_existing_terminal=True)

    assert out["ok"] is True


def test_run_can_opt_into_portable(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path, portable=True)

    assert out["ok"] is True
    assert "/portable" in captured["cmd"]


def test_run_can_opt_into_portable_via_env(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("MT5_TERMINAL_PORTABLE", "1")
    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path)

    assert out["ok"] is True
    assert "/portable" in captured["cmd"]


def test_locate_terminal_data_dir_uses_portable_install_dir(monkeypatch, tmp_path):
    terminal = tmp_path / "MetaTrader 5" / "terminal64.exe"
    terminal.parent.mkdir()
    terminal.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PORTABLE", "1")
    monkeypatch.setenv("APPDATA", str(tmp_path / "missing-appdata"))

    assert launcher.locate_terminal_data_dir(terminal) == terminal.parent


def test_locate_terminal_data_dir_matches_origin(monkeypatch, tmp_path):
    terminal_dir = tmp_path / "Program Files" / "MetaTrader 5"
    terminal = terminal_dir / "terminal64.exe"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"")
    data_root = tmp_path / "MetaQuotes" / "Terminal"
    matched = data_root / "HASH1"
    other = data_root / "HASH2"
    matched.mkdir(parents=True)
    other.mkdir()
    (matched / "origin.txt").write_text(str(terminal_dir), encoding="utf-8")
    (other / "origin.txt").write_text(r"C:\Other", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert launcher.locate_terminal_data_dir(terminal) == matched


def test_locate_terminal_data_dir_does_not_guess_for_explicit_terminal(monkeypatch, tmp_path):
    terminal_dir = tmp_path / "batch" / "MetaTrader 5"
    terminal = terminal_dir / "terminal64.exe"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"")
    data_root = tmp_path / "MetaQuotes" / "Terminal"
    (data_root / "HASH1").mkdir(parents=True)
    mismatched = data_root / "HASH2"
    mismatched.mkdir()
    (mismatched / "origin.txt").write_text(str(tmp_path / "interactive"), encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert launcher.locate_terminal_data_dir(terminal) is None


def test_locate_terminal_data_dir_does_not_guess_for_env_terminal(monkeypatch, tmp_path):
    terminal_dir = tmp_path / "batch" / "MetaTrader 5"
    terminal = terminal_dir / "terminal64.exe"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"")
    data_root = tmp_path / "MetaQuotes" / "Terminal"
    (data_root / "HASH1").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(terminal))

    assert launcher.locate_terminal_data_dir() is None


def test_prepare_report_target_creates_mt5_relative_path(monkeypatch, tmp_path):
    data_dir = tmp_path / "terminal-data"
    stale = data_dir / "reports" / "metatrader5-cli" / "run1" / "report.htm"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    monkeypatch.setattr(launcher, "locate_terminal_data_dir", lambda: data_dir)

    prepared = launcher.prepare_report_target(run_id="run1", filename="report.htm")

    assert prepared is not None
    relative, absolute = prepared
    assert relative == "reports\\metatrader5-cli\\run1\\report.htm"
    assert absolute == stale
    assert absolute.parent.exists()
    assert not absolute.exists()


def test_stage_expert_parameters_copies_set_file(monkeypatch, tmp_path):
    data_dir = tmp_path / "terminal-data"
    source = tmp_path / "alpha.set"
    source.write_text("Risk=1.0\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "locate_terminal_data_dir", lambda: data_dir)

    staged = launcher.stage_expert_parameters(source)

    assert staged == data_dir / "MQL5" / "Profiles" / "Tester" / "alpha.set"
    assert staged.read_text(encoding="utf-8") == "Risk=1.0\n"


def test_stage_expert_copies_source_and_binary(monkeypatch, tmp_path):
    data_dir = tmp_path / "terminal-data"
    source = tmp_path / "alpha.mq5"
    compiled = tmp_path / "alpha.ex5"
    source.write_text("source", encoding="utf-8")
    compiled.write_bytes(b"compiled")
    monkeypatch.setattr(launcher, "locate_terminal_data_dir", lambda: data_dir)

    staged = launcher.stage_expert(source)

    target_dir = data_dir / "MQL5" / "Experts"
    assert staged == target_dir / "alpha.ex5"
    assert (target_dir / "alpha.mq5").read_text(encoding="utf-8") == "source"
    assert (target_dir / "alpha.ex5").read_bytes() == b"compiled"


def test_run_returns_fail_when_terminal_exits_nonzero(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        return subprocess.CompletedProcess(cmd, 5, "out", "bad config")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path, timeout=1)

    assert out["ok"] is False
    assert out["error"]["code"] == "TESTER_FAILED"
    assert out["error"]["data"]["exit_code"] == 5
    assert "bad config" in out["error"]["message"]


def test_run_returns_account_not_specified_from_terminal_log(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    data_dir = tmp_path / "terminal-data"
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "20260619.log").write_bytes(
        "Tester\ttester not started because the account is not specified\n".encode(
            "utf-16-le"
        )
    )
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        return subprocess.CompletedProcess(cmd, 3294954943, "", "")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher, "locate_terminal_data_dir", lambda terminal=None: data_dir)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path, timeout=1)

    assert out["ok"] is False
    assert out["error"]["code"] == "TESTER_ACCOUNT_NOT_SPECIFIED"
    assert out["error"]["data"]["terminal"] == str(fake)
    assert out["error"]["data"]["diagnostic"] == (
        "tester not started because the account is not specified"
    )
    assert "log_tail" not in out["error"]["data"]


def test_terminal_log_tail_handles_utf8_logs(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    data_dir = tmp_path / "terminal-data"
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "20260619.log").write_text(
        "Tester\ttester not started because the account is not specified\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(launcher, "locate_terminal_data_dir", lambda terminal=None: data_dir)

    assert launcher._has_account_not_specified_log(launcher._terminal_log_tail(fake))


def test_terminal_log_tail_handles_data_dir_lookup_error(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")

    def boom(terminal=None):
        raise OSError("scan failed")

    monkeypatch.setattr(launcher, "locate_terminal_data_dir", boom)

    assert launcher._terminal_log_tail(fake) == ""


def test_run_returns_fail_when_subprocess_times_out(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    out = launcher.run(ini_path=ini, run_dir=tmp_path, timeout=1)

    assert out["ok"] is False
    assert out["error"]["code"] == "TESTER_TIMEOUT"
