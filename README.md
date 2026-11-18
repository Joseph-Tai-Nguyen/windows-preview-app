# WinPreview

A fast, private PDF page organizer for Windows, inspired by the page-editing workflow of macOS Preview.

Open a PDF, see every page as a thumbnail, and fix the document directly:

- **Delete pages**: select thumbnails and press <kbd>Delete</kbd>, or use **File › Delete**.
- **Reorder pages**: drag one or many thumbnails to a new position.
- **Insert pages** with **File › Insert ›**
  - **Page from File…**: every page of another PDF, or an image (PNG, JPEG, TIFF, BMP, GIF) as a page
  - **Blank Page**: the same size as the selected page
  - **Page from Scanner…**: through the standard Windows scan dialog (WIA)
- **Drop files** from Explorer onto the sidebar to insert them exactly where you drop them.
- **Rotate** pages, **undo/redo** everything, and **save** safely (the original is replaced atomically, never half-written).

Everything runs locally. No uploads, no accounts.

> New pages are inserted *after* the selected page, as in Preview.

## Requirements

- Windows 10 or 11 (x64). It also runs on Linux and macOS, but without scanning.
- Python 3.11 or newer, installed with the `py` launcher (python.org installer).
- For scanning, a WIA-compatible scanner or multifunction printer. Most are.

## Install (end users)

Download `WinPreview-<version>-setup-x64.exe` and run it. The installer is fully **offline**: Python, Qt and MuPDF are all bundled.

- It installs for the current user without admin rights. Choose "Install for all users" in the first dialog to install machine-wide.
- It creates a Start-menu entry and a **desktop icon**, and can optionally add WinPreview to the "Open with" menu for PDFs. It never changes your default PDF app.
- Uninstall from **Settings › Apps**.
- Silent install for IT deployment: `WinPreview-0.1.0-setup-x64.exe /VERYSILENT /ALLUSERS /TASKS=desktopicon`

## Getting started (from source)

```powershell
git clone <this repo> windows-preview-app
cd windows-preview-app
./scripts/setup.ps1          # creates .venv and installs dependencies
./scripts/run.ps1            # or: ./scripts/run.ps1 C:\path\to\file.pdf
```

If PowerShell blocks the scripts, allow local scripts once for your user:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Manual setup:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m winpreview
```

## Keyboard shortcuts

| Action | Shortcut |
|--------|----------|
| Open / Save / Save As | Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| Delete selected pages | Delete or Backspace |
| Insert page from file / blank page | Ctrl+Shift+I / Ctrl+Shift+B |
| Undo / Redo | Ctrl+Z / Ctrl+Y |
| Select all pages | Ctrl+A |
| Zoom in / out / fit width | Ctrl+= / Ctrl+- / Ctrl+0 (or Ctrl+mouse wheel) |
| Rotate left / right | Ctrl+L / Ctrl+R |
| Show/hide sidebar | Ctrl+Alt+S |

The full list is in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md#4-keyboard-shortcuts).

## Development

```powershell
./scripts/check.ps1   # ruff lint + format check + all tests
./scripts/build.ps1   # PyInstaller build -> dist\WinPreview\WinPreview.exe
./scripts/build_installer.ps1   # build + offline installer -> release\WinPreview-<ver>-setup-x64.exe
```

The installer needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) once on the build machine: `winget install --id JRSoftware.InnoSetup -e`. The version comes from `winpreview.__version__`.

The app icon's source is `src/winpreview/resources/icons/winpreview.svg`. After editing it, regenerate the `.ico` with `.venv\Scripts\python scripts\make_icon.py`.

The tests run headless (Qt `offscreen`) and generate their own PDFs, so the repository holds no binary fixtures. CI runs the same checks on `windows-latest` ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

### Project structure

```
windows-preview-app/
├── src/winpreview/
│   ├── app.py                 # entry point (QApplication, CLI argument)
│   ├── __main__.py            # python -m winpreview
│   ├── core/                  # Qt-free logic, fully unit tested
│   │   ├── document.py        #   PdfDocument: open/save, delete/move/insert/rotate, undo
│   │   └── scanner.py         #   Windows Image Acquisition (WIA) scanning
│   └── ui/                    # PySide6 interface
│       ├── main_window.py     #   menus, toolbar, actions, orchestration
│       ├── thumbnail_view.py  #   sidebar thumbnails + drag & drop
│       ├── page_view.py       #   continuous page view + zoom
│       ├── page_model.py      #   model shared by both views
│       └── renderer.py        #   page -> QPixmap LRU cache
│   └── resources/icons/       # app icon: SVG source + generated .ico/.png
├── tests/
│   ├── core/                  # document + scanner unit tests
│   └── ui/                    # pytest-qt window tests
├── docs/
│   ├── REQUIREMENTS.md        # features, IDs, status, shortcuts
│   └── PROJECT_CONTEXT.md     # architecture, decisions, limitations, roadmap
├── installer/winpreview.iss   # Inno Setup script for the offline installer
├── scripts/                   # setup / run / check / build / build_installer / make_icon
├── .claude/                   # Claude Code: shared settings + /check command
├── .gemini/                   # Gemini CLI settings
├── .github/workflows/ci.yml
├── AGENTS.md                  # instructions for AI coding agents (source of truth)
├── CLAUDE.md                  # Claude Code entry point (imports AGENTS.md)
├── GEMINI.md                  # Gemini CLI entry point (imports AGENTS.md)
└── pyproject.toml
```

### Working with AI coding agents

This repo is set up for Claude Code and Gemini CLI. [AGENTS.md](AGENTS.md) holds the shared rules: commands, architecture constraints, a checklist for adding page operations, and the definition of done. `CLAUDE.md` and `GEMINI.md` import it and add tool-specific notes. In Claude Code, `/check` runs the quality gate.

## Tech stack

PySide6 (Qt 6) for the UI, PyMuPDF (MuPDF) for rendering and page manipulation, and pywin32 for WIA scanning. See [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for the reasoning and the architecture.

## Known limitations

- Pages render on the UI thread, so very heavy pages may make scrolling stutter.
- Encrypted PDFs are saved without encryption.
- Scanning inserts one page per scan. Feeder batches are on the roadmap.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE). PyMuPDF is licensed under AGPL-3.0.

WinPreview is an independent project, not affiliated with Apple. "Preview" refers to the macOS application whose workflow inspired it.
