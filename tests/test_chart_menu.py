"""Tests for mt5_cli/chart/_menu.py - shared Win32 menu-walking helpers.

The most important test here is the tab-suffix normalization case
flagged by Codex post-fix P2 #2: MT5 menu labels often include
keyboard-shortcut suffixes like '&New Chart\\tCtrl+N'. The normalizer
must drop the suffix BEFORE collapsing whitespace, otherwise the
shortcut text leaks into the comparison target and the walk fails.
"""
import pytest

from mt5_cli.chart._menu import normalize_menu_text


# ---------------------------------------------------------------------------
# Codex post-fix P2 #2: tab-suffix normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    # Plain label
    ("Insert", "insert"),
    # '&' accelerator marker stripped
    ("&Insert", "insert"),
    ("F&ile", "file"),
    # Tab-prefixed keyboard shortcut suffix dropped (P2 #2)
    ("&New Chart\tCtrl+N", "new chart"),
    ("&Indicators List...\tCtrl+I", "indicators list..."),
    ("MyEMA\tAlt+1", "myema"),
    # Multiple consecutive whitespace collapses to single space
    ("New   Chart", "new chart"),
    # Leading/trailing whitespace trimmed
    ("  Custom  ", "custom"),
    # Empty / whitespace-only collapses to empty string
    ("", ""),
    ("   ", ""),
    # Mixed: accelerator + shortcut + extra whitespace
    ("&Open  Deleted\tCtrl+Shift+D", "open deleted"),
])
def test_normalize_menu_text(raw, expected):
    """normalize_menu_text must produce stable lowercase labels regardless
    of accelerator markers (&), whitespace runs, leading/trailing space,
    OR keyboard-shortcut suffixes after \\t."""
    assert normalize_menu_text(raw) == expected


def test_normalize_menu_text_codex_p2_2_specific_case():
    """The specific case Codex caught: '&New Chart\\tCtrl+N' must NOT
    normalize to 'new chart ctrl+n'. Before the fix, str.split() (no args)
    treated \\t as whitespace and merged the shortcut into the label."""
    result = normalize_menu_text("&New Chart\tCtrl+N")
    assert result == "new chart"
    assert "ctrl" not in result  # explicit guard against the regression


def test_normalize_menu_text_with_only_tab_and_shortcut():
    """Edge case: label that is only whitespace before the tab."""
    assert normalize_menu_text("\tCtrl+N") == ""
