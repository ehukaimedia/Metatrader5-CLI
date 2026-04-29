from setuptools import setup, find_packages

setup(
    name="cli-anything-mt5",
    version="0.1.0",
    packages=find_packages(),
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
            "mt5 = metatrader5_cli.mt5.mt5_cli:main",
        ],
    },
    python_requires=">=3.10",
)
