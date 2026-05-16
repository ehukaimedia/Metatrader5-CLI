"""CLI smoke tests for `mt5 ea ...` and `mt5 indicator ...` groups.

These tests exercise the click plumbing for the Phase 3b MQL5 groups
without requiring a real metaeditor64.exe or MT5 terminal data dir.
The library tests in tests/test_mql5_*.py cover the underlying
compiler/deployer/discovery/scaffold logic.
"""
import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner


def _purge_cli_cache():
    for name in list(sys.modules):
        if name == "mt5.cli" or name == "mt5.emit":
            sys.modules.pop(name, None)


@pytest.fixture
def cli(monkeypatch):
    """CliRunner + isolated mt5.cli. Patches mql5.discovery._search_paths
    to point at a fresh tmp dir so list/get never see the user's real
    ~/.local/share/metatrader5-cli/."""
    _purge_cli_cache()
    from mt5.cli import main
    yield CliRunner(), main, monkeypatch
    _purge_cli_cache()


def test_ea_list_returns_envelope_with_empty_list_when_no_search_paths(cli):
    runner, main, mp = cli
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "_search_paths", lambda kind: [])
    result = runner.invoke(main, ["--json", "ea", "list"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"] == []


def test_ea_new_then_list_finds_the_scaffolded_ea(cli, tmp_path):
    runner, main, mp = cli
    target = tmp_path / "ea"
    res1 = runner.invoke(main, ["--json", "ea", "new", "smoke_alpha",
                                "--target-dir", str(target)])
    assert res1.exit_code == 0
    env = json.loads(res1.output)
    assert env["ok"] is True
    assert (target / "smoke_alpha.mq5").exists()

    # Wire discovery to the scaffold target so `list` picks it up
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "_search_paths", lambda kind: [target])

    res2 = runner.invoke(main, ["--json", "ea", "list"])
    env2 = json.loads(res2.output)
    names = [e["name"] for e in env2["data"]]
    assert "smoke_alpha" in names


def test_ea_new_unknown_template_returns_fail_envelope(cli, tmp_path):
    runner, main, _ = cli
    result = runner.invoke(main, ["--json", "ea", "new", "alpha",
                                  "--template", "scalper",
                                  "--target-dir", str(tmp_path)])
    # Contract: exit 0 + structured envelope, NOT click usage error
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "UNKNOWN_TEMPLATE"


def test_ea_compile_unknown_returns_fail_envelope(cli, monkeypatch):
    runner, main, mp = cli
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "_search_paths", lambda kind: [])
    result = runner.invoke(main, ["--json", "ea", "compile",
                                  "does_not_exist_xyz"])
    assert result.exit_code == 0  # envelope contract: always exit 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "EA_NOT_FOUND"


def test_ea_compile_routes_to_compiler_for_known_ea(cli, tmp_path, monkeypatch):
    """Verify the CLI threads the discovered .mq5 path into compile_source."""
    runner, main, mp = cli
    src = tmp_path / "alpha.mq5"
    src.write_text("// stub")

    from mt5_cli.mql5 import discovery, compiler
    mp.setattr(
        discovery, "get_ea",
        lambda name: {"name": name, "source": str(src), "compiled": False},
    )
    captured = {}

    def fake_compile(path, **kw):
        captured["path"] = Path(path)
        return {"ok": True, "data": {"source": str(path), "ex5": str(path.with_suffix(".ex5"))}}

    mp.setattr(compiler, "compile_source", fake_compile)
    # Re-bind module-level reference inside mt5.cli since the cli imported
    # compile_source via the compiler module attribute access
    import mt5.cli as cli_mod
    mp.setattr(cli_mod, "_mql5_compiler", compiler)

    result = runner.invoke(main, ["--json", "ea", "compile", "alpha"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert captured["path"] == src


def test_ea_deploy_routes_to_deployer_for_known_ea(cli, tmp_path, monkeypatch):
    runner, main, mp = cli
    src = tmp_path / "alpha.mq5"
    src.write_text("// stub")

    from mt5_cli.mql5 import discovery, deployer
    mp.setattr(
        discovery, "get_ea",
        lambda name: {"name": name, "source": str(src), "compiled": True},
    )
    captured = {}

    def fake_deploy(path, *, data_path=None):
        captured["path"] = Path(path)
        captured["data_path"] = data_path
        return {"ok": True, "data": {"copied": [str(path)]}}

    mp.setattr(deployer, "deploy_ea", fake_deploy)
    import mt5.cli as cli_mod
    mp.setattr(cli_mod, "_mql5_deployer", deployer)
    # Force the bridge data-path lookup to return None so the deploy
    # call falls back to deployer's own resolution chain (which the
    # stub above ignores anyway). Avoids needing a real MT5.
    mp.setattr(cli_mod, "_terminal_data_path", lambda cfg: None)

    result = runner.invoke(main, ["--json", "ea", "deploy", "alpha"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert captured["path"] == src


def test_ea_deploy_threads_terminal_data_path_from_bridge(
    cli, tmp_path, monkeypatch,
):
    """When the bridge is connected, the CLI must thread
    terminal_info().data_path into the deployer so the file lands in
    the connected terminal, not whichever install was touched most
    recently."""
    runner, main, mp = cli
    src = tmp_path / "alpha.mq5"
    src.write_text("// stub")

    from mt5_cli.mql5 import discovery, deployer
    mp.setattr(
        discovery, "get_ea",
        lambda name: {"name": name, "source": str(src), "compiled": True},
    )
    captured = {}

    def fake_deploy(path, *, data_path=None):
        captured["data_path"] = data_path
        return {"ok": True, "data": {"copied": []}}

    mp.setattr(deployer, "deploy_ea", fake_deploy)
    import mt5.cli as cli_mod
    mp.setattr(cli_mod, "_mql5_deployer", deployer)
    # Pretend the bridge says the connected terminal's data_path is X
    mp.setattr(cli_mod, "_terminal_data_path",
               lambda cfg: str(tmp_path / "connected_terminal"))

    runner.invoke(main, ["--json", "ea", "deploy", "alpha"])
    assert captured["data_path"] == str(tmp_path / "connected_terminal")


def test_indicator_deploy_threads_data_path_from_bridge(
    cli, tmp_path, monkeypatch,
):
    runner, main, mp = cli
    src = tmp_path / "rsi.mq5"
    src.write_text("// stub")

    from mt5_cli.mql5 import discovery, deployer
    mp.setattr(
        discovery, "get_indicator",
        lambda name: {"name": name, "source": str(src), "compiled": True},
    )
    captured = {}

    def fake_deploy(path, *, data_path=None):
        captured["data_path"] = data_path
        return {"ok": True, "data": {"copied": []}}

    mp.setattr(deployer, "deploy_indicator", fake_deploy)
    import mt5.cli as cli_mod
    mp.setattr(cli_mod, "_mql5_deployer", deployer)
    mp.setattr(cli_mod, "_terminal_data_path",
               lambda cfg: str(tmp_path / "connected_terminal"))

    runner.invoke(main, ["--json", "indicator", "deploy", "rsi"])
    assert captured["data_path"] == str(tmp_path / "connected_terminal")


def test_ea_deploy_unknown_returns_fail_envelope(cli, monkeypatch):
    runner, main, mp = cli
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "get_ea", lambda name: None)
    result = runner.invoke(main, ["--json", "ea", "deploy", "missing_ea"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "EA_NOT_FOUND"


def test_indicator_new_then_list_finds_it(cli, tmp_path):
    runner, main, mp = cli
    target = tmp_path / "indicators"
    res1 = runner.invoke(main, ["--json", "indicator", "new", "smoke_donch",
                                "--target-dir", str(target)])
    assert json.loads(res1.output)["ok"] is True
    assert (target / "smoke_donch.mq5").exists()

    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "_search_paths", lambda kind: [target])
    res2 = runner.invoke(main, ["--json", "indicator", "list"])
    names = [e["name"] for e in json.loads(res2.output)["data"]]
    assert "smoke_donch" in names


def test_indicator_compile_unknown_returns_fail_envelope(cli, monkeypatch):
    runner, main, mp = cli
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "_search_paths", lambda kind: [])
    result = runner.invoke(main, ["--json", "indicator", "compile",
                                  "does_not_exist_xyz"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "INDICATOR_NOT_FOUND"


def test_indicator_deploy_unknown_returns_fail_envelope(cli, monkeypatch):
    runner, main, mp = cli
    from mt5_cli.mql5 import discovery
    mp.setattr(discovery, "get_indicator", lambda name: None)
    result = runner.invoke(main, ["--json", "indicator", "deploy", "missing"])
    env = json.loads(result.output)
    assert env["error"]["code"] == "INDICATOR_NOT_FOUND"


def test_help_lists_ea_and_indicator_groups(cli):
    """The top-level --help must show the new groups."""
    runner, main, _ = cli
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "ea" in result.output.lower()
    assert "indicator" in result.output.lower()
