"""Smoke test: confirm pytest can import adaptive-forex-mt5 modules."""
def test_journal_importable():
    import journal  # noqa: F401


def test_agent_importable():
    import agent  # noqa: F401
