---
name: Bug report
about: Report a problem
labels: ["bug"]
---

<!--
Thanks for taking the time to file a report.

Please redact anything sensitive before posting: account/login numbers, balances,
and equity can appear in command output and in screenshots ('mt5 screenshot take').
Review and mask these in any text or images you paste below.
-->

## What happened

A clear description of the problem.

## Command run

The exact `mt5 ...` command you ran (include the full command line).

```
mt5 ...
```

## Output

The full `--json` envelope printed to stdout (re-run with `--json` if you didn't
the first time). On failure this looks like:
`{"ok": false, "error": {"code": "...", "message": "..."}}`.

```json

```

## Expected behavior

What you expected to happen instead.

## Environment

- OS / Windows build: <!-- e.g. Windows 11 26200 -->
- Python version (`python --version`):
- metatrader5-cli version (`mt5 --version`):
- MetaTrader 5 build:
- Broker:

## Additional context

Anything else that might help (steps to reproduce, what you already tried).
