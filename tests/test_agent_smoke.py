"""Process-level smoke tests for the agent contract.

Unlike test_cli.py (in-process CliRunner), these spawn the real CLI as a
subprocess — exactly how an agent shells out — and prove the contracted
properties hold end to end without an MT5 terminal:

- the process exits 0 on success AND on failure
- stdout is exactly one parseable JSON envelope (clean protocol channel)
- ``--json`` works in any position
- the error path returns a structured {ok: false, error: {code, message}}

No terminal, no network: ``describe`` is a static catalog, and ``tester show``
with an unknown run id fails deterministically from an empty work dir.
"""
import json
import subprocess
import sys


def _run_mt5(*args: str, cwd=None) -> tuple[int, dict, str]:
    """Run ``python -m mt5 <args...>`` and return (exit_code, envelope, stderr).

    Parsing the FULL stdout as one JSON document is the assertion that the
    protocol channel is clean — any stray print would make json.loads fail.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "mt5", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        timeout=60,
    )
    envelope = json.loads(completed.stdout)
    return completed.returncode, envelope, completed.stderr


def test_describe_emits_envelope_and_exits_zero():
    code, env, _ = _run_mt5("--json", "describe")
    assert code == 0
    assert env["ok"] is True
    assert len(env["data"]["commands"]) > 0
    assert len(env["data"]["error_codes"]) > 0


def test_json_flag_works_in_any_position():
    code_lead, env_lead, _ = _run_mt5("--json", "describe")
    code_trail, env_trail, _ = _run_mt5("describe", "--json")
    assert code_lead == code_trail == 0
    assert env_lead == env_trail


def test_error_path_is_structured_and_exits_zero(tmp_path):
    code, env, _ = _run_mt5("--json", "tester", "show", "no-such-run", cwd=tmp_path)
    assert code == 0
    assert env["ok"] is False
    assert env["error"]["code"] == "RUN_NOT_FOUND"
    assert env["error"]["message"]
