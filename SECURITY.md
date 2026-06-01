# Security Policy

`metatrader5-cli` is a tool-only Python library and CLI for controlling a
running MetaTrader 5 terminal. It ships no trading strategies, indicators, or
signals. Because it can move real money on a live broker account, we take its
security posture seriously and welcome responsible disclosure.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.4.x   | Yes       |
| < 0.4   | No        |

Security fixes are applied to the latest 0.4.x release.

## Reporting a vulnerability

If you discover a security issue, please report it **privately**:

- Email **ehukaimedia@gmail.com** with the details.
- **Do not** open a public GitHub issue for sensitive reports, since that
  discloses the problem before a fix is available.

Helpful details include the affected version, a description of the issue, and
reproduction steps if you have them.

This is a community project maintained on a volunteer basis, so we cannot
commit to a fixed response time. We will acknowledge reports on a **best-effort
basis** and work with you on a resolution.

## Security model / what to know

The points below describe the project's factual security posture. Understanding
them helps you operate the tool safely.

- **Credentials live in the config file or environment variables, never in the
  repository.** Credentials are read from the config file
  (`~/.config/metatrader5-cli.json`, or the path in `$MT5_CONFIG`) or from
  environment variables such as `MT5_PASSWORD`. Keep these out of version
  control.
- **Secrets are redacted by default.** `mt5 config show` redacts the login and
  password.
- **Live trading requires a triple-lock.** Real-account mutations require all
  three gates together: `cfg["live"] = true` **and** the `MT5_LIVE=1`
  environment variable **and** the `--live` flag. If any gate is missing, the
  operation returns `RISK_LIVE_GATE_BLOCKED`.
- **The triple-lock is enforced in the library layer**, not just in the CLI
  (it lives in the orders, positions, and risk code). A direct Python call
  cannot bypass it.
- **Demo and contest accounts bypass the gate by design.** They are still live
  broker execution environments, but they do not require the triple-lock.
- **Subprocess launches are shell-free.** The terminal is launched with
  list-form arguments and no shell, avoiding shell-injection risks.
- **Tester `.ini` files carry no credentials.**

### Privacy warning: screenshots

`mt5 screenshot take` captures the MetaTrader 5 terminal window, which can
include your **account balance and equity** and your **broker login number**.
Review any screenshot before sharing it with an agent or LLM, or before
attaching it to an issue or pull request.

---

"MetaTrader" and "MT5" are trademarks of MetaQuotes Ltd. This project is
independent and is not affiliated with or endorsed by MetaQuotes.
