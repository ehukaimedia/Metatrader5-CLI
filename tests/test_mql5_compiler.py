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
    import os as _os
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    ex5 = src.with_suffix(".ex5")
    ex5.write_bytes(b"compiled-bytes")  # simulate MetaEditor producing .ex5
    # The freshness gate requires .ex5 mtime STRICTLY greater than src
    # mtime; Windows often records both as equal when they're created
    # within the same second, so bump ex5 forward explicitly.
    src_mtime = src.stat().st_mtime
    _os.utime(ex5, (src_mtime + 1, src_mtime + 1))
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
    assert result["error"]["code"] == "MQL5_COMPILE_FAILED"
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
    assert result["error"]["code"] == "MQL5_COMPILE_TIMEOUT"


def test_compile_fails_when_ex5_mtime_equals_source_mtime(
    monkeypatch, tmp_path,
):
    """Spock polish re-review boundary: a stale .ex5 forced to the EXACT
    same mtime as the source must STILL fail. Equal mtimes can happen
    on coarse-resolution filesystems or when a prior .ex5 happens to
    be timestamped identically to a freshly-touched source; the
    freshness gate must be strict `>`, not `>=`."""
    import os as _os
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    stale_ex5 = src.with_suffix(".ex5")
    stale_ex5.write_bytes(b"stale-binary")
    # Force the two mtimes to be exactly equal
    src_mtime = src.stat().st_mtime
    _os.utime(stale_ex5, (src_mtime, src_mtime))
    log = src.with_suffix(".log")
    log.write_text("0 errors, 0 warnings\n", encoding="utf-8")

    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(
        compiler.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, "", "fatal\n"),
    )

    result = compiler.compile_source(src)
    assert result["ok"] is False, (
        "equal mtime must be treated as stale; got: " + str(result)
    )
    assert result["error"]["code"] == "MQL5_COMPILE_FAILED"
    assert "stale" in result["error"]["message"]


def test_compile_fails_when_stale_ex5_predates_source(
    monkeypatch, tmp_path,
):
    """Spock P1 repro tightened: a STALE demo.ex5 (mtime < source) from
    a previous successful compile exists. MetaEditor exited nonzero
    this run and the log shows no errors. Without the mtime guard the
    agent would deploy the OLD binary believing it matched the source.
    Must fail closed when .ex5 predates the source even if errors=0."""
    import os as _os
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    # Stale .ex5: explicitly set mtime BEFORE the source mtime so the
    # freshness check kicks in (test_compile_invokes_subprocess covers
    # the fresh case where the test creates ex5 after src).
    stale_ex5 = src.with_suffix(".ex5")
    stale_ex5.write_bytes(b"stale-binary")
    src_mtime = src.stat().st_mtime
    _os.utime(stale_ex5, (src_mtime - 60, src_mtime - 60))
    log = src.with_suffix(".log")
    log.write_text("0 errors, 0 warnings\n", encoding="utf-8")

    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(
        compiler.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0], 1, "", "fatal: cannot compile\n"
        ),
    )

    result = compiler.compile_source(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "MQL5_COMPILE_FAILED"
    assert "stale" in result["error"]["message"]
    assert result["error"]["data"]["exit_code"] == 1


def test_compile_succeeds_with_warnings_and_nonzero_return(
    monkeypatch, tmp_path,
):
    """Live E2E polish: MetaEditor exits 1 even on warnings-only
    successful builds that DO produce a fresh .ex5. The previous
    returncode-first gate flagged these as MQL5_COMPILE_FAILED. The
    re-graded gate (errors > 0 OR .ex5 missing OR .ex5 stale) must
    now return ok with warnings surfaced — the .ex5 is real and
    deployable."""
    import os as _os
    src = tmp_path / "smoke_alpha.mq5"
    src.write_text("// minimal EA\n")
    # Make sure .ex5 mtime is AFTER source (the fresh case)
    ex5 = src.with_suffix(".ex5")
    ex5.write_bytes(b"compiled-with-warnings")
    src_mtime = src.stat().st_mtime
    _os.utime(ex5, (src_mtime + 1, src_mtime + 1))
    log = src.with_suffix(".log")
    # Realistic MetaEditor "warnings only" log
    log.write_text(
        "smoke_alpha.mq5(7,1) : warning 68 - version 0.1 is incompatible\n"
        "0 errors, 1 warnings, 323 ms elapsed, code generated\n",
        encoding="utf-8",
    )
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(
        compiler.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, "", ""),
    )
    result = compiler.compile_source(src)
    assert result["ok"] is True, (
        f"warnings-only compile must succeed; got fail: {result}"
    )
    assert result["data"]["errors"] == 0
    assert result["data"]["warnings"] == 1
    assert result["data"]["ex5"] == str(ex5)
    # Surface the nonzero exit_code so callers can audit
    assert result["data"]["exit_code"] == 1


def test_compile_success_exposes_exit_code_zero(monkeypatch, tmp_path):
    """Sanity: the happy-path envelope includes exit_code=0 so callers
    can confirm the gate is honored consistently."""
    import os as _os
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    ex5 = src.with_suffix(".ex5")
    ex5.write_bytes(b"compiled-bytes")
    src_mtime = src.stat().st_mtime
    _os.utime(ex5, (src_mtime + 1, src_mtime + 1))
    log = src.with_suffix(".log")
    log.write_text("0 errors, 0 warnings\n", encoding="utf-8")
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(
        compiler.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    result = compiler.compile_source(src)
    assert result["ok"] is True
    assert result["data"]["exit_code"] == 0


def test_parse_log_utf16_bom(tmp_path):
    """MetaEditor writes logs in UTF-16-LE with BOM by default."""
    log = tmp_path / "demo.log"
    text = "demo.mq5(5,1) : error 123 - undefined identifier 'Foo'\n0 warnings\n"
    log.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    errors, warnings, full = compiler._parse_log(log)
    assert errors == 1
    assert warnings == 0
    assert "Foo" in full
