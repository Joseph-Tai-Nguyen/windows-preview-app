from __future__ import annotations

from PySide6.QtGui import QIcon

from winpreview.resources import ICON_DIR, app_icon_path


def test_icon_files_exist():
    assert app_icon_path().is_file()
    assert (ICON_DIR / "winpreview.svg").is_file()


def test_icon_has_windows_sizes(qapp):
    sizes = {s.width() for s in QIcon(str(app_icon_path())).availableSizes()}
    assert {16, 24, 32, 48, 256} <= sizes
