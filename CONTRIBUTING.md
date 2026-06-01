# Contributing

Thanks for your interest in improving **metatrader5-cli** — a Python library and CLI
for controlling a running MetaTrader 5 terminal from scripts and agents. This is a
tool-only project: it ships no trading strategies, indicators, or signals.

The notes below cover everything you need to get set up, run the tests, and open a
pull request that lands smoothly.

## Requirements

- **Windows** — the project depends on the Windows-only `MetaTrader5` package and `pywin32`.
- **Python 3.10+**.
- A running **MetaTrader 5 terminal** is required *only* for integration tests. The
  fast unit suite is fully mock-based and needs no terminal.

## Setup

```bash
git clone https://github.com/ehukaimedia/Metatrader5-CLI.git
cd Metatrader5-CLI
pip install -e ".[dev]"
pre-commit install
```

`pre-commit install` wires up `ruff` so it runs automatically on each commit.

## Running tests

Run the fast suite (550+ mock-based tests, no terminal needed):

```bash
pytest -m "not integration"
```

Integration tests are marked `@pytest.mark.integration` and require a live Windows
MT5 terminal. They are not run in CI; run them locally when your change touches
terminal-facing behavior.

## Linting

```bash
ruff check .
```

`mypy` is available and lenient (non-blocking).

## Architecture rule

The project is a thin CLI layer (the `mt5/` package) over a library (`mt5_cli/`).
Keep that separation intact:

- **`mt5/` is a thin wrapper.** It does argument parsing and envelope routing only.
- **Business logic belongs in the library (`mt5_cli/`).**
- **Route all output through the ok/fail envelope.** Commands emit a JSON envelope
  and always exit 0; callers parse the `ok` boolean, not the exit code.
- **Register new error codes in `mt5_cli/errors.py`.** A test enforces this, so an
  unregistered code will fail the suite.

## Tests

We follow TDD. Every change needs a test — write the failing test first, then the
code that makes it pass.

## Pull requests

- Keep each PR focused on a single change.
- Make sure `ruff check .` is clean and the unit suite (`pytest -m "not integration"`)
  passes before you open the PR.
- Describe what changed and why.

## Security

Please do not file security issues in the public tracker. Report them privately to
**ehukaimedia@gmail.com**.

---

*"MetaTrader" and "MT5" are trademarks of MetaQuotes Ltd. This project is independent
and is not affiliated with or endorsed by MetaQuotes.*
