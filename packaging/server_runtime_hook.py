"""PyInstaller runtime hook for the frozen server.

On first run, copy the bundled world_config.json5 template next to the
executable (writable "data/" dir) and point CHUNKMESH_CONFIG_PATH at it,
so the operator can edit the real config without touching the app bundle.
"""

import os
import shutil
import sys
from pathlib import Path


def _main() -> None:
    if os.environ.get("CHUNKMESH_CONFIG_PATH"):
        return
    if not getattr(sys, "frozen", False):
        return
    data_dir = Path(sys.executable).resolve().parent / "data"
    data_dir.mkdir(exist_ok=True)
    default = data_dir / "world_config.json5"
    if not default.exists():
        bundled = Path(sys._MEIPASS) / "data" / "world_config.json5"
        if bundled.exists():
            shutil.copy2(bundled, default)
    if default.exists():
        os.environ["CHUNKMESH_CONFIG_PATH"] = str(default)


_main()
