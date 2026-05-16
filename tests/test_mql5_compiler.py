"""Tests for mt5_cli/mql5/compiler.py - metaeditor64.exe wrapper.

Strategy: mock the subprocess + filesystem so tests are hermetic and
platform-agnostic. The compiler module imports `subprocess` and
`shutil` as modules so the monkeypatched attributes are accessible.
"""
import subprocess
from pathlib import Path

from mt5_cli.mql5 import compiler


def test_locate_metaeditor_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(
        compiler, "_CANDIDATE_PATHS",
        [Path("/does/not/exist/metaeditor64.exe")],
    )
    monkeypatch.setattr(compiler.shutil, "which", lambda _: None)
    monkeypatch.delenv("MT5_METAEDITOR_PATH", raising=False)
    assert compiler.locate_metaeditor() is None


def test_locate_metaeditor_uses_env_var(monkeypatch, tmp_path):
    fake = tmp_path / "metaeditor64.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("MT5_METAEDITOR_PATH", str(fake))
    assert compiler.locate_metaeditor() == fake


def test_locate_metaeditor_falls_back_to_which(monkeypatch, tmp_path):
    """When env unset and candidates missing, use shutil.which."""
    fake = tmp_path / "metaeditor64.exe"
    fake.write_bytes(b"")
    monkeypatch.delenv("MT5_METAEDITOR_PATH", raising=False)
    monkeypatch.setattr(compiler, "_CANDIDATE_PATHS", [])
    monkeypatch.setattr(compiler.shutil, "which", lambda _: str(fake))
    assert compiler.locate_metaeditor() == fake


def test_compile_returns_fail_when_source_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(compiler, "locate_metaeditor",
                        lambda: tmp_path / "metaeditor64.exe")
    result = compiler.compile_source(tmp_path / "missing.mq5")
    assert result["ok"] is False
    assert result["error"]["code"] == "SOURCE_NOT_FOUND"


def test_compile_returns_fail_when_metaeditor_missing(monkeypatch, tmp_path):
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: None)
    result = compiler.compile_source(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "METAEDITOR_NOT_FOUND"


def test_compile_invokes_subprocess(monkeypatch, tmp_path):
    """Happy path: subprocess.run returns 0, log shows 0 errors, .ex5 exists."""
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    ex5 = src.with_suffix(".ex5")
    ex5.write_bytes(b"compiled-bytes")  # simulate MetaEditor producing .ex5
    log = src.with_suffix(".log")
    log.write_text("0 errors, 0 warnings\n", encoding="utf-8")
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")

    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    result = compiler.compile_source(src)
    assert result["ok"] is True
    assert result["data"]["ex5"] == str(ex5)
    # /compile: is the second positional arg per the cmd shape
    assert any("/compile:" in arg for arg in captured["cmd"])
    assert any("/log:" in arg for arg in captured["cmd"])


def test_compile_reports_compile_failed_on_errors(monkeypatch, tmp_path):
    """When the log shows error lines, return COMPILE_FAILED with the log."""
    src = tmp_path / "broken.mq5"
    src.write_text("// stub\n")
    log = src.with_suffix(".log")
    log.write_text(
        "broken.mq5(5,1) : error 123 - undefined identifier 'Foo'\n"
        "1 error, 0 warnings\n",
        encoding="utf-8",
    )
    # No .ex5 produced
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(
        compiler.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, "", ""),
    )
    result = compiler.compile_source(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "COMPILE_FAILED"
    assert "log" in result["error"]["data"]
    assert "undefined identifier" in result["error"]["data"]["log"]


def test_compile_handles_timeout(monkeypatch, tmp_path):
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)

    def raise_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], 1)

    monkeypatch.setattr(compiler.subprocess, "run", raise_timeout)
    result = compiler.compile_source(src, timeout=1)
    assert result["ok"] is False
    assert result["error"]["code"] == "COMPILE_TIMEOUT"


def test_parse_log_utf16_bom(tmp_path):
    """MetaEditor writes logs in UTF-16-LE with BOM by default."""
    log = tmp_path / "demo.log"
    text = "demo.mq5(5,1) : error 123 - undefined identifier 'Foo'\n0 warnings\n"
    log.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    errors, warnings, full = compiler._parse_log(log)
    assert errors == 1
    assert warnings == 0
    assert "Foo" in full
