from setuptools import setup, find_packages

setup(
    name="metatrader5-cli",
    version="0.1.0",
    packages=find_packages(exclude=("archive", "archive.*", "tests", "tests.*")),
    install_requires=[
        "MetaTrader5>=5.0.45",
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "pandas>=2.0.0",
        "pandas-ta>=0.3.14b",
        "mss>=9.0.0",
        "Pillow>=10.0.0",
        "python-dateutil>=2.9.0",
        "pygetwindow>=0.0.9",
        "pywin32>=306; platform_system=='Windows'",
    ],
    entry_points={
        "console_scripts": [
            "mt5 = mt5.cli:main",
        ],
    },
    # Phase 5 will add `mt5-mcp = mt5_mcp.server:main` when the MCP server
    # lands. The legacy `mt5 = metatrader5_cli.mt5.mt5_cli:main` entry
    # point is gone (the metatrader5_cli/ package was archived in Phase 1);
    # `pip install -e .` after this change replaces the stale binary with
    # the new mt5.cli:main wrapper.
    python_requires=">=3.10",
)
