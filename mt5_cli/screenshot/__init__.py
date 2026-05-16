"""Screenshot submodule. mss + pygetwindow + PIL; no MetaTrader5 SDK touch."""
from .screenshot import (
    annotate,
    dom,
    list_screenshots,
    take,
)

__all__ = ["take", "annotate", "dom", "list_screenshots"]
