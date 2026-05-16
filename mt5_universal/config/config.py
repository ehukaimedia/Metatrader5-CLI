"""4-layer settings resolution: DEFAULTS -> file -> env -> CLI overrides.

Path resolution (where the config file lives) is intentionally simple here.
Phase 6 swaps in the full XDG_CONFIG_HOME / APPDATA / HOME resolver from
config/paths.py.
"""
import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Connection
    "server": "Trading.comMarkets-MT5",
    "login": None,
    "password": None,
    "live": False,

    # Order placement defaults (Task 2.5 will add Trading.com-specific
    # overrides via trading_com.TRADING_COM_DEFAULTS merged here)
    "magic": 88888,
    "deviation": 20,
    "filling": "auto",   # _resolve_filling translates "auto" to FOK for Trading.com

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
    return home / ".config" / "cli-anything-mt5.json"


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
    """Return a copy of cfg with sensitive fields redacted (for logging / display)."""
    masked = dict(cfg)
    if masked.get("password"):
        masked["password"] = "***"
    return masked
