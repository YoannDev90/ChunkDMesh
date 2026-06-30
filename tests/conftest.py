"""Shared test configuration."""

import sys
from pathlib import Path

_server_dir = str(Path(__file__).resolve().parent.parent / "server")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)
