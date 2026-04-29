"""
repl_skin.py — Interactive REPL for the MT5 CLI.

Wraps ``prompt_toolkit.PromptSession`` to provide:
- Banner showing server, balance and currency on start
- Arrow-key history and tab completion on top-level command names
- Prompt prefix that tracks the last-used symbol: ``mt5 (USDJPY)>``
- Automatic one-shot reconnect on MT5 disconnect mid-session
"""
from __future__ import annotations

import re
import shlex

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from cli_anything.mt5.utils import mt5_backend as bridge

# Heuristic: a symbol looks like 3–8 consecutive uppercase ASCII letters.
_SYMBOL_RE = re.compile(r"^[A-Z]{3,8}$")

_TOP_LEVEL_COMMANDS = [
    "account", "analyze", "config", "history", "indicator",
    "kill-switch", "market", "order", "position", "rates",
    "screenshot", "exit", "help",
]


class ReplSkin:
    """Interactive REPL session for the MT5 CLI."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.last_symbol: str = ""
        self._session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            completer=WordCompleter(_TOP_LEVEL_COMMANDS, ignore_case=True),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _banner(self) -> str:
        """Build the startup banner line from cfg + live account info."""
        from cli_anything.mt5.core import account  # noqa: PLC0415 (lazy — avoids circular import)

        server = self.cfg.get("server", "MT5")
        info = account.info()
        if info.get("ok"):
            d = info["data"]
            return (
                f"₿ MT5 CLI v0.1  |  {d.get('server', server)}"
                f"  |  Balance: {d['balance']:,.2f} {d['currency']}\n"
                f"Type 'help' for commands, 'exit' to quit."
            )
        return (
            f"₿ MT5 CLI v0.1  |  {server}\n"
            f"Type 'help' for commands, 'exit' to quit."
        )

    def _prompt_text(self) -> str:
        if self.last_symbol:
            return f"mt5 ({self.last_symbol})> "
        return "mt5> "

    @staticmethod
    def _extract_symbol(args: list[str]) -> str | None:
        """Return the first argument that looks like a ticker symbol."""
        for arg in args:
            if _SYMBOL_RE.match(arg):
                return arg
        return None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the REPL loop (blocks until user types 'exit' or Ctrl-D)."""
        from cli_anything.mt5 import mt5_cli  # noqa: PLC0415 (lazy — avoids circular import at module level)

        click.echo(self._banner())

        while True:
            try:
                text = self._session.prompt(self._prompt_text())
            except EOFError:
                break
            except KeyboardInterrupt:
                continue

            text = text.strip()
            if not text or text.startswith("#"):
                continue
            if text in ("exit", "quit"):
                break
            if text == "help":
                click.echo("Commands: " + "  ".join(_TOP_LEVEL_COMMANDS))
                continue

            args = shlex.split(text)
            sym = self._extract_symbol(args)
            if sym:
                self.last_symbol = sym

            self._dispatch(args, mt5_cli)

    def _dispatch(self, args: list[str], mt5_cli) -> None:  # noqa: ANN001
        """Run one command; auto-reconnect once on ConnectionError."""
        try:
            mt5_cli.main.main(args, standalone_mode=False)
        except SystemExit:
            pass
        except ConnectionError as exc:
            if bridge.reconnect_once(self.cfg):
                try:
                    mt5_cli.main.main(args, standalone_mode=False)
                except Exception as exc2:  # noqa: BLE001
                    click.secho(f"MT5_CONNECTION_ERROR: {exc2}", fg="red", err=True)
            else:
                click.secho(f"MT5_CONNECTION_ERROR: {exc}", fg="red", err=True)
        except Exception as exc:  # noqa: BLE001
            click.secho(f"Error: {exc}", fg="red", err=True)
