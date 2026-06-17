"""Render the consolidated campaign report as one self-contained HTML file.

No matplotlib / pandas: the equity curve is an inline-SVG <polyline> generated
from the parsed balance series the tester already emits. Links out to each child
run's native report. Pure / stdlib-only.
"""
from __future__ import annotations

from datetime import date
from html import escape
from typing import Any


def _split_frac(data: dict[str, Any]) -> float | None:
    """Position of the IS/OOS split along the [from, to] timeline, in (0, 1)."""
    try:
        start = date.fromisoformat(data["from"])
        end = date.fromisoformat(data["to"])
        split = date.fromisoformat(data["split"])
    except (KeyError, ValueError, TypeError):
        return None
    span = (end - start).days
    if span <= 0:
        return None
    frac = (split - start).days / span
    return frac if 0.0 < frac < 1.0 else None


def _svg(curve: list[dict[str, Any]], width: int = 480, height: int = 120,
         split_frac: float | None = None) -> str:
    pts: list[float] = []
    for p in curve:
        b = p.get("balance")
        if isinstance(b, (int, float)):
            pts.append(float(b))
    if len(pts) < 2:
        # Degenerate curve (real backtests have many points): still emit a
        # <polyline> so every card has a uniform structure — one point draws a
        # flat baseline, zero points an empty (non-crashing) polyline.
        coords = f"0,{height / 2:.1f} {width:.1f},{height / 2:.1f}" if pts else ""
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">'
            f'<polyline fill="none" stroke="#0f766e" stroke-width="2" points="{coords}"/></svg>'
        )
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = width / (len(pts) - 1)
    coords = " ".join(
        f"{i * step:.1f},{height - (v - lo) / span * height:.1f}" for i, v in enumerate(pts)
    )
    marker = ""
    if split_frac is not None:
        mx = split_frac * width
        marker = (f'<line x1="{mx:.1f}" y1="0" x2="{mx:.1f}" y2="{height}" '
                  f'stroke="#b7791f" stroke-width="1" stroke-dasharray="4 3"/>')
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">'
        f'<polyline fill="none" stroke="#0f766e" stroke-width="2" points="{coords}"/>'
        f'{marker}</svg>'
    )


def _g(block: dict[str, Any] | None, key: str) -> str:
    if not block or block.get(key) is None:
        return ""
    return escape(str(block[key]))


def _row(c: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(c.get('rank', '')))}</td>"
        f"<td>{escape(str(c.get('symbol', '')))}</td>"
        f"<td>{escape(str(c.get('timeframe', '')))}</td>"
        f"<td>{'yes' if c.get('validated') else 'no'}</td>"
        f"<td>{_g(c.get('full'), 'trades')}</td>"
        f"<td>{_g(c.get('full'), 'net_profit')}</td>"
        f"<td>{_g(c.get('oos'), 'sharpe')}</td>"
        # the report lives at results/<campaign-id>/report.html; child runs are
        # siblings at results/<run-id>/, so link relative to the campaign dir.
        f"<td><a href=\"../{escape(str(c.get('run_id', '')))}/report.html\">report</a></td>"
        "</tr>"
    )


def render(data: dict[str, Any]) -> str:
    """Return one self-contained HTML document for the campaign envelope ``data``."""
    ranked = data.get("ranked", [])
    rows = "".join(_row(c) for c in ranked)
    split_frac = _split_frac(data)
    cards = "".join(
        f"<section><h3>{escape(str(c.get('symbol', '')))} "
        f"{escape(str(c.get('timeframe', '')))} &mdash; rank {escape(str(c.get('rank', '')))}</h3>"
        f"{_svg(c.get('equity_curve', []), split_frac=split_frac)}</section>"
        for c in ranked
    )
    rejected = "".join(
        f"<li>{escape(str(r.get('symbol', '')))} {escape(str(r.get('timeframe', '')))} "
        f"&mdash; {escape(str(r.get('reason', '')))}</li>"
        for r in data.get("rejected", [])
    )
    caveat = data.get("rank_caveat")
    caveat_html = f"<p><strong>rank caveat:</strong> {escape(str(caveat))}</p>" if caveat else ""
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>Quant campaign {escape(str(data.get('campaign_id', '')))}</title>"
        "<style>body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#1f2933}"
        "table{border-collapse:collapse;font-size:0.92rem}td,th{border:1px solid #d8d2c4;"
        "padding:6px 10px;text-align:left}h1{font-size:1.5rem}</style></head><body>"
        f"<h1>Quant campaign &mdash; {escape(str(data.get('from', '')))} &rarr; "
        f"{escape(str(data.get('to', '')))} (split {escape(str(data.get('split', '')))})</h1>"
        f"{caveat_html}"
        "<table><tr><th>#</th><th>Asset</th><th>TF</th><th>validated</th>"
        "<th>FULL trades</th><th>FULL net</th><th>OOS Sharpe</th><th>run</th></tr>"
        f"{rows}</table>{cards}"
        f"<h2>Rejected</h2><ul>{rejected}</ul>"
        "<p><small>A single-asset, single-broker result is not validated edge &mdash; "
        "confirm broker clock, spread/slippage, and cost sensitivity, and compare the "
        "strategy's return to the asset's own move before trusting it.</small></p>"
        "</body></html>"
    )
