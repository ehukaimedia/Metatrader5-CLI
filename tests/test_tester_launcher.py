"""Tests for mt5_cli/tester/launcher.py - terminal64 /config wrapper."""
import subprocess

from mt5_cli.tester import launcher


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
    assert "/portable" in captured["cmd"]
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 30


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
