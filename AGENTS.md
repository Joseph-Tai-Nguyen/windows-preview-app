# AGENTS.md

Instructions for AI coding agents (Claude Code, Gemini CLI, Codex, Cursor, …) working in this repository. Humans are welcome to read it too.

## Project in one paragraph

WinPreview is a Windows desktop app (Python + PySide6 + PyMuPDF) for organizing PDF pages, modeled on macOS Preview's page workflow. You open a PDF, see thumbnails in a sidebar, select pages and delete them (Delete key or File › Delete), drag to reorder, and insert pages from other PDFs, images, a blank page or a scanner (File › Insert ›). Everything can be undone, and saving is atomic.

Read before larger changes:

- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md): what to build, with IDs and status. Update the status when you finish an item.
- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): architecture, data flow, design decisions, known limitations.

## Commands (PowerShell, from the repo root)

```powershell
./scripts/setup.ps1                        # create .venv and install the app with dev extras
./scripts/run.ps1 [path\to\file.pdf]       # launch the app
./scripts/check.ps1                        # ruff lint + format check + pytest (run before finishing)
./scripts/build.ps1                        # PyInstaller build into dist\WinPreview\
./scripts/build_installer.ps1              # build + Inno Setup offline installer into release\
.venv\Scripts\python scripts\make_icon.py  # regenerate winpreview.ico from winpreview.svg
```

Release notes for agents:

- The version lives only in `src/winpreview/__init__.py` (`__version__`). Bump it there and also in `pyproject.toml`. The build scripts read it from the package.
- Never change `AppId` in `installer/winpreview.iss`. Windows uses it to recognise upgrades. `APP_USER_MODEL_ID` in `app.py` must match `AppUserModelID` in the `.iss`.
- The icon's source of truth is `resources/icons/winpreview.svg`. Edit it, run `make_icon.py`, and commit the regenerated `.ico` and `.png`. The icon is original artwork; don't swap in Apple's Preview icon.

The same commands without the scripts:

```powershell
.venv\Scripts\python -m pytest             # all tests (Qt runs offscreen automatically)
.venv\Scripts\python -m pytest tests/core  # fast, Qt-free tests only
.venv\Scripts\ruff check src tests
.venv\Scripts\ruff format src tests
.venv\Scripts\python -m winpreview sample.pdf
```

Always use the interpreter in `.venv`. The system has no `python` on PATH, only the `py` launcher.

## Layout

```
src/winpreview/core/   Qt-free logic: document.py (PdfDocument), scanner.py (WIA)
src/winpreview/ui/     PySide6 widgets: main_window, thumbnail_view, page_view, page_model, renderer
src/winpreview/resources/icons/  app icon (SVG source, generated .ico/.png)
installer/             Inno Setup script (offline installer)
tests/core/            unit tests for core (no Qt)
tests/ui/              pytest-qt tests for the window
docs/                  requirements + project context
scripts/               PowerShell helpers
```

## Architecture rules

1. **`core` must never import PySide6.** All PDF logic goes in `PdfDocument` so it can be tested without a GUI.
2. **Every mutating `PdfDocument` method** must:
   - validate its input first and raise `DocumentError` (with a user-facing message) *before* changing anything,
   - call `self._checkpoint()` immediately before mutating,
   - return the list of 0-based page indices to select afterwards.
3. **The UI performs operations through `MainWindow._apply(lambda: ...)`.** That method handles errors, refreshes the model, restores the scroll position and selects the returned rows. Do not mutate the document anywhere else.
4. **After any document change the model is reset** (`PageListModel.refresh()`). The delegates clear their pixmap caches on `modelReset`. Do not cache pixmaps by page index across changes.
5. **Drag and drop on the sidebar is handled in `ThumbnailView`**, not in model `dropMimeData`. Keep reporting `CopyAction` on internal drops and keep deferring signals with `QTimer.singleShot(0, ...)`. PROJECT_CONTEXT.md explains why.
6. **Never hold the source file open.** Read files as bytes (`_read_bytes`) and open from the stream. `save()` writes to a temp file and then calls `os.replace`.
7. The import name is `pymupdf`. Do not use the legacy `fitz` alias.

## Adding a new page operation (checklist)

1. Add the method to `PdfDocument` following rule 2, and write tests in `tests/core/test_document.py`. Cover normal cases, edge cases, invalid input leaving the document unmodified, and undo.
2. Add a `QAction` in `MainWindow._create_actions` (with a shortcut if it makes sense). Place it in the menus, toolbar or context menu, and set its enabled state in `_update_ui`.
3. Add a `MainWindow` method that calls `self._apply(...)`.
4. Add a pytest-qt test in `tests/ui/test_main_window.py`.
5. Update the requirement status in `docs/REQUIREMENTS.md`, and the shortcut table if needed.

## Coding conventions

- Python 3.11+, `from __future__ import annotations`, type hints on public functions.
- ruff with the config in `pyproject.toml` (line length 100). Run `ruff format` before finishing.
- Qt overrides keep Qt's camelCase names (`dropEvent`, `sizeHint`). Everything else uses snake_case.
- Use the fully qualified Qt enums (`Qt.ItemDataRole.DisplayRole`, `QMessageBox.StandardButton.Save`).
- User-facing strings are plain and brief, with curly quotes around file names (“name.pdf”). Menu paths use `›`.
- Keep comments for the *why*. No banner comments that restate the code.

## Testing notes

- `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` and redirects `QSettings` to a temp INI. Never write tests that touch the real registry or the user's files.
- Test PDFs and images are **generated** by the `make_pdf` and `make_png` fixtures. Do not commit binary sample files.
- Modal dialogs block tests. The `window` fixture already patches `MainWindow._error` and `QMessageBox.question`. Patch any new dialog the same way.
- The scanner cannot be exercised in CI. Test `scanner._translate` and the unsupported path, and mock `acquire_image` for UI flows.

## Definition of done

- `./scripts/check.ps1` passes (lint, format and tests).
- New behavior has tests, and the docs and requirement status are updated.
- No new dependency is added without updating `pyproject.toml` and noting its license in PROJECT_CONTEXT.md. (AGPL/GPL-compatible only.)

## Don'ts

- Don't commit `.venv/`, build output, real user PDFs, or `.claude/settings.local.json`.
- Don't switch the PDF library, GUI toolkit or license without discussing it first.
- Don't copy Apple's Preview artwork, icons or names into the app. The workflow is the inspiration, not the branding.
