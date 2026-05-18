"""Tests for mt5_cli/tester/launcher.py - terminal64 /config wrapper."""
import subprocess

import pytest

from mt5_cli.tester import launcher


@pytest.fixture(autouse=True)
def _no_existing_terminal(monkeypatch):
    monkeypatch.setattr(launcher, "is_terminal_running", lambda: False)


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
    monkeypatch.setattr(launcher, "is_terminal_running", lambda: True)

    out = launcher.run(ini_path=ini, run_dir=tmp_path)

    assert out["ok"] is False
    assert out["error"]["code"] == "TERMINAL_ALREADY_RUNNING"


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
