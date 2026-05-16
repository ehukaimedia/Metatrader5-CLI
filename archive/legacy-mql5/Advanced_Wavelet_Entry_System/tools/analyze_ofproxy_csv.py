#!/usr/bin/env python3
"""Analyze Advanced Wavelet OFProxy v2 signal CSVs.

The script is intentionally dependency-free so it can run on the MT5 host with
only Python installed. It reads MetaTrader CSV exports, groups high-confidence
signals by symbol, direction, and OFProxy class, and writes a Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import math
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable


DEFAULT_TESTER_GLOB = (
    r"C:\Users\arsen\AppData\Roaming\MetaQuotes\Tester"
    r"\D0E8209F77C8CF37AD8BF550E51FF075"
    r"\Agent-127.0.0.1-3000\MQL5\Files\WaveletResearch"
    r"\*_signals_ofproxy_v2.csv"
)


@dataclass
class BucketStats:
    name: str
    count: int
    avg_12: float | None
    med_12: float | None
    win_12: float | None
    avg_24: float | None
    med_24: float | None
    win_24: float | None
    avg_48: float | None
    med_48: float | None
    win_48: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--glob",
        default=DEFAULT_TESTER_GLOB,
        help="Glob for *_signals_ofproxy_v2.csv files.",
    )
    parser.add_argument(
        "--symbols",
        default="USDJPY,GBPUSD,AUDUSD",
        help="Comma-separated symbols to include. Empty means include all.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.80,
        help="Minimum signal score for the high-confidence slice.",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(
            "metatrader5_cli",
            "mt5",
            "mql5",
            "Advanced_Wavelet_Entry_System",
            "reports",
            "ofproxy_direction_comparison_2026-05-11.md",
        ),
        help="Markdown report output path.",
    )
    return parser.parse_args()


def read_csv(path: str) -> list[dict[str, str]]:
    # MT5 writes FileOpen(..., FILE_CSV) output as UTF-16LE with BOM on this terminal.
    for encoding in ("utf-16", "utf-8-sig"):
        try:
            with open(path, newline="", encoding=encoding) as handle:
                return list(csv.DictReader(handle))
        except UnicodeError:
            continue
    raise UnicodeError(f"Unable to decode {path}")


def to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if math.isfinite(parsed):
        return parsed
    return None


def mean(values: Iterable[float]) -> float | None:
    vals = list(values)
    return statistics.mean(vals) if vals else None


def median(values: Iterable[float]) -> float | None:
    vals = list(values)
    return statistics.median(vals) if vals else None


def win_rate(values: Iterable[float]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return 100.0 * sum(1 for value in vals if value > 0.0) / len(vals)


def horizon_values(rows: Iterable[dict[str, str]], horizon: int) -> list[float]:
    key = f"fwd_ret_{horizon}_points"
    return [value for value in (to_float(row.get(key)) for row in rows) if value is not None]


def bucket_stats(name: str, rows: list[dict[str, str]]) -> BucketStats:
    vals_12 = horizon_values(rows, 12)
    vals_24 = horizon_values(rows, 24)
    vals_48 = horizon_values(rows, 48)
    return BucketStats(
        name=name,
        count=len(rows),
        avg_12=mean(vals_12),
        med_12=median(vals_12),
        win_12=win_rate(vals_12),
        avg_24=mean(vals_24),
        med_24=median(vals_24),
        win_24=win_rate(vals_24),
        avg_48=mean(vals_48),
        med_48=median(vals_48),
        win_48=win_rate(vals_48),
    )


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"


def markdown_bucket_table(stats: list[BucketStats]) -> list[str]:
    lines = [
        "| Bucket | N | Avg 12 | Med 12 | Win 12 | Avg 24 | Med 24 | Win 24 | Avg 48 | Med 48 | Win 48 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in stats:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    str(item.count),
                    fmt(item.avg_12),
                    fmt(item.med_12),
                    fmt_pct(item.win_12),
                    fmt(item.avg_24),
                    fmt(item.med_24),
                    fmt_pct(item.win_24),
                    fmt(item.avg_48),
                    fmt(item.med_48),
                    fmt_pct(item.win_48),
                ]
            )
            + " |"
        )
    return lines


def split_rows(rows: list[dict[str, str]], predicate: Callable[[dict[str, str]], bool]) -> list[dict[str, str]]:
    return [row for row in rows if predicate(row)]


def latest_file_by_symbol(paths: list[str]) -> dict[str, str]:
    latest: dict[str, str] = {}
    latest_time: dict[str, float] = {}
    for path in paths:
        try:
            sample = read_csv(path)
        except Exception:
            continue
        if not sample:
            continue
        symbol = sample[0].get("symbol", "")
        if not symbol:
            continue
        mtime = os.path.getmtime(path)
        if symbol not in latest_time or mtime > latest_time[symbol]:
            latest[symbol] = path
            latest_time[symbol] = mtime
    return latest


def year_table(rows: list[dict[str, str]], bucket_name: str) -> list[str]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        year = row.get("bar_time", "")[:4]
        klass = row.get("of_proxy_decision_class", "")
        value = to_float(row.get("fwd_ret_24_points"))
        if year and value is not None:
            grouped[(klass, year)].append(value)

    lines = [
        f"**{bucket_name} Year Split, 24-Bar Forward Return**",
        "",
        "| Class | Year | N | Avg 24 | Median 24 |",
        "|---|---:|---:|---:|---:|",
    ]
    for (klass, year), values in sorted(grouped.items()):
        lines.append(
            f"| {klass} | {year} | {len(values)} | {fmt(mean(values))} | {fmt(median(values))} |"
        )
    return lines


def build_report(paths: list[str], symbols: set[str], threshold: float) -> str:
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    latest = latest_file_by_symbol(paths)
    if symbols:
        latest = {symbol: path for symbol, path in latest.items() if symbol in symbols}

    lines: list[str] = [
        "# OFProxy Direction Comparison",
        "",
        f"Generated: {generated}",
        f"Score threshold: `{threshold:.2f}`",
        "",
        "This report analyzes `*_signals_ofproxy_v2.csv` diagnostics only. It is not a profitability claim and it does not use trade execution results.",
        "",
        "## Files",
        "",
    ]
    if not latest:
        lines.append("No matching files found.")
        return "\n".join(lines) + "\n"

    for symbol, path in sorted(latest.items()):
        lines.append(f"- `{symbol}`: `{path}`")
    lines.append("")

    cross_symbol_rows: list[BucketStats] = []
    combined_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)

    for symbol, path in sorted(latest.items()):
        rows = read_csv(path)
        high_conf = [row for row in rows if (to_float(row.get("score")) or 0.0) >= threshold]
        data_modes = Counter(row.get("of_proxy_data_mode", "") for row in rows)
        classes = Counter(row.get("of_proxy_decision_class", "") for row in high_conf)

        buckets: list[tuple[str, Callable[[dict[str, str]], bool]]] = [
            ("all_hc", lambda row: True),
            ("all_buy", lambda row: row.get("direction") == "buy"),
            ("all_sell", lambda row: row.get("direction") == "sell"),
            ("proceed_all", lambda row: row.get("of_proxy_decision_class") in {"proceed_buy", "proceed_sell"}),
            ("proceed_buy", lambda row: row.get("of_proxy_decision_class") == "proceed_buy"),
            ("proceed_sell", lambda row: row.get("of_proxy_decision_class") == "proceed_sell"),
            ("non_proceed", lambda row: row.get("of_proxy_decision_class") not in {"proceed_buy", "proceed_sell"}),
            ("investigate", lambda row: row.get("of_proxy_decision_class") == "investigate"),
            ("no_evidence", lambda row: row.get("of_proxy_decision_class") == "no_evidence"),
            ("stand_down", lambda row: row.get("of_proxy_decision_class") == "stand_down"),
        ]

        stats: list[BucketStats] = []
        for name, predicate in buckets:
            bucket_rows = split_rows(high_conf, predicate)
            if bucket_rows:
                stats.append(bucket_stats(name, bucket_rows))
                combined_by_name[f"{symbol}:{name}"].extend(bucket_rows)

        lines.extend(
            [
                f"## {symbol}",
                "",
                f"- Total signal rows: `{len(rows)}`",
                f"- High-confidence rows: `{len(high_conf)}`",
                f"- Data modes: `{dict(data_modes)}`",
                f"- HC decision classes: `{dict(classes)}`",
                "",
            ]
        )
        lines.extend(markdown_bucket_table(stats))
        lines.append("")

        all_buy = split_rows(high_conf, lambda row: row.get("direction") == "buy")
        all_sell = split_rows(high_conf, lambda row: row.get("direction") == "sell")
        proceed_buy = split_rows(high_conf, lambda row: row.get("of_proxy_decision_class") == "proceed_buy")
        proceed_sell = split_rows(high_conf, lambda row: row.get("of_proxy_decision_class") == "proceed_sell")
        buy_lift = (bucket_stats("proceed_buy", proceed_buy).avg_24 or 0.0) - (bucket_stats("all_buy", all_buy).avg_24 or 0.0) if all_buy and proceed_buy else None
        sell_lift = (bucket_stats("proceed_sell", proceed_sell).avg_24 or 0.0) - (bucket_stats("all_sell", all_sell).avg_24 or 0.0) if all_sell and proceed_sell else None
        cross_symbol_rows.extend(
            [
                BucketStats(f"{symbol} buy lift", 0, None, None, None, buy_lift, None, None, None, None, None),
                BucketStats(f"{symbol} sell lift", 0, None, None, None, sell_lift, None, None, None, None, None),
            ]
        )

        lines.extend(year_table(high_conf, symbol))
        lines.append("")

    lines.extend(
        [
            "## Direction-Aware Lift",
            "",
            "Lift is `proceed_direction avg 24` minus `all same-direction avg 24`. Positive lift means the proxy classification improved that direction versus taking every high-confidence signal in the same direction.",
            "",
            "| Symbol/Direction | Lift 24 |",
            "|---|---:|",
        ]
    )
    for item in cross_symbol_rows:
        lines.append(f"| {item.name} | {fmt(item.avg_24)} |")

    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Treat buckets with fewer than 30 signals as weak evidence.",
            "- Prefer median and year consistency over average alone.",
            "- Do not promote a filter to execution until it survives symbol and year splits.",
            "- Current OFProxy outputs are spot-FX order-flow proxies, not true footprint delta.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    paths = sorted(glob.glob(args.glob))
    symbols = {symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()}
    report = build_report(paths, symbols, args.threshold)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
        if not report.endswith("\n"):
            handle.write("\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
