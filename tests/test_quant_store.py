"""Quant campaign store: id shape + manifest round-trip + listing."""
from mt5_cli.quant import store


def test_campaign_id_shape():
    assert store.make_campaign_id("alpha", at="2026-06-16T19-40-00") == "2026-06-16T19-40-00_quant_alpha"


def test_manifest_roundtrip_and_list(tmp_path):
    cid = "2026-06-16T19-40-00_quant_alpha"
    data = {"schema": "quant.v1", "campaign_id": cid, "ranked": [], "rejected": []}
    store.write_manifest(cid, data, root=tmp_path)

    loaded = store.get_campaign(cid, root=tmp_path)
    assert loaded["campaign_id"] == cid
    assert loaded["data"]["schema"] == "quant.v1"
    assert [c["campaign_id"] for c in store.list_campaigns(root=tmp_path)] == [cid]


def test_list_campaigns_newest_first(tmp_path):
    older = "2026-06-16T09-00-00_quant_a"
    newer = "2026-06-16T19-40-00_quant_b"
    store.write_manifest(older, {"schema": "quant.v1"}, root=tmp_path)
    store.write_manifest(newer, {"schema": "quant.v1"}, root=tmp_path)
    # a stray dir without a manifest must be ignored
    (tmp_path / "not-a-campaign").mkdir()
    assert [c["campaign_id"] for c in store.list_campaigns(root=tmp_path)] == [newer, older]


def test_get_campaign_missing_returns_none(tmp_path):
    assert store.get_campaign("nope", root=tmp_path) is None
    assert store.list_campaigns(root=tmp_path) == []
