"""
MT5 CLI configuration module.

Pure Python — no MetaTrader5, no Click, no REPL.
Reads and writes JSON; resolves env vars and runtime overrides.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path("~/.config/cli-anything-mt5.json").expanduser()

DEFAULTS: dict = {
    "login": None,
    "password": None,
    "server": "Trading.com-Demo",
    "timeout": 10000,
    "live": False,
    "magic": 88888,
    "deviation": 20,
    "filling": "auto",
    "max_positions": 5,
    "max_daily_loss": 50.0,
    "max_lot_per_order": 1.0,
    "min_sl_distance_points": 50,
    "max_orders_per_minute": 10,
    "max_spread_points": 30,
    "symbol_allowlist": [],
    "min_free_margin_pct": 20,
    "screenshot_path": "~/mt5-screenshots",
    "screenshot_monitor": 0,
    "allow_hedging": False,
    "strategy_ids": {},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(overrides: dict | None = None) -> dict:
    """Return merged config in resolution order (highest priority wins):

    1. DEFAULTS
    2. JSON file at CONFIG_PATH (if it exists)
    3. Environment variables: MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_LIVE
    4. *overrides* dict (CLI flags — highest priority)
    """
    cfg: dict = dict(DEFAULTS)

    # Layer 2 — JSON file
    if CONFIG_PATH.exists():
        try:
            file_data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                cfg.update(file_data)
        except (json.JSONDecodeError, OSError):
            pass  # silently ignore corrupt / unreadable file

    # Layer 3 — environment variables
    login_env = os.environ.get("MT5_LOGIN")
    if login_env is not None:
        cfg["login"] = int(login_env)

    password_env = os.environ.get("MT5_PASSWORD")
    if password_env is not None:
        cfg["password"] = str(password_env)

    server_env = os.environ.get("MT5_SERVER")
    if server_env is not None:
        cfg["server"] = str(server_env)

    live_env = os.environ.get("MT5_LIVE")
    if live_env is not None:
        cfg["live"] = live_env == "1"

    # Layer 4 — caller overrides (highest priority)
    if overrides is not None:
        cfg.update(overrides)

    return cfg


def save(cfg: dict) -> None:
    """Write *cfg* as pretty-printed JSON to CONFIG_PATH.

    Creates the parent directory if it does not already exist.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def mask_secrets(cfg: dict) -> dict:
    """Return a shallow copy of *cfg* with the 'password' key replaced by '***'.

    The original dict is not modified.
    """
    masked = dict(cfg)
    masked["password"] = "***"
    return masked
