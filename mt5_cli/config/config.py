"""4-layer settings resolution: DEFAULTS -> file -> env -> CLI overrides.

Path resolution (where the config file lives) is intentionally simple here.
Phase 6 swaps in the full XDG_CONFIG_HOME / APPDATA / HOME resolver from
config/paths.py.
"""
import json
import os
from pathlib import Path
from typing import Any

from .trading_com import TRADING_COM_DEFAULTS

DEFAULTS: dict[str, Any] = {
    # Connection
    "server": "Trading.comMarkets-MT5",
    "login": None,
    "password": None,
    "live": False,

    # Order placement defaults - Trading.com-specific values from
    # TRADING_COM_DEFAULTS (filling=FOK, allow_hedging=False,
    # rollover_utc_hour=22) are merged in at the end of this dict.
    "magic": 88888,
    "deviation": 20,

    # Risk-gate thresholds
    "max_positions": 5,
    "max_daily_loss": 2000.0,
    "max_lot_per_order": 2.5,
    "min_sl_distance_points": 50,
    "max_spread_points": 80,
    "min_free_margin_pct": 20,
    "max_orders_per_minute": 10,

    # Behaviors
    "symbol_allowlist": [],
    "allow_hedging": False,
    "strategy_ids": {},

    # Trading.com broker-specific defaults (single-broker scope).
    # The spread re-asserts allow_hedging=False (no-op merge), adds
    # filling="FOK", and adds rollover_utc_hour=22. There is intentionally
    # no literal "filling" key above; the broker policy is the only source.
    **TRADING_COM_DEFAULTS,
}

ENV_MAP: dict[str, tuple[str, Any]] = {
    "MT5_LOGIN": ("login", int),
    "MT5_PASSWORD": ("password", str),
    "MT5_SERVER": ("server", str),
    "MT5_LIVE": ("live", lambda s: s == "1"),
}


def _config_path() -> Path:
    """Resolve config file path. Phase 6 swaps in the full XDG/APPDATA resolver."""
    if "MT5_CONFIG" in os.environ:
        return Path(os.environ["MT5_CONFIG"])
    home = Path(os.path.expanduser("~"))
    return home / ".config" / "metatrader5-cli.json"


def load(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve the active config by merging DEFAULTS, file, env, and overrides.

    Precedence (highest wins): overrides > env > file > DEFAULTS.
    Corrupt JSON file silently falls back to defaults (do not raise — agents
    operating live should not crash because of a bad config file edit).
    """
    cfg = dict(DEFAULTS)
    path = _config_path()
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
    for env_key, (cfg_key, caster) in ENV_MAP.items():
        if env_key in os.environ:
            cfg[cfg_key] = caster(os.environ[env_key])
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def save(cfg: dict[str, Any]) -> None:
    """Write the config dict to the resolved config file path."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))


def mask_secrets(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of cfg with sensitive fields redacted (for logging / display).

    Redacts both `password` and `login`. The login is an MT5 account number
    that uniquely identifies the user to the broker - treating it as a
    secret prevents accidental disclosure in transcripts, logs, screenshots,
    and bug reports.
    """
    masked = dict(cfg)
    if masked.get("password"):
        masked["password"] = "***"
    if masked.get("login") is not None:
        masked["login"] = "***"
    return masked
