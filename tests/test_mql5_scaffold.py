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


def test_scaffold_rejects_parent_traversal(tmp_path):
    """Spock P2 repro: a name containing '..' must NOT escape the
    target dir. Must fail INVALID_NAME and write nothing outside the
    requested directory."""
    target = tmp_path / "ea"
    result = scaffold.create_ea("../outside", target_dir=target)
    assert result["ok"] is False
    assert result["error"]["code"] == "MT5_INVALID_PARAMS"
    # The traversal write must NOT have happened
    assert not (tmp_path / "outside.mq5").exists()


def test_scaffold_rejects_path_separators(tmp_path):
    """Forward slash, backslash, or any path-separator in the name
    must also be rejected (Windows + POSIX path safety)."""
    for bad in ("foo/bar", "foo\\bar", "../../etc/passwd",
                "/abs/path", "name with space"):
        result = scaffold.create_ea(bad, target_dir=tmp_path)
        assert result["ok"] is False, f"name {bad!r} was accepted"
        assert result["error"]["code"] == "MT5_INVALID_PARAMS"


def test_scaffold_rejects_empty_name(tmp_path):
    result = scaffold.create_ea("", target_dir=tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "MT5_INVALID_PARAMS"


def test_scaffold_accepts_safe_names(tmp_path):
    """Letters, digits, underscore, hyphen, starting with letter or
    underscore — must all be accepted."""
    for good in ("alpha", "alpha_v2", "_internal", "a", "ABC-123"):
        out = scaffold.create_ea(good, target_dir=tmp_path / good)
        assert out["ok"] is True, f"name {good!r} was rejected: {out}"


def test_ea_template_is_stubs_only():
    """Locked decision #10: EA template ships OnInit / OnDeinit / OnTick
    stubs only — no `input` parameters, no strategy logic, no
    opinionated comments. Any change that adds an input here regresses
    the hands-not-strategies contract."""
    template_path = (
        scaffold._TEMPLATE_ROOT / scaffold._EA_TEMPLATE
    )
    text = template_path.read_text(encoding="utf-8")
    assert "input " not in text, (
        "EA template must not declare any `input` parameters — locked "
        "decision #10 (hands, not strategies)"
    )
    assert "OnInit" in text
    assert "OnDeinit" in text
    assert "OnTick" in text


def test_list_templates_returns_minimal_only():
    """Locked decision: ship ONE minimal template per asset type.
    No scalper/swing/oscillator/overlay variants."""
    out = scaffold.list_templates()
    assert out == {
        "ea": ["ea_minimal.mq5"],
        "indicator": ["indicator_minimal.mq5"],
    }
