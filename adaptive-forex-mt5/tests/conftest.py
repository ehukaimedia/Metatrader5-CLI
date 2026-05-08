"""Pytest fixtures for adaptive-forex-mt5 unit tests.

We add the parent directory to sys.path so tests can `import journal`,
`import agent`, etc., the same way the production scripts do.
"""
from __future__ import annotations

import sys
from pathlib import Path

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))
