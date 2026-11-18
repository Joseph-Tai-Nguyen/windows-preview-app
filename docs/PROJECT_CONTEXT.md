# Project context

Background for anyone working on WinPreview, human or AI agent. It covers why the project exists, how it is built, and the decisions behind it. The requirements are in [REQUIREMENTS.md](REQUIREMENTS.md). The working rules for coding agents are in [AGENTS.md](../AGENTS.md).

## Why this exists

On a Mac, Preview makes simple PDF page surgery easy. You open the file, show thumbnails, delete or drag pages, insert another PDF or a scan, and save. Windows has no built-in equivalent. The free tools tend to be web uploaders (a privacy problem), full editors with subscriptions, or clumsy page-range dialogs. WinPreview recreates that one workflow natively on Windows and does nothing else.

The goal is a familiar *workflow*, not a clone of Preview's look. Names, icons and visuals are our own.

## Tech stack

| Concern | Choice | Why |
|---------|--------|-----|
| Language | Python 3.11+ (developed on 3.14) | Fast to iterate, good PDF libraries, easy for agents to work in. |
| GUI | PySide6 (Qt 6, LGPL) | Native-feeling Windows widgets, high-DPI support, solid drag and drop, a mature model/view framework. |
| PDF engine | PyMuPDF (`import pymupdf`, MuPDF, AGPL) | Fast rendering plus page delete, reorder (`select`), insert and rotate in one library. Converts images to PDF pages. |
| Word export | pdf2docx (MIT), with python-docx (MIT), fonttools (MIT), OpenCV headless (Apache-2.0), numpy (BSD) and fire (Apache-2.0) | Rebuilds paragraphs, tables and images from the PDF layout on top of PyMuPDF, fully offline. Imported only when exporting. |
| Excel export | openpyxl (MIT, with et-xmlfile, MIT) + PyMuPDF `Page.find_tables()` | PyMuPDF already detects tables. openpyxl writes the `.xlsx` with real numbers and formats. |
| Scanning | WIA Automation through pywin32 (`WIA.CommonDialog`) | Built into Windows, works with any WIA scanner or MFP, and provides the standard scan dialog. No SDK needed. |
| Tests | pytest + pytest-qt, Qt offscreen platform | Headless UI tests that work in CI. |
| Lint / format | ruff | One fast tool for both. |
| Packaging | PyInstaller (`scripts/build.ps1`) | Self-contained folder build for Windows, with the icon and version info embedded in the exe. |
| Installer | Inno Setup 6 (`installer/winpreview.iss`, `scripts/build_installer.ps1`) | A single offline `setup.exe` (about 115 MB, LZMA2; OpenCV for Word export is the largest addition, and `build.ps1` drops its unused 40 MB FFmpeg DLL). Per-user install without admin rights, an optional all-users install, desktop and Start-menu shortcuts, an optional "Open with" entry for PDFs, and a clean uninstall. Inno Setup is a build-time tool only; it is not shipped with the app. |

**License note:** the repository is GPL-3.0. PyMuPDF is AGPL-3.0, and GPLv3 code may be combined with it. The Office-export libraries (pdf2docx, openpyxl and their dependencies) are MIT, BSD or Apache-2.0, all compatible with GPLv3. A future closed-source or permissive release would need a commercial MuPDF license, or a switch to `pypdfium2` (rendering) plus `pypdf` (page operations).

## Architecture

```
┌────────────────────────── ui (PySide6) ───────────────────────────┐
│ MainWindow ── menus, toolbar, actions, dialogs, orchestration     │
│   ├─ ThumbnailView + ThumbnailDelegate   (sidebar, drag & drop)   │
│   ├─ PageView + PageDelegate             (continuous main view)   │
│   └─ PageListModel  (shared by both views)                        │
│        └─ PixmapCache (one per delegate, LRU, cleared on reset)   │
└───────────────────────────────┬───────────────────────────────────┘
                                │ calls / returns rows to select
┌───────────────────────── core (no Qt) ────────────────────────────┐
│ PdfDocument ── open/save, delete/move/insert/rotate, undo/redo    │
│ office      ── pages → Word (.docx) / tables → Excel (.xlsx)      │
│ scanner     ── WIA acquire → image file                           │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                             PyMuPDF
```

### How a page operation flows

1. A user action (key, menu, drag) reaches a `MainWindow` method, for example `delete_selected`.
2. `MainWindow._apply(op)` calls the `PdfDocument` method. That method:
   - validates its input and raises `DocumentError` with a user-facing message if something is wrong,
   - stores an undo snapshot (`_checkpoint`), mutates the PyMuPDF document, and returns the rows that should be selected afterwards.
3. `MainWindow._after_change(rows)` resets the model (`PageListModel.refresh`). Both views re-layout, the delegates' pixmap caches are cleared, the scroll position is restored, the returned rows are selected, and the action states and title are updated.

The model is fully reset after every change on purpose. Page operations restructure the document anyway, and a reset keeps both views, both caches and the selection consistent with no fine-grained bookkeeping. If that ever becomes slow for very large documents, switch to `beginMoveRows` / `beginRemoveRows` with a cache keyed by page identity.

### Undo and redo

Snapshot-based: before each mutation, the whole document is serialized with `Document.tobytes()`. Undo reopens the previous bytes. This is simple and exactly correct for every operation, at the cost of memory on very large PDFs. History is capped at `DEFAULT_UNDO_LIMIT` (30). Each snapshot carries a revision id, so undoing back to the saved revision clears the modified flag.

### Drag and drop

`ThumbnailView` handles drag and drop itself. It does **not** use Qt's `dropMimeData` or internal-move path. Qt's internal move removes the source rows after the drop, which conflicts with "rebuild the document, then reset the model". The view:

- works out an insert-before row from the cursor's y position (`drop_row_at`),
- paints its own insertion line,
- reports `CopyAction` back to Qt so that `startDrag` leaves the rows alone,
- emits `pagesMoved(rows, dest)` or `filesDropped(paths, dest)` through `QTimer.singleShot(0, …)`, so the model is not reset while Qt is still inside the drag loop.

### Files on disk

Documents are read fully into memory (`pymupdf.open(stream=…)`). That means:

- the original file is never locked, so Save can write a temp file in the same folder and `os.replace` it over the original (an atomic swap on NTFS),
- undo snapshots and the live document never depend on the file still existing.

## Repository layout

```
src/winpreview/
  app.py               QApplication bootstrap, CLI file argument
  core/document.py     PdfDocument (all page logic, undo, save)
  core/scanner.py      WIA scanning
  ui/main_window.py    Window, actions, menus, operation orchestration
  ui/thumbnail_view.py Sidebar view, delegate, drag & drop
  ui/page_view.py      Main continuous page view, zoom
  ui/page_model.py     Shared Qt list model
  ui/renderer.py       PixmapCache (RenderedPage → QPixmap, LRU)
  resources/icons/     App icon: winpreview.svg (source) → .ico/.png via scripts/make_icon.py
installer/             Inno Setup script
tests/core/            Pure-Python tests (no Qt)
tests/ui/              pytest-qt tests (offscreen)
docs/                  Requirements, this file
scripts/               setup / run / check / build PowerShell helpers
```

## Exporting to Word and Excel

`PdfDocument.export_word` / `export_excel` validate the input, copy the selected pages into a scratch document, and hand that to `core/office.py`. The result is written to a temp file next to the target and moved into place with `os.replace`, like `save()`. Decisions worth knowing:

- **The copy has its rotation baked in** (`Page.remove_rotation()`). Both converters read unrotated page space, so a landscape page stored as sideways content plus `/Rotate 90` would otherwise lose its text (pdf2docx skips vertical text) or its tables. Copying also strips encryption, and it means later edits can't affect an export that is still running.
- **pdf2docx is driven step by step** (`load_pages`, `parse_document`, then `page.parse` per page, then `make_docx`) instead of `convert()`, so the UI gets per-page progress and can cancel, and so pages that fail are reported instead of only logged. Multiprocessing stays off because it breaks in a frozen exe.
- **pdf2docx calls `logging.basicConfig` on import** and logs every step to the root logger. `_quiet_root_logger()` puts a temporary `NullHandler` on the root logger for the duration and restores it afterwards. It also imports the legacy `fitz` alias. That deprecation warning is silenced at import; our own code still uses `pymupdf`.
- **Cell text is read from the cell rectangles** (`page.get_textbox(cell)`), not `Table.extract()`. With PyMuPDF 2.x, `extract()` can split “1,200” into “1200” and “,” on separate lines.
- **Table detection** tries `strategy="lines"` (ruled tables) first and falls back to `strategy="text"` only for pages without ruled tables, because the text strategy finds borderless tables but leaves ordinary prose alone.
- **Numbers become numbers** only when nothing is lost: leading-zero codes, values over 15 digits, and ambiguous formats such as “1.234,56” stay text. The first row of each sheet is treated as the header and is never converted.

## Known limitations

- **Rendering happens on the GUI thread** inside the delegates' `paint`. That is fine for typical documents, but very heavy pages can stutter while scrolling. Next step: render in a `QThreadPool` and show placeholders (VIEW-7).
- **Saving an encrypted PDF writes it without encryption** (DOC-10).
- **Scanning gets one page per dialog.** Feeder (ADF) batches need the lower-level WIA `Item.Transfer` loop (PAGE-10).
- **Undo memory** grows with document size times history depth.
- **Office export is layout reconstruction, not a perfect round trip.** Complex layouts (multi-column text, text boxes, forms) can come out shifted in Word. Excel only gets tables: a ruled cell holding several lines of text may be split into one row per line (PyMuPDF behavior), and very small borderless tables (for example three rows of two columns) aren't recognized. Scanned pages contain no text, so Word gets a picture of them and Excel finds no tables. OCR (Tesseract) would fix that, but it is a separate install.
- **Office export runs on the GUI thread.** The progress dialog keeps the window responsive between pages, but one very complex page can freeze the window for a few seconds.
- `Document.select()` (used for reordering) rebuilds the page tree. Outline (bookmark) entries that point to deleted pages are dropped. That is acceptable for this tool.

## Roadmap (suggested order)

1. Background rendering and highlighting the current page's thumbnail (VIEW-7, VIEW-9).
2. Multi-page feeder scanning (PAGE-10).
3. Export selected pages to a new PDF and drag pages between windows (PAGE-12, PAGE-11, DOC-9).
4. Keep encryption on save (DOC-10) and a recent-files list (DOC-8).
5. Code signing for the exe and the installer, to avoid SmartScreen warnings. An optional MSIX package for Store or Intune distribution.

Done already: the app icon and the offline Inno Setup installer.

## App icon

The icon is original artwork: two fanned PDF pages on a blue rounded tile, with an orange accent line. It is intentionally *not* Preview's magnifier-and-photos icon. `winpreview.svg` is the source. `scripts/make_icon.py` renders it with QtSvg into a 10-size `.ico` (16 to 256 px, PNG-compressed entries) with no extra dependencies. The `.ico` is used for:

- the window and taskbar (`QApplication.setWindowIcon`, plus an explicit AppUserModelID so the taskbar doesn't show python.exe's icon),
- the exe (`pyinstaller --icon`),
- the installer and its desktop and Start-menu shortcuts.

## Glossary

- **Row / page index**: 0-based position of a page. Shown to users as 1-based.
- **Insert-before row**: the destination convention used by `move_pages` and drops. `page_count` means "append".
- **Snapshot**: serialized document bytes plus a revision id, used for undo and redo.
