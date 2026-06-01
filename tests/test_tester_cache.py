"""Tests for mt5_cli/tester/cache.py - per-run snapshot dirs."""
from datetime import datetime, timezone
from pathlib import Path

from mt5_cli.tester import cache


def test_make_run_id_format():
    rid = cache.make_run_id(
        "alpha", "AUDUSD", "M5",
        at=datetime(2026, 5, 15, 14, 22, 5, tzinfo=timezone.utc),
    )
    assert rid == "2026-05-15T14-22-05_alpha_AUDUSD_M5"


def test_make_run_id_defaults_to_now():
    """Without `at`, falls back to UTC now. Just sanity-check the shape."""
    rid = cache.make_run_id("alpha", "AUDUSD", "M5")
    assert rid.endswith("_alpha_AUDUSD_M5")
    # Format: YYYY-MM-DDTHH-MM-SS_<expert>_<symbol>_<tf>
    assert len(rid.split("_")[0]) == len("2026-05-15T14-22-05")


def test_run_dir_creates_under_results(tmp_path):
    rid = "2026-05-15T14-22-05_alpha_AUDUSD_M5"
    rdir = cache.run_dir(rid, root=tmp_path)
    assert rdir == tmp_path / rid
    assert rdir.exists()


def test_run_dir_idempotent(tmp_path):
    """Calling run_dir twice for the same run_id is a no-op (mkdir exist_ok)."""
    rid = "duplicate_run"
    cache.run_dir(rid, root=tmp_path)
    cache.run_dir(rid, root=tmp_path)
    assert (tmp_path / rid).exists()


def test_list_recent_orders_newest_first(tmp_path):
    for stamp in (
        "2026-05-14T10-00-00_a",
        "2026-05-15T10-00-00_b",
        "2026-05-13T10-00-00_c",
    ):
        (tmp_path / stamp).mkdir()
    out = cache.list_recent(root=tmp_path, limit=3)
    assert [r["run_id"] for r in out] == [
        "2026-05-15T10-00-00_b",
        "2026-05-14T10-00-00_a",
        "2026-05-13T10-00-00_c",
    ]


def test_list_recent_returns_empty_when_root_missing(tmp_path):
    bogus = tmp_path / "no-such-root"
    assert cache.list_recent(root=bogus) == []


def test_list_recent_respects_limit(tmp_path):
    for i in range(5):
        (tmp_path / f"2026-05-{15-i:02d}T10-00-00_run").mkdir()
    out = cache.list_recent(root=tmp_path, limit=2)
    assert len(out) == 2


def test_get_run_returns_payload_when_present(tmp_path):
    rid = "real_run"
    (tmp_path / rid).mkdir()
    got = cache.get_run(rid, root=tmp_path)
    assert got is not None
    assert got["run_id"] == rid
    assert Path(got["path"]) == tmp_path / rid


def test_get_run_returns_none_when_missing(tmp_path):
    assert cache.get_run("nope", root=tmp_path) is None
