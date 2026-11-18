# Requirements

Product requirements for **WinPreview**, a Windows desktop app for organizing the pages of PDF files, modeled on the page-editing workflow of macOS Preview.

Status legend: ✅ implemented · 🟡 partial · ⬜ not started

Priority: **Must** = needed for v1.0 · **Should** = expected soon after v1.0 · **Could** = nice to have.

## 1. Users and goals

The main user has a PDF and wants to fix its pages quickly: remove some, put them in the right order, add pages from another file, a blank page, or a fresh scan. Then they save, without learning a full PDF editor.

Goals:

- Page operations are direct manipulations: select thumbnails, then press Delete or drag.
- It is always safe: undo every change, and saving never corrupts the original.
- It feels at home on Windows (shortcuts, file dialogs, the WIA scanner dialog).

Non-goals for v1: editing page content (text, annotations, forms), OCR, digital signatures, or a PDF reader with search and bookmarks.

## 2. Functional requirements

### 2.1 Documents

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| DOC-1 | Open a PDF via File › Open (Ctrl+O), the command line (`winpreview file.pdf`) or by dropping it on the window. | Must | ✅ |
| DOC-2 | Prompt for a password when the PDF is encrypted, and re-prompt if the password is wrong. | Must | ✅ |
| DOC-3 | Save (Ctrl+S) overwrites the file atomically through a temp file and `os.replace`; Save As (Ctrl+Shift+S) writes a new file. | Must | ✅ |
| DOC-4 | The window title shows the file name and an unsaved-changes marker `*`. | Must | ✅ |
| DOC-5 | Closing or opening another file with unsaved changes asks Save / Discard / Cancel. | Must | ✅ |
| DOC-6 | File › New creates an empty document that pages can be inserted into, for example to build a PDF from scans. | Should | ✅ |
| DOC-7 | The source file is not locked while it is open, so it can be renamed, synced or overwritten. | Must | ✅ |
| DOC-8 | Recent files list. | Could | ⬜ |
| DOC-9 | Multiple documents in separate windows. | Could | ⬜ |
| DOC-10 | Keep the original encryption when saving an encrypted PDF. | Should | ⬜ |

### 2.2 Viewing

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| VIEW-1 | A sidebar shows a thumbnail and page number for every page. | Must | ✅ |
| VIEW-2 | The main area shows all pages in one continuous scroll. | Must | ✅ |
| VIEW-3 | Clicking a thumbnail scrolls the main view to that page. | Must | ✅ |
| VIEW-4 | Zoom in and out (Ctrl+=, Ctrl+-, Ctrl+wheel) and fit width (Ctrl+0). | Must | ✅ |
| VIEW-5 | The status bar shows "Page X of N" and the number of selected pages. | Should | ✅ |
| VIEW-6 | Show or hide the sidebar (Ctrl+Alt+S). | Should | ✅ |
| VIEW-7 | Pages render in the background so scrolling never blocks the UI. | Should | ⬜ |
| VIEW-8 | Rendering is sharp on high-DPI displays. | Must | ✅ |
| VIEW-9 | Scrolling the main view highlights the current page's thumbnail. | Could | ⬜ |

### 2.3 Page operations

All operations act on the thumbnail selection, can be undone, and leave the affected pages selected afterwards.

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| PAGE-1 | Select pages with click, Ctrl+click, Shift+click and Ctrl+A. | Must | ✅ |
| PAGE-2 | **Delete** the selected pages with the Delete or Backspace key, File › Delete, the toolbar or the context menu. | Must | ✅ |
| PAGE-3 | Deleting is refused if it would remove every page. | Must | ✅ |
| PAGE-4 | **Reorder** pages by dragging one or many thumbnails. An insertion line shows where they will land. | Must | ✅ |
| PAGE-5 | **File › Insert › Page from File…** inserts all pages of a PDF, or an image (PNG, JPEG, TIFF, BMP, GIF) as one page, after the selection. Multiple files can be chosen. | Must | ✅ |
| PAGE-6 | **File › Insert › Blank Page** inserts a page with the same size as the selected page. | Must | ✅ |
| PAGE-7 | **File › Insert › Page from Scanner…** scans through the Windows WIA dialog and inserts the result after the selection. | Must | ✅ |
| PAGE-8 | Drop PDF or image files from Explorer onto the sidebar to insert them at the drop position. | Should | ✅ |
| PAGE-9 | Rotate the selected pages left or right (Ctrl+L / Ctrl+R). | Should | ✅ |
| PAGE-10 | Scan several pages in one go from a document feeder. | Should | ⬜ |
| PAGE-11 | Drag thumbnails between two document windows. | Could | ⬜ |
| PAGE-12 | Export the selected pages to a new PDF. | Could | ⬜ |
| PAGE-13 | Crop pages. | Could | ⬜ |
| PAGE-14 | **File › Export as Image…** (Ctrl+Shift+E) saves the selected pages as PNG or JPEG at 72–600 DPI (default 300), optionally with a transparent background (PNG only). One page goes to a chosen file; several go to a folder as “<name> - Page N.png”. | Could | ✅ |

When nothing is selected, inserts go after the page currently in view. In an empty document they go at the start.

### 2.4 Editing history

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| HIST-1 | Undo (Ctrl+Z) and Redo (Ctrl+Y / Ctrl+Shift+Z) for every page operation. | Must | ✅ |
| HIST-2 | Undoing back to the saved state clears the unsaved-changes marker. | Must | ✅ |
| HIST-3 | Inserting several files at once is a single undo step. | Could | ⬜ (currently one step per file) |

## 3. Non-functional requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Platform | Windows 10 (22H2) and Windows 11, x64. Linux and macOS should still run, but scanning is unavailable there. |
| NFR-2 | Performance | Open a 200-page PDF and show the first page in under 1 s. Each page operation finishes in under 500 ms on a 200-page, 20 MB document. |
| NFR-3 | Memory | The undo history keeps at most `DEFAULT_UNDO_LIMIT` (30) document snapshots. The pixmap caches are bounded (400 thumbnails, 16 pages). |
| NFR-4 | Safety | A failed save never damages the existing file, because the app writes to a temp file and then renames it. |
| NFR-5 | Accessibility | Every command is reachable from the menus and has a keyboard shortcut where it makes sense. Views have accessible names. |
| NFR-6 | Distribution | ✅ An offline installer (`release/WinPreview-<ver>-setup-x64.exe`, Inno Setup) with desktop and Start-menu shortcuts and a clean uninstall. Installs per-user without admin rights; all-users is optional. Code signing and MSIX are still to do. |
| NFR-9 | Branding | ✅ An original app icon in the window title bar, taskbar, exe and shortcuts. No Apple artwork. |
| NFR-7 | License | GPL-3.0-or-later. PyMuPDF is AGPL-3.0, which is compatible. Any change of license must account for that. |
| NFR-8 | Quality | The core logic has unit tests, the main UI flows have pytest-qt tests, and ruff runs clean. CI runs on `windows-latest`. |

## 4. Keyboard shortcuts

| Action | Shortcut |
|--------|----------|
| New / Open / Save / Save As | Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| Close / Exit | Ctrl+W (Ctrl+F4) / Ctrl+Q |
| Delete selected pages | Delete, Backspace |
| Insert page from file / blank page | Ctrl+Shift+I / Ctrl+Shift+B |
| Export selected pages as images | Ctrl+Shift+E |
| Undo / Redo | Ctrl+Z / Ctrl+Y, Ctrl+Shift+Z |
| Select all pages | Ctrl+A |
| Zoom in / out / fit width | Ctrl+= / Ctrl+- / Ctrl+0, Ctrl+mouse wheel |
| Rotate left / right | Ctrl+L / Ctrl+R |
| Toggle sidebar | Ctrl+Alt+S |
