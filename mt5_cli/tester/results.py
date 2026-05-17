"""Parse MT5 Strategy Tester output artifacts.

The Strategy Tester writes report, journal, and optimization artifacts to disk.
This module keeps parsing hermetic and stdlib-only; it does not import the
MT5 Python bridge.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from mt5_cli.reports import ok


class _RowExtractor(HTMLParser):
    """Minimal table extractor that yields rows-of-cells per table."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                cell = " ".join("".join(self._current_cell).split())
                self._current_row.append(cell)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_table is not None:
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace(" ", ""))
    except (AttributeError, ValueError):
        return None


def _to_int(value: str) -> int | None:
    try:
        return int(value.replace(",", "").replace(" ", ""))
    except (AttributeError, ValueError):
        return None


def _cast_scalar(value: str) -> Any:
    text = value.strip()
    number = _to_float(text)
    if number is None:
        return text
    if number == int(number) and "." not in text:
        return int(number)
    return number


def _to_iso(stamp: str) -> str:
    """Convert '2024.01.05 10:15:00' to '2024-01-05T10:15:00'."""
    date, time = stamp.strip().split(" ", 1)
    return f"{date.replace('.', '-')}T{time}"


def _kv_from_metadata_table(rows: list[list[str]]) -> dict[str, str]:
    kv: dict[str, str] = {}
    for row in rows:
        for index in range(0, len(row) - 1, 2):
            key = row[index].rstrip(":").strip()
            if key:
                kv[key] = row[index + 1].strip()
    return kv


def _parse_period(period: str) -> tuple[str | None, str | None, str | None]:
    match = re.match(
        r"(\w+)\s*\((\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2})\)",
        period,
    )
    if not match:
        return period or None, None, None
    timeframe, start, end = match.groups()
    return timeframe, start.replace(".", "-"), end.replace(".", "-")


def parse_html_report(path: Path | str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    parser = _RowExtractor()
    parser.feed(text)
    if not parser.tables:
        return {"metadata": {}, "stats": {}, "deals": []}

    kv = _kv_from_metadata_table(parser.tables[0])
    metadata: dict[str, Any] = {}
    if "Symbol" in kv:
        metadata["symbol"] = kv["Symbol"]
    if "Period" in kv:
        timeframe, start, end = _parse_period(kv["Period"])
        metadata["timeframe"] = timeframe
        if start:
            metadata["from"] = start
        if end:
            metadata["to"] = end
    if "Initial Deposit" in kv:
        metadata["initial_deposit"] = _to_float(kv["Initial Deposit"])

    stats: dict[str, Any] = {}
    if "Total Trades" in kv:
        stats["total_trades"] = _to_int(kv["Total Trades"])
    if "Profit Trades (% of total)" in kv:
        match = re.search(r"\(([\d.]+)%\)", kv["Profit Trades (% of total)"])
        if match:
            stats["win_rate"] = round(float(match.group(1)) / 100, 4)
    if "Profit Factor" in kv:
        stats["profit_factor"] = _to_float(kv["Profit Factor"])
    if "Maximal Drawdown" in kv:
        match = re.search(r"\(([\d.]+)%\)", kv["Maximal Drawdown"])
        if match:
            stats["max_drawdown_pct"] = float(match.group(1))
    if "Sharpe Ratio" in kv:
        stats["sharpe"] = _to_float(kv["Sharpe Ratio"])
    if "Expected Payoff" in kv:
        stats["expectancy"] = _to_float(kv["Expected Payoff"])
    if "Total Net Profit" in kv:
        stats["net_profit"] = _to_float(kv["Total Net Profit"])

    deals: list[dict[str, Any]] = []
    if len(parser.tables) >= 2 and parser.tables[1]:
        rows = parser.tables[1]
        headers = [header.lower() for header in rows[0]]
        for row in rows[1:]:
            if len(row) != len(headers):
                continue
            raw = dict(zip(headers, row))
            deals.append(
                {
                    "time": raw.get("time"),
                    "type": raw.get("type"),
                    "order": _to_int(raw.get("order", "")),
                    "symbol": raw.get("symbol"),
                    "volume": _to_float(raw.get("volume", "")),
                    "price": _to_float(raw.get("price", "")),
                    "profit": _to_float(raw.get("profit", "")),
                }
            )

    return {"metadata": metadata, "stats": stats, "deals": deals}


def parse_journal(path: Path | str) -> list[dict[str, Any]]:
    """Parse a line-per-event tester journal CSV."""
    events: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 2)
        if len(parts) != 3:
            continue
        stamp, level, message = parts
        events.append(
            {
                "time": _to_iso(stamp),
                "level": level.strip(),
                "msg": message.strip(),
            }
        )
    return events


def parse_optimization_xml(path: Path | str) -> list[dict[str, Any]]:
    root = ET.parse(Path(path)).getroot()
    passes: list[dict[str, Any]] = []
    for pass_node in root.findall("pass"):
        entry: dict[str, Any] = {}
        for child in pass_node:
            entry[child.tag] = _cast_scalar(child.text or "")
        passes.append(entry)
    return passes


def assemble(
    *,
    run_id: str,
    html_path: Path | str | None,
    journal_path: Path | str | None = None,
    optimization_path: Path | str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"run_id": run_id}
    if extra_metadata:
        data.update(extra_metadata)

    if html_path and Path(html_path).exists():
        report = parse_html_report(html_path)
        data.setdefault("metadata", {}).update(report["metadata"])
        data["stats"] = report["stats"]
        data["deals"] = report["deals"]
    else:
        data.setdefault("metadata", {})
        data["stats"] = {}
        data["deals"] = []

    if journal_path and Path(journal_path).exists():
        data["journal_events"] = parse_journal(journal_path)
    else:
        data["journal_events"] = []

    if optimization_path and Path(optimization_path).exists():
        data["optimization"] = parse_optimization_xml(optimization_path)
    else:
        data["optimization"] = []

    return ok(data)
