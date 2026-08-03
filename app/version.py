"""Application version.

The version lives in ``pyproject.toml`` and is read from there so there is a
single source of truth. The application is not installed as a package, so
``importlib.metadata`` is not an option.
"""

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

with _PYPROJECT.open("rb") as f:
    __version__ = tomllib.load(f)["project"]["version"]
