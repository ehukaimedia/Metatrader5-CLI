"""Tests for mt5_cli/mql5/scaffold.py - create new MQL5 sources from templates."""
from pathlib import Path

from mt5_cli.mql5 import scaffold


def test_scaffold_ea_writes_minimal_file(tmp_path):
    out = scaffold.create_ea("alpha", target_dir=tmp_path)
    assert out["ok"] is True
    src = Path(out["data"]["source"])
    assert src.exists()
    text = src.read_text()
    assert "alpha.mq5" in text
    assert "{{name}}" not in text


def test_scaffold_ea_writes_compilable_skeleton(tmp_path):
    """The minimal EA must have OnInit / OnDeinit / OnTick stubs so it
    loads in MT5 without further authoring."""
    out = scaffold.create_ea("alpha", target_dir=tmp_path)
    text = Path(out["data"]["source"]).read_text()
    assert "OnInit" in text
    assert "OnDeinit" in text
    assert "OnTick" in text


def test_scaffold_ea_refuses_overwrite(tmp_path):
    (tmp_path / "alpha.mq5").write_text("// existing")
    out = scaffold.create_ea("alpha", target_dir=tmp_path)
    assert out["ok"] is False
    assert out["error"]["code"] == "ALREADY_EXISTS"


def test_scaffold_indicator_writes_minimal_file(tmp_path):
    out = scaffold.create_indicator("rsi_dual", target_dir=tmp_path)
    assert out["ok"] is True
    text = Path(out["data"]["source"]).read_text()
    assert "rsi_dual" in text
    assert "{{name}}" not in text


def test_scaffold_indicator_writes_compilable_skeleton(tmp_path):
    """The minimal indicator must have OnInit + OnCalculate stubs."""
    out = scaffold.create_indicator("alpha", target_dir=tmp_path)
    text = Path(out["data"]["source"]).read_text()
    assert "OnInit" in text
    assert "OnCalculate" in text


def test_scaffold_rejects_unknown_template(tmp_path):
    out = scaffold.create_ea("alpha", target_dir=tmp_path, template="scalper")
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_TEMPLATE"


def test_scaffold_creates_target_dir_if_missing(tmp_path):
    """target_dir does not exist yet → scaffold creates it."""
    out_dir = tmp_path / "fresh" / "ea"
    out = scaffold.create_ea("alpha", target_dir=out_dir)
    assert out["ok"] is True
    assert out_dir.exists()


def test_list_templates_returns_minimal_only():
    """Locked decision: ship ONE minimal template per asset type.
    No scalper/swing/oscillator/overlay variants."""
    out = scaffold.list_templates()
    assert out == {
        "ea": ["ea_minimal.mq5"],
        "indicator": ["indicator_minimal.mq5"],
    }
