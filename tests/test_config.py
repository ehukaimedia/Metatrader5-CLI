import pytest

from mt5_cli.config import load, save, mask_secrets


@pytest.fixture
def clean_env(monkeypatch):
    """Strip MT5_* env vars so they don't bleed from the host environment."""
    for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
        monkeypatch.delenv(k, raising=False)


def test_defaults_when_nothing_overrides(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    cfg = load()
    assert cfg["live"] is False
    assert cfg["magic"] == 88888
    assert cfg["max_positions"] == 5
    assert cfg["server"] == "Trading.comMarkets-MT5"
    # broker_profile is intentionally NOT in cfg — single-broker scope
    assert "broker_profile" not in cfg


def test_file_overrides_defaults(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"max_positions": 7, "max_lot_per_order": 1.0}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = load()
    assert cfg["max_positions"] == 7
    assert cfg["max_lot_per_order"] == 1.0


def test_env_overrides_file(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"login": 11111, "server": "FileServer"}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    monkeypatch.setenv("MT5_SERVER", "EnvServer")
    cfg = load()
    assert cfg["login"] == 22222
    assert cfg["server"] == "EnvServer"


def test_overrides_arg_takes_highest_precedence(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    cfg = load(overrides={"login": 33333})
    assert cfg["login"] == 33333


def test_overrides_None_is_skipped(clean_env, tmp_path, monkeypatch):
    """overrides={'login': None} should NOT clobber the env-resolved value."""
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    cfg = load(overrides={"login": None})
    assert cfg["login"] == 22222


def test_corrupt_json_file_falls_back_to_defaults(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "bad.json"
    cfg_path.write_text("{this is not json")
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = load()
    # Falls back to defaults, doesn't raise
    assert cfg["max_positions"] == 5


@pytest.mark.parametrize("payload", ["42", "null", "true", '"a string"', "[1, 2, 3]"])
def test_valid_but_non_object_json_falls_back_to_defaults(
    clean_env, tmp_path, monkeypatch, payload
):
    """Codex P2 #4: valid JSON of the wrong shape (scalar / list / null)
    must fall through to DEFAULTS the same way corrupt JSON does.
    cfg.update() would TypeError on non-mapping values; load() must
    skip the file layer instead so agents don't crash on a bad edit."""
    cfg_path = tmp_path / "wrong_shape.json"
    cfg_path.write_text(payload)
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = load()  # must not raise
    # Falls back to defaults
    assert cfg["max_positions"] == 5
    assert cfg["magic"] == 88888


def test_mask_secrets_redacts_password_and_login(clean_env):
    """Both password and login must be redacted - the login is an MT5
    account number that uniquely identifies the user to the broker."""
    cfg = {"login": 12345, "password": "supersecret", "server": "X"}
    masked = mask_secrets(cfg)
    assert masked["password"] == "***"
    assert masked["login"] == "***"
    assert masked["server"] == "X"


def test_mask_secrets_handles_no_password(clean_env):
    cfg = {"login": 12345, "server": "X"}  # no password
    masked = mask_secrets(cfg)
    assert "password" not in masked or masked.get("password") is None
    # Login is still redacted even when password is absent
    assert masked["login"] == "***"


def test_mask_secrets_does_not_mutate_input(clean_env):
    """mask_secrets must return a copy; never mutate caller's cfg."""
    cfg = {"login": 12345, "password": "secret"}
    mask_secrets(cfg)
    assert cfg["login"] == 12345
    assert cfg["password"] == "secret"


def test_save_writes_json(clean_env, tmp_path, monkeypatch):
    import json
    cfg_path = tmp_path / "saved.json"
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = {"max_positions": 9, "max_lot_per_order": 0.5}
    save(cfg)
    assert cfg_path.exists()
    loaded = json.loads(cfg_path.read_text())
    assert loaded["max_positions"] == 9


def test_live_env_var_parsed_as_bool(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MT5_LIVE", "1")
    cfg = load()
    assert cfg["live"] is True


def test_live_env_var_other_value_is_false(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MT5_LIVE", "0")
    cfg = load()
    assert cfg["live"] is False
