"""Tests for mt5_universal/config/trading_com.py and its merge into config.py.

Task 2.5: Trading.com order-placement settings (single-broker).
No BrokerProfile abstraction - single-broker scope per user direction.
"""
import pytest

from mt5_universal.config import load
from mt5_universal.config.trading_com import (
    TRADING_COM_DEFAULTS,
    retcode_help as _retcode_help,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip MT5_* env vars so host env doesn't bleed into load()."""
    for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
        monkeypatch.delenv(k, raising=False)


def test_trading_com_defaults_shape():
    assert TRADING_COM_DEFAULTS["filling"] == "FOK"
    assert TRADING_COM_DEFAULTS["allow_hedging"] is False
    assert TRADING_COM_DEFAULTS["rollover_utc_hour"] == 22


def test_retcode_help_returns_string():
    msg = _retcode_help(10030)
    assert "filling" in msg.lower()
    assert "FOK" in msg


def test_retcode_help_unknown_falls_back():
    msg = _retcode_help(99999)
    assert "99999" in msg


def test_config_load_merges_trading_com_defaults(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    cfg = load()
    assert cfg["filling"] == "FOK"
    assert cfg["allow_hedging"] is False
    assert cfg["rollover_utc_hour"] == 22


def test_retcode_help_importable_from_config_package():
    from mt5_universal.config import retcode_help
    assert callable(retcode_help)
    result = retcode_help(10030)
    assert isinstance(result, str)
    assert "FOK" in result
