from pathlib import Path

from mt5_cli.tester import results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_journal.csv"


def test_parse_journal_returns_events():
    events = results.parse_journal(FIXTURE)
    assert len(events) == 4
    assert events[0]["level"] == "info"
    assert events[2]["level"] == "warning"
    assert "Slippage" in events[2]["msg"]


def test_journal_iso_timestamps():
    events = results.parse_journal(FIXTURE)
    assert events[0]["time"] == "2024-01-05T10:15:00"
