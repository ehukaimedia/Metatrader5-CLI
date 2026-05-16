"""Tests for mt5_cli/mql5/deployer.py - copy .mq5+.ex5 to MT5 MQL5/ dirs.

Strategy: mock the candidate data dirs + env var so tests are
hermetic and platform-independent.
"""
from pathlib import Path

from mt5_cli.mql5 import deployer


def test_resolve_terminal_data_dir_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(tmp_path))
    assert deployer.resolve_terminal_data_dir() == tmp_path


def test_resolve_terminal_data_dir_returns_none_when_env_missing(
    monkeypatch, tmp_path,
):
    bogus = tmp_path / "no-such-dir"
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(bogus))
    assert deployer.resolve_terminal_data_dir() is None


def test_resolve_terminal_data_dir_returns_none_when_nothing_matches(
    monkeypatch,
):
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)
    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS",
                        [Path("/does/not/exist")])
    assert deployer.resolve_terminal_data_dir() is None


def test_resolve_terminal_data_dir_picks_newest_hash_dir(monkeypatch, tmp_path):
    """When the candidate root has multiple terminal hash dirs, pick the
    newest one that has an MQL5/ subdir."""
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
    assert deployer.resolve_terminal_data_dir() == newer


def test_deploy_ea_copies_mq5_and_ex5_to_experts(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "MQL5" / "Experts").mkdir(parents=True)
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    (src_dir / "demo.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: data_dir)
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

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: data_dir)
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
    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: None)
    result = deployer.deploy_ea(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "TERMINAL_DATA_DIR_NOT_FOUND"


def test_deploy_with_only_mq5_copies_just_the_source(monkeypatch, tmp_path):
    """Pre-compile deploy is a valid workflow (rare). The .ex5 sibling is
    optional; the result still reports the mq5 was copied."""
    data_dir = tmp_path / "data"
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    # No demo.ex5

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: data_dir)
    result = deployer.deploy_ea(src_dir / "demo.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Experts" / "demo.mq5").exists()
    assert not (data_dir / "MQL5" / "Experts" / "demo.ex5").exists()
