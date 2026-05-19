"""Copy compiled MQL5 artifacts to the MT5 terminal's Experts/ or Indicators/.

Terminal data dir is the per-instance Roaming dir like
%APPDATA%\\MetaQuotes\\Terminal\\<HASH>\\MQL5\\. We pick the newest one
under the candidate root (most recently modified hash dir that has an
MQL5/ subdir) which matches how MT5 keeps state across reinstalls.

Bridge isolation: pure filesystem; never touches the MT5 Python SDK.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from mt5_cli.reports import fail, ok


def _refresh_navigator() -> dict:
    """Thin wrapper so tests can monkeypatch without importing pywin32.

    Imported lazily inside the wrapper so non-Windows test environments
    (and the hermetic-fixture path) never touch Win32 unless the real
    function is actually exercised.
    """
    from mt5_cli.chart.navigator import refresh_navigator as _real  # noqa: PLC0415
    return _real()

# Module-level so tests can monkeypatch via `deployer._CANDIDATE_DATA_DIRS`.
_CANDIDATE_DATA_DIRS: list[Path] = [
    Path(os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal")),
]


def resolve_terminal_data_dir(
    data_path: Path | str | None = None,
) -> tuple[Path | None, str]:
    """Find the active MT5 terminal data dir (the parent of MQL5/).

    Returns (data_dir, resolved_via) where resolved_via is one of:
      'explicit_data_path' - caller passed data_path (typically threaded
                             from bridge.terminal_info().data_path)
      'env_var'            - MT5_TERMINAL_DATA_DIR env var
      'fallback_newest_hash' - last-resort newest-hash-dir scan; may
                             pick the wrong terminal when multiple
                             installs coexist
      'unresolved'         - no candidate reachable (data_dir is None)

    Surfacing how the dir was picked lets callers distinguish a
    deliberate explicit deploy from the fallback heuristic in their
    audit logs.
    """
    if data_path:
        p = Path(data_path)
        return (p, "explicit_data_path") if p.exists() else (None, "unresolved")
    env = os.environ.get("MT5_TERMINAL_DATA_DIR")
    if env:
        p = Path(env)
        return (p, "env_var") if p.exists() else (None, "unresolved")
    for root in _CANDIDATE_DATA_DIRS:
        if not root.exists():
            continue
        # MT5 keeps each terminal install under a 32-char hash dir. Pick the
        # newest one that has an MQL5/ subdir.
        try:
            candidates = sorted(
                (d for d in root.iterdir()
                 if d.is_dir() and (d / "MQL5").exists()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            continue
        if candidates:
            return candidates[0], "fallback_newest_hash"
    return None, "unresolved"


def _deploy(
    src: Path | str,
    subdir: str,
    data_path: Path | str | None = None,
    refresh_navigator: bool = True,
) -> dict:
    """Copy `src` (.mq5) and its sibling `.ex5` (if any) to MQL5/<subdir>/.

    Args:
        src: path to the .mq5 (the .ex5 sibling, if present, is also copied).
        subdir: "Experts" or "Indicators".
        data_path: optional explicit terminal data dir. When given, takes
            precedence over MT5_TERMINAL_DATA_DIR env + the newest-hash-dir
            fallback. The CLI threads this from
            bridge.mt5_call('terminal_info').data_path so the deploy
            targets the connected terminal, not whichever install happens
            to have been touched most recently.

    Failure codes:
      SOURCE_NOT_FOUND              - the .mq5 path does not exist
      TERMINAL_DATA_DIR_NOT_FOUND   - resolve_terminal_data_dir returned None
      DEPLOY_TARGET_NOT_WRITABLE    - mkdir/copy raised OSError
                                      (e.g. MQL5/<subdir> is a file, ACL
                                      denial, disk full)
      NOTHING_TO_DEPLOY             - neither .mq5 nor .ex5 sibling exists
    """
    src = Path(src).resolve()
    if not src.exists():
        return fail("SOURCE_NOT_FOUND", f"Source file not found: {src}")
    data_dir, resolved_via = resolve_terminal_data_dir(data_path)
    if not data_dir:
        return fail(
            "TERMINAL_DATA_DIR_NOT_FOUND",
            "Could not locate MT5 terminal data dir. Connect to MT5 so "
            "the CLI can read terminal_info().data_path, set "
            "MT5_TERMINAL_DATA_DIR, or run MT5 at least once.",
        )
    dest_dir = data_dir / "MQL5" / subdir
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return fail(
            "DEPLOY_TARGET_NOT_WRITABLE",
            f"Could not prepare {dest_dir} for deploy: {exc!r}",
            data={
                "data_dir": str(data_dir),
                "subdir": subdir,
                "resolved_via": resolved_via,
            },
        )
    copied: list[str] = []
    for ext in (".mq5", ".ex5"):
        candidate = src.with_suffix(ext)
        if not candidate.exists():
            continue
        dest = dest_dir / candidate.name
        try:
            shutil.copy2(candidate, dest)
        except OSError as exc:
            return fail(
                "DEPLOY_TARGET_NOT_WRITABLE",
                f"Could not copy {candidate} to {dest}: {exc!r}",
                data={
                    "data_dir": str(data_dir),
                    "subdir": subdir,
                    "resolved_via": resolved_via,
                    "copied_before_failure": copied,
                },
            )
        copied.append(str(dest))
    if not copied:
        return fail(
            "NOTHING_TO_DEPLOY",
            f"Found no .mq5 or .ex5 sibling of {src}",
        )
    payload: dict = {
        "copied": copied,
        "data_dir": str(data_dir),
        "resolved_via": resolved_via,
    }
    if refresh_navigator:
        nav = _refresh_navigator()
        if nav.get("ok"):
            payload["navigator_refresh"] = nav["data"]
        else:
            # Deploy succeeded; surface refresh failure as a warning so the
            # caller knows Navigator may need a manual F5 before attach-ea.
            payload["navigator_refresh"] = {
                "attempted": False,
                "error": nav["error"],
            }
    return ok(payload)


def deploy_ea(
    src: Path | str,
    *,
    data_path: Path | str | None = None,
    refresh_navigator: bool = True,
) -> dict:
    """Deploy `src` and its .ex5 sibling to <data_dir>/MQL5/Experts/.

    When `refresh_navigator` is True (default) and the copy succeeds, a
    Win32 F5 keystroke is posted to MT5's Navigator panel so it rescans
    and the new EA becomes attachable without a manual UI refresh. The
    result envelope's `navigator_refresh` key reports whether the
    keystroke was attempted; MT5's actual rescan is NOT programmatically
    verifiable from outside.
    """
    return _deploy(src, "Experts", data_path=data_path,
                   refresh_navigator=refresh_navigator)


def deploy_indicator(
    src: Path | str,
    *,
    data_path: Path | str | None = None,
    refresh_navigator: bool = True,
) -> dict:
    """Deploy `src` and its .ex5 sibling to <data_dir>/MQL5/Indicators/.

    See `deploy_ea` for the `refresh_navigator` contract.
    """
    return _deploy(src, "Indicators", data_path=data_path,
                   refresh_navigator=refresh_navigator)
