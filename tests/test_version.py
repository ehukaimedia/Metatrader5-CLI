"""Version exposure: the package must expose mt5_cli.__version__ and the CLI
must answer `mt5 --version`, sourced from the installed package metadata."""
import re


def test_package_exposes_version_string():
    import mt5_cli
    assert isinstance(mt5_cli.__version__, str)
    assert re.match(r"^\d+\.\d+", mt5_cli.__version__)
