"""Quant report: self-contained HTML, inline-SVG equity, child-run links, no deps."""
import re

from mt5_cli.quant import report

DATA = {
    "campaign_id": "cid", "from": "2022-01-01", "to": "2024-12-31", "split": "2024-02-06",
    "rank_caveat": None,
    "ranked": [{
        "rank": 1, "symbol": "XAUUSD", "timeframe": "H1", "validated": True, "run_id": "r1",
        "full": {"trades": 804, "net_profit": 55198.59, "profit_factor": 2.02},
        "is": {"profit_factor": 2.10}, "oos": {"profit_factor": 2.02, "sharpe": 1.79},
        "equity_curve": [{"balance": 10000}, {"balance": 10200}, {"balance": 10500}],
    }],
    "rejected": [{"symbol": "UKOIL", "timeframe": "H1", "reason": "MIN_TRADES"}],
}


def test_render_self_contained_with_svg_and_child_links():
    html = report.render(DATA)
    assert "<svg" in html and "<polyline" in html
    assert "results/r1/report.html" in html        # link to the child run's native report
    assert "MIN_TRADES" in html                     # rejected section
    # no external assets — playground/report must be offline-safe
    assert not re.search(r'(src|href)="https?://', html)


def test_render_handles_short_curve_without_crashing():
    data = dict(DATA)
    data["ranked"] = [{"rank": 1, "symbol": "X", "timeframe": "H1", "full": {}, "oos": {},
                       "equity_curve": [{"balance": 100}]}]
    html = report.render(data)
    # degenerate curve still yields a uniform <svg>/<polyline> structure, no exception
    assert "<svg" in html and "<polyline" in html


def test_render_imports_without_matplotlib_or_pandas():
    import sys
    assert "matplotlib" not in sys.modules
    assert "pandas" not in sys.modules
