"""Path resolution that works both from source and from a PyInstaller bundle."""

import sys
from pathlib import Path


def bundle_root() -> Path:
    """Return project root when running from source, or the PyInstaller bundle root when frozen.

    In a PyInstaller onedir build every bundled module/data lives under the bundle
    root (sys._MEIPASS, i.e. the "_internal" directory), so relative paths computed
    from ``__file__`` still resolve to the correct bundled assets.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent
