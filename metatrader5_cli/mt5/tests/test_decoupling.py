"""
Regression guards for host-agnostic packaging.

The CLI may expose Ehukai-named trading indicators, but it must not grow a
runtime dependency on the EhukaiConnect app, its services, or a machine-local
launcher path.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

RUNTIME_FILES = [
    ROOT / "setup.py",
    *(
        path
        for path in (ROOT / "metatrader5_cli").rglob("*.py")
        if "__pycache__" not in path.parts
        and "tests" not in path.parts
    ),
]

FORBIDDEN_RUNTIME_MARKERS = (
    "EhukaiConnect",
    "ehukaiconnect",
    "Ehukai Connect",
    "localhost:8800",
    "localhost:8810",
    "127.0.0.1:8800",
    "127.0.0.1:8810",
    "AppData\\Roaming\\Python\\Python313\\Scripts\\mt5.exe",
    "Python313\\Scripts\\mt5.exe",
)


def test_runtime_has_no_ehukaiconnect_dependency_markers():
    hits = []
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_RUNTIME_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert hits == []
