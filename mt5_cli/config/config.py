"""4-layer settings resolution: DEFAULTS -> file -> env -> CLI overrides.

Path resolution (where the config file lives) is intentionally simple here:
the config file is located under the user's home directory unless
overridden by the MT5_CONFIG environment variable.
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
    """Resolve config file path from MT5_CONFIG or the user's home directory."""
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
            parsed = json.loads(path.read_text())
            # json.loads can return a scalar / list / null for valid-but-
            # wrong-shaped JSON (file contents like `42` or `[1,2,3]`).
            # cfg.update() requires a mapping; silently skip the file
            # layer when the parse result is not a dict, same fall-back
            # as the corrupt-syntax case. Agents should not crash on a
            # bad config file edit.
            if isinstance(parsed, dict):
                cfg.update(parsed)
        except (OSError, ValueError):
            pass
    for env_key, (cfg_key, caster) in ENV_MAP.items():
        if env_key in os.environ:
            cfg[cfg_key] = caster(os.environ[env_key])
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def save(cfg: dict[str, Any], *, include_password: bool = False) -> None:
    """Write the config dict to the resolved config file path.

    For safety, the broker ``password`` is NOT written by default — pass
    ``include_password=True`` to override (you then own the plaintext-on-disk
    risk; prefer the ``MT5_PASSWORD`` environment variable instead). The file is
    created with owner-only permissions (0o600) on POSIX; on Windows, file ACLs
    differ and are not adjusted here.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = dict(cfg)
    if not include_password:
        to_write.pop("password", None)
    path.write_text(json.dumps(to_write, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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
