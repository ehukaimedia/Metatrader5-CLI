"""Alert wake contracts for agent workflows.

This module turns MT5 alert definitions into structured wake events. It is a
first implementation slice: notification, ask-permission, and dry-run decisions
are supported; live autonomous mutation is intentionally blocked.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_cli import alert as _alert
from mt5_cli import orders as _orders
from mt5_cli.reports import fail, ok

VALID_PERMISSION_MODES = {
    "notify_only",
    "ask_permission",
    "auto_dryrun",
    "auto_trade",
}

SUPPORTED_TRADE_ACTIONS = {
    "place_market": "market",
    "place_limit": "limit",
    "place_stop": "stop",
}

SUPPORTED_ADAPTERS = {
    "audit",
    "stdout",
    "mt5_push",
    "codex",
    "claude",
    "antigravity",
}

DEFAULT_POLICY = {
    "id": "default-notify-only",
    "enabled": True,
    "match": {"source": "mt5.alert"},
    "permission_mode": "notify_only",
    "adapters": ["audit"],
    "limits": {},
}

DryrunFunc = Callable[..., dict]


def load_policies(policy_path: str | None = None, cfg: dict | None = None) -> dict:
    """Load and validate wake policies from JSON or effective config.

    The JSON shape can be either ``{"wake_policies": [...]}`` or a bare list.
    With no configured policies, a safe notify-only default is returned.
    """
    source = "default"
    raw: Any = None
    if policy_path:
        source = "file"
        path = Path(policy_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            return fail("WAKE_POLICY_INVALID", f"Could not read wake policy file: {exc}")
        except ValueError as exc:
            return fail("WAKE_POLICY_INVALID", f"Wake policy file is not valid JSON: {exc}")
    elif cfg and "wake_policies" in cfg:
        source = "config"
        raw = {"wake_policies": cfg.get("wake_policies")}

    policies_raw: Any
    if raw is None:
        policies_raw = [dict(DEFAULT_POLICY)]
    elif isinstance(raw, list):
        policies_raw = raw
    elif isinstance(raw, dict):
        policies_raw = raw.get("wake_policies")
    else:
        return fail("WAKE_POLICY_INVALID", "Wake policy root must be an object or list.")

    if not isinstance(policies_raw, list):
        return fail("WAKE_POLICY_INVALID", "wake_policies must be a list.")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for index, policy in enumerate(policies_raw):
        env = _normalize_policy(policy, index)
        if not env.get("ok"):
            return env
        policy_data = env["data"]
        policy_id = policy_data["id"]
        if policy_id in seen_ids:
            return fail("WAKE_POLICY_INVALID", f"Duplicate wake policy id: {policy_id!r}.")
        seen_ids.add(policy_id)
        normalized.append(policy_data)

    return ok({"source": source, "policies": normalized})


def watch_alerts(
    alerts_path: str | None = None,
    *,
    cfg: dict | None = None,
    data_path: str | None = None,
    policy_path: str | None = None,
    state_path: str | None = None,
    audit_path: str | None = None,
    mt5_push_queue_path: str | None = None,
    iterations: int = 1,
    poll_seconds: float = 5.0,
    is_live_intent: bool = False,
    dryrun_func: DryrunFunc | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict:
    """Poll MT5 terminal alerts and emit structured wake decisions.

    ``iterations`` lets callers run a bounded watch loop. The CLI defaults to a
    single pass so commands keep the repo's one-envelope stdout contract.
    """
    cfg = cfg or {}
    if iterations < 1:
        return fail("MT5_INVALID_PARAMS", "iterations must be >= 1.")
    if poll_seconds < 0:
        return fail("MT5_INVALID_PARAMS", "poll_seconds must be >= 0.")

    policies_env = load_policies(policy_path, cfg)
    if not policies_env.get("ok"):
        return policies_env
    policies = policies_env["data"]["policies"]

    state_file = _resolve_state_path(state_path)
    audit_file = _resolve_audit_path(audit_path)
    push_queue_file = _resolve_push_queue_path(mt5_push_queue_path)
    state_env = _load_state(state_file)
    if not state_env.get("ok"):
        return state_env
    seen = set(state_env["data"].get("seen", []))

    dryrun = dryrun_func or _orders.dryrun
    clock = now or (lambda: datetime.now(timezone.utc))
    emitted: list[dict] = []
    listed_data: dict | None = None

    for iteration in range(iterations):
        listed = _alert.list_alerts(
            alerts_path=alerts_path,
            cfg=cfg,
            data_path=data_path,
        )
        if not listed.get("ok"):
            return listed
        listed_data = listed["data"]
        for record in listed_data.get("alerts", []):
            event = _build_wake_event(record, listed_data, cfg, clock())
            dedupe_key = event["dedupe_key"]
            if dedupe_key in seen:
                continue
            policy = _match_policy(event, policies)
            if policy is None:
                policy = dict(DEFAULT_POLICY)
            event["policy_id"] = policy["id"]
            event["permission_mode"] = policy["permission_mode"]
            trade_intent = _build_trade_intent(event, policy)
            event["proposed_action"] = trade_intent
            event["agent_prompt"] = _build_agent_prompt(event, trade_intent)
            execution = _execute_policy(
                event,
                policy,
                cfg=cfg,
                is_live_intent=is_live_intent,
                dryrun_func=dryrun,
            )
            adapters = _run_adapters(event, policy, execution, push_queue_file)
            audit_env = _write_audit(audit_file, event, policy, execution, adapters)
            if not audit_env.get("ok"):
                return audit_env
            event["execution"] = execution
            event["adapters"] = adapters
            emitted.append(event)
            seen.add(dedupe_key)
        if iteration < iterations - 1:
            time.sleep(poll_seconds)

    saved = _save_state(state_file, seen)
    if not saved.get("ok"):
        return saved
    return ok(
        {
            "schema": "wake_watch.v1",
            "count": len(emitted),
            "events": emitted,
            "policy_source": policies_env["data"]["source"],
            "state_path": str(state_file),
            "audit_path": str(audit_file),
            "mt5_push_queue_path": str(push_queue_file),
            "alert_count": None if listed_data is None else listed_data.get("count"),
        }
    )


def _normalize_policy(policy: Any, index: int) -> dict:
    if not isinstance(policy, dict):
        return fail("WAKE_POLICY_INVALID", f"Policy #{index} must be an object.")
    policy_id = policy.get("id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        return fail("WAKE_POLICY_INVALID", f"Policy #{index} needs a non-empty id.")
    match = policy.get("match", {})
    if not isinstance(match, dict):
        return fail("WAKE_POLICY_INVALID", f"Policy {policy_id!r} match must be an object.")
    permission_mode = policy.get("permission_mode", "notify_only")
    if permission_mode not in VALID_PERMISSION_MODES:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} has invalid permission_mode {permission_mode!r}.",
        )
    enabled = policy.get("enabled", True)
    if not isinstance(enabled, bool):
        return fail("WAKE_POLICY_INVALID", f"Policy {policy_id!r} enabled must be true or false.")
    adapters = policy.get("adapters", ["audit"])
    if not isinstance(adapters, list) or not all(isinstance(a, str) for a in adapters):
        return fail("WAKE_POLICY_INVALID", f"Policy {policy_id!r} adapters must be a list of strings.")
    unsupported = sorted(set(adapters) - SUPPORTED_ADAPTERS)
    if unsupported:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} has unsupported adapters: {', '.join(unsupported)}.",
        )
    limits = policy.get("limits", {})
    if not isinstance(limits, dict):
        return fail("WAKE_POLICY_INVALID", f"Policy {policy_id!r} limits must be an object.")
    limits_env = _normalize_limits(policy_id, limits)
    if not limits_env.get("ok"):
        return limits_env
    trade_template = policy.get("trade_template")
    if trade_template is not None:
        env = _validate_trade_template(policy_id, trade_template)
        if not env.get("ok"):
            return env
    if permission_mode in {"auto_dryrun", "auto_trade"} and trade_template is None:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} requires trade_template for {permission_mode}.",
        )
    return ok(
        {
            "id": policy_id,
            "enabled": enabled,
            "match": dict(match),
            "permission_mode": permission_mode,
            "adapters": list(adapters),
            "limits": limits_env["data"],
            "trade_template": dict(trade_template) if trade_template is not None else None,
        }
    )


def _normalize_limits(policy_id: str, limits: dict) -> dict:
    normalized = dict(limits)
    allowed_symbols = normalized.get("allowed_symbols")
    if allowed_symbols is not None:
        if (
            not isinstance(allowed_symbols, list)
            or not all(isinstance(symbol, str) for symbol in allowed_symbols)
        ):
            return fail(
                "WAKE_POLICY_INVALID",
                f"Policy {policy_id!r} limits.allowed_symbols must be a list of strings.",
            )
    max_volume = normalized.get("max_volume")
    if max_volume is not None:
        try:
            normalized["max_volume"] = float(max_volume)
        except (TypeError, ValueError):
            return fail(
                "WAKE_POLICY_INVALID",
                f"Policy {policy_id!r} limits.max_volume must be numeric.",
            )
        if normalized["max_volume"] <= 0:
            return fail(
                "WAKE_POLICY_INVALID",
                f"Policy {policy_id!r} limits.max_volume must be > 0.",
            )
    return ok(normalized)


def _validate_trade_template(policy_id: str, template: Any) -> dict:
    if not isinstance(template, dict):
        return fail("WAKE_POLICY_INVALID", f"Policy {policy_id!r} trade_template must be an object.")
    action = template.get("action")
    if action not in SUPPORTED_TRADE_ACTIONS:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} trade_template action must be one of: "
            f"{', '.join(sorted(SUPPORTED_TRADE_ACTIONS))}.",
        )
    for required in ("side", "volume", "sl"):
        if required not in template:
            return fail(
                "WAKE_POLICY_INVALID",
                f"Policy {policy_id!r} trade_template requires {required!r}.",
            )
    if str(template.get("side")).lower() not in {"buy", "sell"}:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} trade_template side must be 'buy' or 'sell'.",
        )
    for field in ("volume", "sl", "tp"):
        if field in template and _as_float(template.get(field)) is None:
            return fail(
                "WAKE_POLICY_INVALID",
                f"Policy {policy_id!r} trade_template {field!r} must be numeric.",
            )
    if action in {"place_limit", "place_stop"} and "price" not in template:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} {action} trade_template requires 'price'.",
        )
    if "price" in template and _as_float(template.get("price")) is None:
        return fail(
            "WAKE_POLICY_INVALID",
            f"Policy {policy_id!r} trade_template 'price' must be numeric.",
        )
    return ok({"valid": True})


def _build_wake_event(record: dict, listed_data: dict, cfg: dict, observed_at: datetime) -> dict:
    source_text = record.get("source") or ""
    symbol = record.get("symbol") or ""
    condition = record.get("condition") or ""
    price = record.get("price")
    dedupe_material = "|".join(
        [
            str(listed_data.get("path", "")),
            str(record.get("id", "")),
            symbol,
            condition,
            _stable_price(price),
            source_text,
        ]
    )
    dedupe_key = hashlib.sha256(dedupe_material.encode("utf-8")).hexdigest()
    return {
        "schema": "wake.v1",
        "event_id": f"wake-{dedupe_key[:16]}",
        "dedupe_key": dedupe_key,
        "source": "mt5.alert",
        "observed_at": observed_at.isoformat(),
        "terminal": {
            "alerts_path": listed_data.get("path"),
            "resolved_via": listed_data.get("resolved_via"),
            "server": cfg.get("server"),
        },
        "account": {
            "login_configured": cfg.get("login") is not None,
            "login": "***" if cfg.get("login") is not None else None,
        },
        "symbol": symbol,
        "trigger": {
            "kind": "price",
            "condition": condition,
            "price": price,
            "source_text": source_text,
            "condition_code": record.get("condition_code"),
            "alert_id": record.get("id"),
        },
    }


def _stable_price(price: Any) -> str:
    try:
        return f"{float(price):.10f}"
    except (TypeError, ValueError):
        return str(price)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_policy(event: dict, policies: list[dict]) -> dict | None:
    for policy in policies:
        if not policy.get("enabled", True):
            continue
        match = policy.get("match", {})
        if _event_matches(event, match):
            return policy
    return None


def _event_matches(event: dict, match: dict) -> bool:
    fields = {
        "source": event.get("source"),
        "symbol": event.get("symbol"),
        "condition": event.get("trigger", {}).get("condition"),
        "source_text": event.get("trigger", {}).get("source_text"),
    }
    return all(fields.get(key) == value for key, value in match.items() if value is not None)


def _build_trade_intent(event: dict, policy: dict) -> dict | None:
    template = policy.get("trade_template")
    if template is None:
        return None
    intent = dict(template)
    action = intent["action"]
    intent.setdefault("schema", "trade_intent.v1")
    intent.setdefault("symbol", event.get("symbol"))
    intent.setdefault("order_type", SUPPORTED_TRADE_ACTIONS[action])
    intent.setdefault("client_order_id", event["event_id"])
    intent.setdefault("comment", f"wake {policy['id']}")
    return intent


def _execute_policy(
    event: dict,
    policy: dict,
    *,
    cfg: dict,
    is_live_intent: bool,
    dryrun_func: DryrunFunc,
) -> dict:
    mode = policy["permission_mode"]
    intent = event.get("proposed_action")
    dryrun_env = None
    if intent is not None:
        limits_env = _check_intent_limits(intent, policy.get("limits", {}))
        if not limits_env.get("ok"):
            return {"decision": "policy_blocked", "dryrun": limits_env, "mutation": None}
    if mode in {"ask_permission", "auto_dryrun", "auto_trade"} and intent is not None:
        dryrun_env = _dryrun_trade_intent(intent, cfg, is_live_intent, dryrun_func)

    if mode == "notify_only":
        return {"decision": "notified", "dryrun": None, "mutation": None}
    if mode == "ask_permission":
        return {
            "decision": "permission_required",
            "dryrun": dryrun_env,
            "mutation": None,
        }
    if mode == "auto_dryrun":
        return {
            "decision": "dryrun_passed" if dryrun_env and dryrun_env.get("ok") else "dryrun_failed",
            "dryrun": dryrun_env,
            "mutation": None,
        }

    # auto_trade is deliberately specified but not enabled in this first slice.
    if dryrun_env and not dryrun_env.get("ok"):
        return {"decision": "dryrun_failed", "dryrun": dryrun_env, "mutation": None}
    return {
        "decision": "autonomous_blocked",
        "dryrun": dryrun_env,
        "mutation": fail(
            "WAKE_AUTONOMOUS_BLOCKED",
            "auto_trade is specified but live mutation is not implemented in this first slice.",
        ),
    }


def _check_intent_limits(intent: dict, limits: dict) -> dict:
    allowed_symbols = limits.get("allowed_symbols")
    if allowed_symbols and intent.get("symbol") not in allowed_symbols:
        return fail(
            "RISK_SYMBOL_NOT_ALLOWED",
            f"Wake policy does not allow symbol {intent.get('symbol')!r}.",
            data={"allowed_symbols": allowed_symbols},
        )
    max_volume = limits.get("max_volume")
    volume = _as_float(intent.get("volume"))
    if volume is None:
        return fail(
            "WAKE_POLICY_INVALID",
            "Wake trade intent volume must be numeric.",
        )
    if max_volume is not None and volume > float(max_volume):
        return fail(
            "RISK_MAX_LOT_EXCEEDED",
            "Wake policy max_volume blocks this trade intent.",
            data={"max_volume": max_volume, "volume": volume},
        )
    return ok({"allowed": True})


def _dryrun_trade_intent(
    intent: dict,
    cfg: dict,
    is_live_intent: bool,
    dryrun_func: DryrunFunc,
) -> dict:
    action = intent.get("action")
    if not isinstance(action, str):
        return fail("WAKE_POLICY_INVALID", "Wake trade intent action must be a string.")
    order_type = SUPPORTED_TRADE_ACTIONS.get(action)
    if order_type is None:
        return fail("WAKE_POLICY_INVALID", f"Unsupported trade action: {action!r}.")
    volume = _as_float(intent.get("volume"))
    sl = _as_float(intent.get("sl"))
    if volume is None or sl is None:
        return fail("WAKE_POLICY_INVALID", "Wake trade intent volume and sl must be numeric.")
    return dryrun_func(
        symbol=intent.get("symbol"),
        side=intent.get("side"),
        order_type=order_type,
        price=_as_float(intent.get("price")) if intent.get("price") is not None else None,
        volume=volume,
        sl=sl,
        tp=_as_float(intent.get("tp")) if intent.get("tp") is not None else None,
        strategy_id=intent.get("strategy_id"),
        filling=intent.get("filling", "auto"),
        cfg=cfg,
        is_live_intent=is_live_intent,
    )


def _run_adapters(
    event: dict,
    policy: dict,
    execution: dict,
    push_queue_file: Path,
) -> list[dict]:
    results: list[dict] = []
    for adapter in policy.get("adapters", ["audit"]):
        if adapter == "audit":
            results.append({"name": "audit", "ok": True, "mode": "jsonl"})
        elif adapter == "stdout":
            results.append({"name": "stdout", "ok": True, "mode": "envelope"})
        elif adapter == "mt5_push":
            queued = _queue_mt5_push(push_queue_file, event, execution)
            results.append({"name": "mt5_push", **queued})
        else:
            results.append({"name": adapter, "ok": True, "mode": "prompt_in_payload"})
    return results


def _queue_mt5_push(push_queue_file: Path, event: dict, execution: dict) -> dict:
    message = _mt5_push_message(event, execution)
    record = {
        "schema": "mt5_push_request.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_id": event["event_id"],
        "message": message,
    }
    try:
        push_queue_file.parent.mkdir(parents=True, exist_ok=True)
        with push_queue_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")))
            fh.write("\n")
    except OSError as exc:
        env = fail("MT5_NOTIFICATION_FAILED", f"Could not write MT5 push queue: {exc}")
        return {"ok": False, "error": env["error"]}
    return {"ok": True, "mode": "queued", "path": str(push_queue_file), "message": message}


def _mt5_push_message(event: dict, execution: dict) -> str:
    base = (
        f"MT5 wake {event.get('symbol')} {event.get('trigger', {}).get('condition')} "
        f"{event.get('trigger', {}).get('price')} -> {execution.get('decision')}"
    )
    return base[:255]


def _write_audit(
    audit_file: Path,
    event: dict,
    policy: dict,
    execution: dict,
    adapters: list[dict],
) -> dict:
    record = {
        "schema": "wake_audit.v1",
        "event_id": event["event_id"],
        "dedupe_key": event["dedupe_key"],
        "policy_id": policy["id"],
        "permission_mode": policy["permission_mode"],
        "decision": execution.get("decision"),
        "dryrun": execution.get("dryrun"),
        "mutation": execution.get("mutation"),
        "adapters": adapters,
        "observed_at": event.get("observed_at"),
    }
    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        with audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")))
            fh.write("\n")
    except OSError as exc:
        return fail("WAKE_AUDIT_WRITE_FAILED", f"Could not write wake audit log: {exc}")
    return ok({"path": str(audit_file)})


def _build_agent_prompt(event: dict, intent: dict | None) -> str:
    prompt = [
        f"MT5 wake {event['event_id']} for {event.get('symbol')}.",
        f"Trigger: {event.get('trigger', {}).get('condition')} "
        f"{event.get('trigger', {}).get('price')}.",
        f"Permission mode: {event.get('permission_mode')}.",
    ]
    if intent is not None:
        prompt.append(
            "Review the proposed trade intent, inspect current MT5 account/market state, "
            "and ask the user before any live mutation."
        )
    else:
        prompt.append("Notify the user and inspect state only if requested.")
    return " ".join(prompt)


def _runtime_dir() -> Path:
    if os.environ.get("MT5_WAKE_DIR"):
        return Path(os.environ["MT5_WAKE_DIR"])
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "metatrader5-cli"
    return Path.home() / ".local" / "state" / "metatrader5-cli"


def _resolve_state_path(path: str | None) -> Path:
    if path:
        return Path(path)
    if os.environ.get("MT5_WAKE_STATE_PATH"):
        return Path(os.environ["MT5_WAKE_STATE_PATH"])
    return _runtime_dir() / "wake-state.json"


def _resolve_audit_path(path: str | None) -> Path:
    if path:
        return Path(path)
    if os.environ.get("MT5_WAKE_AUDIT_PATH"):
        return Path(os.environ["MT5_WAKE_AUDIT_PATH"])
    return _runtime_dir() / "wake-audit.jsonl"


def _resolve_push_queue_path(path: str | None) -> Path:
    if path:
        return Path(path)
    if os.environ.get("MT5_PUSH_QUEUE_PATH"):
        return Path(os.environ["MT5_PUSH_QUEUE_PATH"])
    return _runtime_dir() / "mt5-push-queue.jsonl"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return ok({"seen": []})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return fail("WAKE_STATE_READ_ERROR", f"Could not read wake state: {exc}")
    except ValueError as exc:
        return fail("WAKE_STATE_READ_ERROR", f"Wake state is not valid JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("seen", []), list):
        return fail("WAKE_STATE_READ_ERROR", "Wake state must be an object with a seen list.")
    return ok({"seen": [str(item) for item in data.get("seen", [])]})


def _save_state(path: Path, seen: set[str]) -> dict:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"seen": sorted(seen)}, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        return fail("WAKE_STATE_WRITE_FAILED", f"Could not write wake state: {exc}")
    return ok({"path": str(path)})
