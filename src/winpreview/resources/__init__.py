"""Bundled assets (icons). Paths work from source, an installed wheel and PyInstaller."""

from __future__ import annotations

from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"


def app_icon_path() -> Path:
    """The multi-resolution .ico used for windows, the taskbar and the .exe."""
    return ICON_DIR / "winpreview.ico"
