# adaptive-forex-mt5

POC: scan many pairs, place small high-quality setups via the existing Ehukai
TDA gates, journal every trade with its reasoning, learn from outcomes.

Three files do real work:
- `agent.py` — scans pairs every minute, places when `analyze sniper-poc` returns `status=ready`
- `journal.py` — append-only log of placements, reasoning, and outcomes
- `dashboard.py` — local web view of the journal

## Setup

```powershell
cd C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\adaptive-forex-mt5
copy config.example.json config.json
```

Edit `config.json`:
- `pairs` — symbols to scan
- `agent.volume` — lot size per trade (start at 0.001)
- `agent.min_quality_score` — only place when quality >= this (default 0.8)
- `agent.max_concurrent_positions` / `max_trades_per_day` — guardrails
- `mt5_cli.live` — `false` for demo, `true` for live (also requires `--live` flag inheritance)

## Run

Two terminals:

```powershell
python agent.py        # the trading loop
python dashboard.py    # the journal viewer
```

Expose dashboard to your tailnet:

```powershell
tailscale serve https / http://localhost:8765
```

Then visit `https://<this-machine>.<your-tailnet>.ts.net/` from any device on your tailnet.

## What gets logged per trade

Every placement records:
- ticket, pair, direction, entry, SL, TP, R:R, volume, strategy_id
- **Reasoning**: the full sniper-poc setup snapshot — structure, POI, liquidity context, entry model, gates that passed, quality score, and human-readable `explain` strings

Every closed position records:
- profit, close price, close time, result (tp/sl/even)

Skips and errors are logged too so you can see why setups didn't fire.

## What "learn from the trade" means here

The dashboard summarizes:
- Win rate, total P/L, open vs closed counts
- Per-pair: wins, losses, total P/L
- Each closed trade shows the gates that fired before placement → over time you can see which gate combinations actually produce wins vs losses

No ML; just the journal and aggregates. Once you have ~50 closed trades you can grep the JSONL or query it with SQL via DuckDB to find which reasoning patterns correlate with wins.

## Safety

- Uses `mt5 order ready-limit` which already gates: READY status + 2 broker dry-runs + drift check + risk.py
- Daily trade cap and concurrent position cap in `config.json`
- Dashboard is read-only (no order placement from the web view)
- Tailscale-only exposure (no public funnel) — dashboard binds 127.0.0.1

## Layout

```
adaptive-forex-mt5/
├── agent.py            # scan + place loop
├── journal.py          # append-only trade log
├── dashboard.py        # local web view
├── alerts.py           # ntfy push wrapper
├── config.example.json
├── README.md
├── .gitignore
└── logs/               # trades.jsonl + per-day diagnostic logs (gitignored)
```
