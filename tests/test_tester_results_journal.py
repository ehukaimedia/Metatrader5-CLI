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


def test_parse_journal_skips_header_and_bad_timestamps(tmp_path):
    journal = tmp_path / "journal.csv"
    journal.write_text(
        "time,level,msg\n"
        "not-a-time,info,skip me\n"
        "2024.01.05 10:15:00,info,\"message, with comma\"\n",
        encoding="utf-8",
    )
    events = results.parse_journal(journal)
    assert events == [
        {
            "time": "2024-01-05T10:15:00",
            "level": "info",
            "msg": "message, with comma",
        }
    ]
