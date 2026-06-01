"""Tests for mt5_cli/mql5/discovery.py - auto-find EAs/indicators.

Strategy: monkeypatch _search_paths to point at tmp_path so tests are
hermetic and don't read the user's real home dir.
"""

from mt5_cli.mql5 import discovery


def test_list_eas_returns_empty_when_no_search_paths(monkeypatch):
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [])
    assert discovery.list_eas() == []


def test_list_eas_finds_mq5_and_marks_compiled(tmp_path, monkeypatch):
    ea_dir = tmp_path / "ea"
    ea_dir.mkdir()
    (ea_dir / "alpha.mq5").write_text("// stub")
    (ea_dir / "alpha.ex5").write_bytes(b"compiled")
    (ea_dir / "beta.mq5").write_text("// stub")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [ea_dir])
    found = discovery.list_eas()
    names = {e["name"]: e for e in found}
    assert set(names) == {"alpha", "beta"}
    assert names["alpha"]["compiled"] is True
    assert names["beta"]["compiled"] is False


def test_list_indicators_uses_indicators_kind(tmp_path, monkeypatch):
    indicators_dir = tmp_path / "indicators"
    indicators_dir.mkdir()
    (indicators_dir / "rsi.mq5").write_text("// stub")
    captured = {}

    def fake_paths(kind):
        captured["kind"] = kind
        return [indicators_dir]

    monkeypatch.setattr(discovery, "_search_paths", fake_paths)
    out = discovery.list_indicators()
    assert captured["kind"] == "indicators"
    assert [e["name"] for e in out] == ["rsi"]


def test_get_ea_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [tmp_path])
    assert discovery.get_ea("missing") is None


def test_get_ea_returns_path_and_compiled_flag(tmp_path, monkeypatch):
    (tmp_path / "demo.mq5").write_text("// stub")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [tmp_path])
    e = discovery.get_ea("demo")
    assert e is not None
    assert e["name"] == "demo"
    assert e["source"].endswith("demo.mq5")
    assert e["compiled"] is False


def test_get_ea_marks_compiled_when_ex5_exists(tmp_path, monkeypatch):
    (tmp_path / "demo.mq5").write_text("// stub")
    (tmp_path / "demo.ex5").write_bytes(b"compiled")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [tmp_path])
    e = discovery.get_ea("demo")
    assert e["compiled"] is True


def test_get_ea_first_match_wins_across_roots(tmp_path, monkeypatch):
    """When the same EA name appears in CWD and the user dir, CWD wins."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "demo.mq5").write_text("// from a")
    (b / "demo.mq5").write_text("// from b")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [a, b])
    e = discovery.get_ea("demo")
    # First-match-wins on the ordered search-path list
    assert e["source"].replace("\\", "/").endswith("/a/demo.mq5")


def test_list_first_match_wins(tmp_path, monkeypatch):
    """Same name in two roots → list shows the first-root entry only."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "demo.mq5").write_text("// from a")
    (b / "demo.mq5").write_text("// from b")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [a, b])
    out = discovery.list_eas()
    assert len(out) == 1
    assert out[0]["source"].replace("\\", "/").endswith("/a/demo.mq5")


def test_get_ea_finds_nested_mq5(tmp_path, monkeypatch):
    """When the .mq5 lives in a nested subdir (e.g., examples/<name>.mq5),
    get_ea should still find it within the same root."""
    root = tmp_path
    nested = root / "examples"
    nested.mkdir()
    (nested / "macd_sample.mq5").write_text("// stub")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [root])
    e = discovery.get_ea("macd_sample")
    assert e is not None
    assert e["source"].endswith("macd_sample.mq5")


def test_search_paths_filters_to_existing_dirs(monkeypatch, tmp_path):
    """_search_paths should only return roots that actually exist."""
    # Force CWD into tmp_path so the "./ea" arm resolves to tmp_path/ea
    monkeypatch.chdir(tmp_path)
    # Don't create the ea/ subdir → CWD arm should be filtered out
    # Force the user fallback root to a tmp dir that DOES exist
    monkeypatch.setattr(
        "os.path.expanduser",
        lambda p: str(tmp_path) if p == "~" else p,
    )
    user_dir = tmp_path / ".local" / "share" / "metatrader5-cli" / "ea"
    user_dir.mkdir(parents=True)
    paths = discovery._search_paths("ea")
    # CWD/ea does not exist (filtered out); user_dir does
    assert paths == [user_dir]
