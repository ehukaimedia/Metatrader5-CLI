"""Tests for mt5_cli/mql5/deployer.py - copy .mq5+.ex5 to MT5 MQL5/ dirs.

Strategy: mock the candidate data dirs + env var so tests are
hermetic and platform-independent.
"""
from pathlib import Path

from mt5_cli.mql5 import deployer


def test_resolve_terminal_data_dir_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(tmp_path))
    assert deployer.resolve_terminal_data_dir() == (tmp_path, "env_var")


def test_resolve_terminal_data_dir_returns_none_when_env_missing(
    monkeypatch, tmp_path,
):
    bogus = tmp_path / "no-such-dir"
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(bogus))
    assert deployer.resolve_terminal_data_dir() == (None, "unresolved")


def test_resolve_terminal_data_dir_returns_none_when_nothing_matches(
    monkeypatch,
):
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)
    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS",
                        [Path("/does/not/exist")])
    assert deployer.resolve_terminal_data_dir() == (None, "unresolved")


def test_resolve_terminal_data_dir_picks_newest_hash_dir(monkeypatch, tmp_path):
    """When the candidate root has multiple terminal hash dirs, pick the
    newest one that has an MQL5/ subdir, and tag the resolution as
    `fallback_newest_hash` so callers can see they're on the heuristic."""
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)
    root = tmp_path / "Terminal"
    root.mkdir()
    older = root / "AAAA1111"
    (older / "MQL5").mkdir(parents=True)
    newer = root / "BBBB2222"
    (newer / "MQL5").mkdir(parents=True)
    # Force older's mtime backward so newer wins regardless of FS ordering
    import os as _os
    _os.utime(older, (1_000_000_000, 1_000_000_000))

    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS", [root])
    data_dir, via = deployer.resolve_terminal_data_dir()
    assert data_dir == newer
    assert via == "fallback_newest_hash"


def test_deploy_ea_copies_mq5_and_ex5_to_experts(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "MQL5" / "Experts").mkdir(parents=True)
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    (src_dir / "demo.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    result = deployer.deploy_ea(src_dir / "demo.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Experts" / "demo.mq5").exists()
    assert (data_dir / "MQL5" / "Experts" / "demo.ex5").exists()
    copied = result["data"]["copied"]
    assert any("demo.mq5" in p for p in copied)
    assert any("demo.ex5" in p for p in copied)


def test_deploy_indicator_copies_to_indicators(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    src_dir = tmp_path / "indicators"
    src_dir.mkdir()
    (src_dir / "donchian.mq5").write_text("// stub")
    (src_dir / "donchian.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    result = deployer.deploy_indicator(src_dir / "donchian.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Indicators" / "donchian.mq5").exists()


def test_deploy_fails_when_source_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda: tmp_path / "data")
    result = deployer.deploy_ea(tmp_path / "missing.mq5")
    assert result["ok"] is False
    assert result["error"]["code"] == "SOURCE_NOT_FOUND"


def test_deploy_fails_when_data_dir_unresolved(monkeypatch, tmp_path):
    src = tmp_path / "demo.mq5"
    src.write_text("// stub")
    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (None, "unresolved"))
    result = deployer.deploy_ea(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "TERMINAL_DATA_DIR_NOT_FOUND"


def test_resolve_terminal_data_dir_prefers_explicit_data_path(
    monkeypatch, tmp_path,
):
    """When the caller passes data_path explicitly (CLI threads this
    from bridge.terminal_info().data_path), it MUST take precedence
    over env + newest-hash-dir resolution so the file lands in the
    terminal the user is actually connected to."""
    explicit = tmp_path / "connected_terminal"
    explicit.mkdir()
    # Even with the env var set to something else, explicit wins
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(tmp_path / "wrong"))
    data_dir, via = deployer.resolve_terminal_data_dir(explicit)
    assert data_dir == explicit
    assert via == "explicit_data_path"


def test_resolve_terminal_data_dir_returns_none_when_explicit_missing(
    monkeypatch, tmp_path,
):
    """If the explicit data_path does not exist, return None — do NOT
    silently fall through to the env / newest-hash fallback. The
    caller asked for a specific path; surface that it's gone."""
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)
    bogus = tmp_path / "no-such-dir"
    data_dir, via = deployer.resolve_terminal_data_dir(bogus)
    assert data_dir is None
    assert via == "unresolved"


def test_deploy_fails_closed_when_target_subdir_is_a_file(
    monkeypatch, tmp_path,
):
    """Spock P2 repro: MQL5/Experts exists as a FILE, not a directory.
    Previously the mkdir raised FileExistsError, bypassing emit() and
    making the CLI exit 1 with a traceback. Must fail closed with
    DEPLOY_TARGET_NOT_WRITABLE so the agent gets a structured envelope."""
    data_dir = tmp_path / "data"
    (data_dir / "MQL5").mkdir(parents=True)
    # MQL5/Experts is a file blocking the mkdir
    (data_dir / "MQL5" / "Experts").write_text("not a dir")
    src = tmp_path / "demo.mq5"
    src.write_text("// stub")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    result = deployer.deploy_ea(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "DEPLOY_TARGET_NOT_WRITABLE"
    assert "Experts" in result["error"]["message"]


def test_deploy_fails_closed_when_copy_raises(monkeypatch, tmp_path):
    """When the mkdir succeeds but shutil.copy2 raises (e.g. ACL,
    disk full), still fail closed with DEPLOY_TARGET_NOT_WRITABLE."""
    data_dir = tmp_path / "data"
    src = tmp_path / "demo.mq5"
    src.write_text("// stub")
    (tmp_path / "demo.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))

    def boom(*a, **kw):
        raise PermissionError("ACL deny")

    monkeypatch.setattr(deployer.shutil, "copy2", boom)
    result = deployer.deploy_ea(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "DEPLOY_TARGET_NOT_WRITABLE"
    assert "ACL deny" in result["error"]["message"]


def test_deploy_ea_threads_data_path_kwarg(monkeypatch, tmp_path):
    """Verify deploy_ea forwards data_path to resolve_terminal_data_dir."""
    captured = {}

    def fake_resolve(data_path=None):
        captured["data_path"] = data_path
        return tmp_path / "data", "explicit_data_path"

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", fake_resolve)
    src = tmp_path / "demo.mq5"
    src.write_text("// stub")
    explicit = tmp_path / "explicit_terminal"
    deployer.deploy_ea(src, data_path=explicit)
    assert captured["data_path"] == explicit


def test_deploy_indicator_threads_data_path_kwarg(monkeypatch, tmp_path):
    captured = {}

    def fake_resolve(data_path=None):
        captured["data_path"] = data_path
        return tmp_path / "data", "explicit_data_path"

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", fake_resolve)
    src = tmp_path / "rsi.mq5"
    src.write_text("// stub")
    explicit = tmp_path / "explicit_terminal"
    deployer.deploy_indicator(src, data_path=explicit)
    assert captured["data_path"] == explicit


def test_deploy_success_envelope_includes_resolved_via(monkeypatch, tmp_path):
    """The success envelope must surface how the data_dir was picked
    so audit logs can distinguish a deliberate explicit deploy from
    the fallback newest-hash heuristic (which can target the wrong
    terminal install)."""
    data_dir = tmp_path / "data"
    src = tmp_path / "demo.mq5"
    src.write_text("// stub")

    monkeypatch.setattr(
        deployer, "resolve_terminal_data_dir",
        lambda *a, **kw: (data_dir, "fallback_newest_hash"),
    )
    result = deployer.deploy_ea(src)
    assert result["ok"] is True
    assert result["data"]["resolved_via"] == "fallback_newest_hash"


def test_deploy_with_only_mq5_copies_just_the_source(monkeypatch, tmp_path):
    """Pre-compile deploy is a valid workflow (rare). The .ex5 sibling is
    optional; the result still reports the mq5 was copied."""
    data_dir = tmp_path / "data"
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    # No demo.ex5

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    result = deployer.deploy_ea(src_dir / "demo.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Experts" / "demo.mq5").exists()
    assert not (data_dir / "MQL5" / "Experts" / "demo.ex5").exists()


# ---------------------------------------------------------------------------
# Navigator refresh integration (Phase 5 Wave A)
# ---------------------------------------------------------------------------


def _stub_deploy_setup(monkeypatch, tmp_path):
    """Common setup so deploy succeeds; tests only assert the refresh path."""
    data_dir = tmp_path / "data"
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    (src_dir / "demo.ex5").write_bytes(b"compiled")
    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    return data_dir, src_dir / "demo.mq5"


def test_deploy_ea_calls_refresh_navigator_by_default(monkeypatch, tmp_path):
    """refresh_navigator default-on: a successful deploy attempts the F5 poke."""
    _, src = _stub_deploy_setup(monkeypatch, tmp_path)
    captured = {"called": False}

    def fake_refresh():
        captured["called"] = True
        return {"ok": True, "data": {"attempted": True, "navigator_hwnd": 42,
                                      "message": "F5 posted; not verified."}}

    monkeypatch.setattr(deployer, "_refresh_navigator", fake_refresh)
    result = deployer.deploy_ea(src)
    assert result["ok"] is True
    assert captured["called"] is True


def test_deploy_ea_skips_refresh_when_flag_false(monkeypatch, tmp_path):
    """refresh_navigator=False suppresses the F5 poke entirely; no envelope key."""
    _, src = _stub_deploy_setup(monkeypatch, tmp_path)
    captured = {"called": False}

    def fake_refresh():
        captured["called"] = True
        return {"ok": True, "data": {}}

    monkeypatch.setattr(deployer, "_refresh_navigator", fake_refresh)
    result = deployer.deploy_ea(src, refresh_navigator=False)
    assert result["ok"] is True
    assert captured["called"] is False
    assert "navigator_refresh" not in result["data"]


def test_deploy_ea_envelope_includes_navigator_refresh_on_success(
    monkeypatch, tmp_path,
):
    """Successful F5 poke surfaces attempted/navigator_hwnd/message."""
    _, src = _stub_deploy_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(deployer, "_refresh_navigator", lambda: {
        "ok": True,
        "data": {
            "attempted": True,
            "navigator_hwnd": 2042,
            "message": "F5 posted; rescan not verifiable.",
        },
    })
    result = deployer.deploy_ea(src)
    nav = result["data"]["navigator_refresh"]
    assert nav["attempted"] is True
    assert nav["navigator_hwnd"] == 2042
    assert "message" in nav


def test_deploy_ea_navigator_failure_does_not_fail_deploy(monkeypatch, tmp_path):
    """If F5 cannot be posted, deploy still succeeds; envelope carries the
    NAVIGATOR_NOT_FOUND warning so the caller knows to refresh manually."""
    _, src = _stub_deploy_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(deployer, "_refresh_navigator", lambda: {
        "ok": False,
        "error": {
            "code": "NAVIGATOR_NOT_FOUND",
            "message": "Navigator panel not found.",
        },
    })
    result = deployer.deploy_ea(src)
    assert result["ok"] is True   # deploy itself succeeded
    nav = result["data"]["navigator_refresh"]
    assert nav["attempted"] is False
    assert nav["error"]["code"] == "NAVIGATOR_NOT_FOUND"


def test_deploy_indicator_calls_refresh_navigator_by_default(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    src_dir = tmp_path / "ind"
    src_dir.mkdir()
    (src_dir / "rsi.mq5").write_text("// stub")
    monkeypatch.setattr(deployer, "resolve_terminal_data_dir",
                        lambda *a, **kw: (data_dir, "explicit_data_path"))
    captured = {"called": False}
    monkeypatch.setattr(deployer, "_refresh_navigator", lambda: (
        captured.update(called=True),
        {"ok": True, "data": {"attempted": True}},
    )[1])
    result = deployer.deploy_indicator(src_dir / "rsi.mq5")
    assert result["ok"] is True
    assert captured["called"] is True


def test_deploy_refresh_skipped_when_underlying_copy_fails(monkeypatch, tmp_path):
    """If deploy itself fails (e.g. SOURCE_NOT_FOUND), do NOT attempt the
    F5 poke — there is nothing newly deployed to rescan, and we should
    not waste an OS event."""
    captured = {"called": False}
    monkeypatch.setattr(deployer, "_refresh_navigator", lambda: (
        captured.update(called=True), {"ok": True, "data": {}},
    )[1])
    result = deployer.deploy_ea(tmp_path / "missing.mq5")
    assert result["ok"] is False
    assert result["error"]["code"] == "SOURCE_NOT_FOUND"
    assert captured["called"] is False
