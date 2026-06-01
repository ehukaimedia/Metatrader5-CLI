"""mt5 - thin CLI wrapper around the mt5_cli library.

The CLI exists ONLY to expose the library surface to shell-based agents
and humans. Every command:

  1. Delegates to a function in mt5_cli/<concern>/
  2. Receives an ok/fail envelope dict
  3. Emits it as JSON (with --json) or human-readable text (default)

The library is the source of truth - test against mt5_cli functions
directly, not against the CLI. CLI tests are smoke tests that verify
plumbing (arg parsing, envelope formatting, --json/--live threading).
"""
