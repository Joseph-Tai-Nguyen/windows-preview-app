"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from winpreview import APP_NAME, __version__
from winpreview.resources import app_icon_path

# Must match AppUserModelID in installer/winpreview.iss so taskbar pinning and
# grouping use our icon instead of python.exe's.
APP_USER_MODEL_ID = "WinPreview.WinPreview"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass  # cosmetic only


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _set_windows_app_id()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(app_icon_path())))

    # Imported after QApplication exists so module-level Qt objects are safe.
    from winpreview.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    files = [arg for arg in app.arguments()[1:] if not arg.startswith("-")]
    if files:
        window.open_file(files[0])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
