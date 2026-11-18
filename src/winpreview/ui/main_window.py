"""Main application window: menus, toolbar, sidebar + page view."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStackedWidget,
    QToolButton,
)

from winpreview import APP_NAME, __version__
from winpreview.core import DocumentError, PasswordRequiredError, PdfDocument, scanner
from winpreview.core.document import (
    DEFAULT_EXPORT_DPI,
    EXPORT_IMAGE_FORMATS,
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    filter_insertable,
)
from winpreview.ui.export_dialog import ExportImageDialog, ExportOptions
from winpreview.ui.page_model import PageListModel
from winpreview.ui.page_view import PageView
from winpreview.ui.thumbnail_view import ThumbnailView

T = TypeVar("T")

PDF_FILTER = "PDF documents (*.pdf)"
INSERT_FILTER = (
    "PDFs and images ("
    + " ".join(f"*{ext}" for ext in sorted(PDF_EXTENSIONS | IMAGE_EXTENSIONS))
    + ");;"
    + PDF_FILTER
    + ";;All files (*)"
)
EXPORT_FILTERS = {".png": "PNG image (*.png)", ".jpg": "JPEG image (*.jpg *.jpeg)"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._doc: PdfDocument | None = None
        self._settings = QSettings()

        self.model = PageListModel(self)
        self.thumbnails = ThumbnailView()
        self.thumbnails.setModel(self.model)
        self.page_view = PageView()
        self.page_view.setModel(self.model)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.thumbnails)
        self.splitter.addWidget(self.page_view)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([180, 820])
        self.splitter.setChildrenCollapsible(False)

        self.placeholder = QLabel("Open a PDF with File › Open (Ctrl+O)\nor drop one here.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setEnabled(False)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.splitter)
        self.setCentralWidget(self.stack)

        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._connect_signals()

        self.setAcceptDrops(True)
        self.resize(1100, 800)
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._update_ui()

    # ================================================================== setup
    def _action(
        self,
        text: str,
        slot: Callable[[], object],
        shortcut: QKeySequence | str | list | None = None,
        tip: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(lambda _checked=False: slot())
        if isinstance(shortcut, list):
            action.setShortcuts([QKeySequence(s) for s in shortcut])
        elif shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
            action.setToolTip(tip)
        return action

    def _create_actions(self) -> None:
        std = QKeySequence.StandardKey
        self.act_new = self._action("&New", self.new_document, std.New, "Create an empty document")
        self.act_open = self._action("&Open…", self.open_file, std.Open, "Open a PDF")
        self.act_insert_file = self._action(
            "Page from &File…",
            self.insert_from_file,
            "Ctrl+Shift+I",
            "Insert the pages of a PDF or an image after the selection",
        )
        self.act_insert_blank = self._action(
            "&Blank Page",
            self.insert_blank_page,
            "Ctrl+Shift+B",
            "Insert a blank page after the selection",
        )
        self.act_insert_scan = self._action(
            "Page from &Scanner…",
            self.insert_from_scanner,
            None,
            "Scan a page and insert it after the selection",
        )
        self.act_delete = self._action(
            "&Delete",
            self.delete_selected,
            [QKeySequence(Qt.Key.Key_Delete), QKeySequence(Qt.Key.Key_Backspace)],
            "Delete the selected pages",
        )
        self.act_export_image = self._action(
            "&Export as Image…",
            self.export_selected_as_images,
            "Ctrl+Shift+E",
            "Export the selected pages as PNG or JPEG images",
        )
        self.act_export_image.setIconText("Export Image")
        self.act_save = self._action("&Save", self.save, std.Save, "Save the document")
        self.act_save_as = self._action("Save &As…", self.save_as, "Ctrl+Shift+S")
        self.act_close = self._action("&Close", self.close_document, std.Close)
        self.act_exit = self._action("E&xit", self.close, "Ctrl+Q")

        self.act_undo = self._action("&Undo", self.undo, std.Undo)
        self.act_redo = self._action("&Redo", self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"])
        self.act_select_all = self._action("Select &All", self.select_all, std.SelectAll)

        self.act_sidebar = self._action("Show &Sidebar", self._toggle_sidebar, "Ctrl+Alt+S")
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self.act_zoom_in = self._action(
            "Zoom &In", self.page_view.zoom_in, ["Ctrl+=", "Ctrl++"], "Zoom in"
        )
        self.act_zoom_out = self._action("Zoom &Out", self.page_view.zoom_out, "Ctrl+-", "Zoom out")
        self.act_fit_width = self._action(
            "Zoom to &Fit Width", self.page_view.fit_width, "Ctrl+0", "Fit pages to the window"
        )

        self.act_rotate_left = self._action(
            "Rotate &Left",
            lambda: self.rotate_selected(-90),
            "Ctrl+L",
            "Rotate selected pages left",
        )
        self.act_rotate_right = self._action(
            "Rotate &Right",
            lambda: self.rotate_selected(90),
            "Ctrl+R",
            "Rotate selected pages right",
        )
        self.act_about = self._action(f"&About {APP_NAME}", self._about)

    def _create_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        self.insert_menu = QMenu("&Insert", self)
        self.insert_menu.addAction(self.act_insert_file)
        self.insert_menu.addAction(self.act_insert_blank)
        self.insert_menu.addAction(self.act_insert_scan)
        file_menu.addMenu(self.insert_menu)
        file_menu.addAction(self.act_delete)
        file_menu.addAction(self.act_export_image)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_close)
        file_menu.addAction(self.act_exit)

        edit_menu = bar.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_select_all)

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self.act_sidebar)
        view_menu.addSeparator()
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_fit_width)

        tools_menu = bar.addMenu("&Tools")
        tools_menu.addAction(self.act_rotate_left)
        tools_menu.addAction(self.act_rotate_right)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)

        # Right-click menu on thumbnails.
        self.thumbnails.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _create_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self.act_sidebar)
        toolbar.addSeparator()
        toolbar.addAction(self.act_zoom_out)
        toolbar.addAction(self.act_zoom_in)
        toolbar.addAction(self.act_fit_width)
        toolbar.addSeparator()
        toolbar.addAction(self.act_rotate_left)
        toolbar.addAction(self.act_rotate_right)
        toolbar.addSeparator()
        insert_button = QToolButton()
        insert_button.setText("Insert")
        insert_button.setMenu(self.insert_menu)
        insert_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(insert_button)
        toolbar.addAction(self.act_delete)
        toolbar.addAction(self.act_export_image)

    def _connect_signals(self) -> None:
        sel = self.thumbnails.selectionModel()
        sel.selectionChanged.connect(lambda *_: self._update_ui())
        sel.currentChanged.connect(lambda current, _prev: self._on_current_thumbnail(current.row()))
        self.thumbnails.pagesMoved.connect(self.move_pages)
        self.thumbnails.filesDropped.connect(self.insert_files)
        self.thumbnails.customContextMenuRequested.connect(self._show_thumbnail_menu)
        self.page_view.currentPageChanged.connect(lambda _row: self._update_status())

    # ================================================================== document lifecycle
    def document(self) -> PdfDocument | None:
        return self._doc

    def set_document(self, doc: PdfDocument | None) -> None:
        old, self._doc = self._doc, doc
        self.model.set_document(doc)
        if old is not None:
            old.close()
        self.stack.setCurrentWidget(self.splitter if doc is not None else self.placeholder)
        if doc is not None:
            self.page_view.fit_width()
            if doc.page_count:
                self._select_rows([0])
        self._update_ui()

    def new_document(self) -> None:
        if self._maybe_save():
            self.set_document(PdfDocument.new())
            self.statusBar().showMessage("Use File › Insert to add pages.", 5000)

    def open_file(self, path: str | Path | None = None) -> bool:
        if not self._maybe_save():
            return False
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open", self._last_dir(), PDF_FILTER)
            if not path:
                return False
        path = Path(path)
        doc = self._with_password(lambda password: PdfDocument.open(path, password))
        if doc is None:
            return False
        self._remember_dir(path)
        self.set_document(doc)
        return True

    def close_document(self) -> None:
        if self._maybe_save():
            self.set_document(None)

    def save(self) -> bool:
        if self._doc is None:
            return False
        if self._doc.path is None:
            return self.save_as()
        return self._save_to(None)

    def save_as(self) -> bool:
        if self._doc is None:
            return False
        suggested = str(
            Path(self._last_dir()) / (self._doc.path.name if self._doc.path else "Untitled.pdf")
        )
        path, _ = QFileDialog.getSaveFileName(self, "Save As", suggested, PDF_FILTER)
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".pdf":
            target = target.with_name(target.name + ".pdf")
        if self._save_to(target):
            self._remember_dir(target)
            return True
        return False

    def _save_to(self, target: Path | None) -> bool:
        assert self._doc is not None
        try:
            self._doc.save(target)
        except DocumentError as exc:
            self._error(str(exc))
            return False
        self.statusBar().showMessage(f"Saved “{self._doc.display_name}”.", 4000)
        self._update_ui()
        return True

    def _maybe_save(self) -> bool:
        """Ask to save unsaved changes. False means the user cancelled."""
        if self._doc is None or not self._doc.is_modified:
            return True
        if self._doc.page_count == 0:
            return True  # nothing that could be saved
        buttons = (
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Do you want to save the changes made to “{self._doc.display_name}”?",
            buttons,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    # ================================================================== page operations
    def selected_rows(self) -> list[int]:
        return self.thumbnails.selected_rows()

    def insert_position(self) -> int:
        """Preview inserts after the (last) selected page; otherwise after the
        page being viewed; in an empty document at the start."""
        if self._doc is None or self._doc.page_count == 0:
            return 0
        rows = self.selected_rows()
        if rows:
            return rows[-1] + 1
        current = self.page_view.current_page()
        return current + 1 if current >= 0 else self._doc.page_count

    def delete_selected(self) -> None:
        if self._doc is None:
            return
        rows = self.selected_rows()
        if rows:
            self._apply(lambda: self._doc.delete_pages(rows))

    def move_pages(self, rows: list[int], destination: int) -> None:
        if self._doc is not None and rows:
            self._apply(lambda: self._doc.move_pages(rows, destination))

    def rotate_selected(self, degrees: int) -> None:
        if self._doc is None:
            return
        rows = self.selected_rows()
        if rows:
            self._apply(lambda: self._doc.rotate_pages(rows, degrees))

    def insert_blank_page(self) -> None:
        if self._doc is not None:
            at = self.insert_position()
            self._apply(lambda: self._doc.insert_blank_page(at))

    def insert_from_file(self) -> None:
        if self._doc is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Insert", self._last_dir(), INSERT_FILTER)
        if paths:
            self._remember_dir(Path(paths[0]))
            self.insert_files([Path(p) for p in paths], self.insert_position())

    def insert_files(self, paths: list[Path], at: int) -> None:
        """Insert PDFs/images in order before page ``at``."""
        if self._doc is None:
            return
        inserted: list[int] = []
        for path in filter_insertable(paths):
            rows = self._with_password(
                lambda password, p=path, pos=at: self._doc.insert_file(p, pos, password)
            )
            if rows is None:
                break
            inserted.extend(rows)
            at += len(rows)
        if inserted:
            self._after_change(list(range(inserted[0], inserted[-1] + 1)))

    def insert_from_scanner(self) -> None:
        if self._doc is None:
            return
        at = self.insert_position()
        with tempfile.TemporaryDirectory(prefix="winpreview-scan-") as tmp:
            try:
                image = scanner.acquire_image(tmp)
            except scanner.ScannerError as exc:
                self._error(str(exc), title="Scanner")
                return
            if image is not None:
                self._apply(lambda: self._doc.insert_file(image, at))

    def export_selected_as_images(self) -> None:
        """Ask for format and resolution, then where to save, and export the selection.

        One page is saved to a chosen file; several pages go to a chosen folder as
        “<document> - Page N.png”. Exporting does not change the document.
        """
        if self._doc is None:
            return
        rows = self.selected_rows()
        if not rows:
            return
        options = ExportImageDialog.get_options(
            self, self._doc.page_size(rows[0]), len(rows), self._export_defaults()
        )
        if options is None:
            return
        targets = self._ask_export_targets(rows, options.extension)
        if not targets:
            return
        self._settings.setValue("export/extension", options.extension)
        self._settings.setValue("export/dpi", options.dpi)
        self._settings.setValue("export/transparent", options.transparent)

        done = self._export_pages(list(zip(rows, targets, strict=True)), options)
        if done == len(rows) == 1:
            message = f"Exported page {rows[0] + 1} to “{targets[0].name}”."
        elif done == len(rows):
            message = f"Exported {done} pages to “{targets[0].parent.name}”."
        else:
            message = f"Exported {done} of {len(rows)} pages."
        self.statusBar().showMessage(message, 5000)

    def undo(self) -> None:
        if self._doc is not None and self._doc.can_undo:
            keep = self.selected_rows()[:1]
            self._doc.undo()
            self._after_change(keep)

    def redo(self) -> None:
        if self._doc is not None and self._doc.can_redo:
            keep = self.selected_rows()[:1]
            self._doc.redo()
            self._after_change(keep)

    def select_all(self) -> None:
        self.thumbnails.selectAll()

    # ================================================================== helpers
    def _apply(self, operation: Callable[[], list[int]]) -> bool:
        try:
            rows = operation()
        except DocumentError as exc:
            self._error(str(exc))
            return False
        self._after_change(rows)
        return True

    def _after_change(self, rows: list[int]) -> None:
        """Refresh views after the document changed and select ``rows``."""
        scroll = self.page_view.verticalScrollBar().value()
        self.model.refresh()
        self.page_view.doItemsLayout()
        self.page_view.verticalScrollBar().setValue(scroll)
        count = self._doc.page_count if self._doc else 0
        self._select_rows([r for r in rows if 0 <= r < count] or ([0] if count else []))
        self._update_ui()

    def _select_rows(self, rows: list[int]) -> None:
        if not rows:
            return
        selection = QItemSelection()
        for row in rows:
            index = self.model.index(row, 0)
            selection.select(index, index)
        sel = self.thumbnails.selectionModel()
        sel.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        sel.setCurrentIndex(
            self.model.index(rows[0], 0), QItemSelectionModel.SelectionFlag.NoUpdate
        )
        self.thumbnails.scrollTo(self.model.index(rows[0], 0))

    def _on_current_thumbnail(self, row: int) -> None:
        if row >= 0:
            self.page_view.scroll_to_page(row)

    def _with_password(self, operation: Callable[[str | None], T]) -> T | None:
        password: str | None = None
        while True:
            try:
                return operation(password)
            except PasswordRequiredError as exc:
                password, ok = QInputDialog.getText(
                    self,
                    "Password Required",
                    f"{exc}\n\nPassword:",
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return None
            except DocumentError as exc:
                self._error(str(exc))
                return None

    def _export_defaults(self) -> ExportOptions:
        extension = str(self._settings.value("export/extension", ".png"))
        try:
            dpi = int(self._settings.value("export/dpi", DEFAULT_EXPORT_DPI))
        except (TypeError, ValueError):
            dpi = DEFAULT_EXPORT_DPI
        transparent = self._settings.value("export/transparent", False, type=bool)
        return ExportOptions(extension, dpi, bool(transparent))

    def _ask_export_targets(self, rows: list[int], extension: str) -> list[Path]:
        """The output file for each row, or [] if the user cancelled."""
        assert self._doc is not None
        stem = self._doc.path.stem if self._doc.path else "Untitled"
        if len(rows) == 1:
            suggested = Path(self._last_dir()) / f"{stem} - Page {rows[0] + 1}{extension}"
            path, _ = QFileDialog.getSaveFileName(
                self, "Export as Image", str(suggested), EXPORT_FILTERS[extension]
            )
            if not path:
                return []
            target = Path(path)
            if target.suffix.lower() not in EXPORT_IMAGE_FORMATS:
                target = target.with_name(target.name + extension)
            self._remember_dir(target)
            return [target]

        folder = QFileDialog.getExistingDirectory(self, "Export Pages to Folder", self._last_dir())
        if not folder:
            return []
        folder = Path(folder)
        targets = [folder / f"{stem} - Page {row + 1}{extension}" for row in rows]
        existing = sum(1 for target in targets if target.exists())
        if existing:
            noun = "file already exists" if existing == 1 else "files already exist"
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"{existing} {noun} in “{folder.name}”. Do you want to replace them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return []
        self._settings.setValue("paths/lastDir", str(folder))
        return targets

    def _export_pages(self, jobs: list[tuple[int, Path]], options: ExportOptions) -> int:
        """Export each (row, target); returns how many pages were written."""
        assert self._doc is not None
        progress: QProgressDialog | None = None
        if len(jobs) > 1:
            progress = QProgressDialog("Exporting pages…", "Cancel", 0, len(jobs), self)
            progress.setWindowTitle("Export as Image")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(500)
        done = 0
        error: str | None = None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for row, target in jobs:
                if progress is not None:
                    progress.setValue(done)
                    if progress.wasCanceled():
                        break
                try:
                    self._doc.export_page_image(
                        row, target, dpi=options.dpi, transparent=options.transparent
                    )
                except DocumentError as exc:
                    error = str(exc)
                    break
                done += 1
        finally:
            QApplication.restoreOverrideCursor()
            if progress is not None:
                progress.close()
                progress.deleteLater()
        if error is not None:
            self._error(error)
        return done

    def _show_thumbnail_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction(self.act_insert_blank)
        menu.addAction(self.act_insert_file)
        menu.addSeparator()
        menu.addAction(self.act_rotate_left)
        menu.addAction(self.act_rotate_right)
        menu.addSeparator()
        menu.addAction(self.act_export_image)
        menu.addAction(self.act_delete)
        menu.exec(self.thumbnails.viewport().mapToGlobal(pos))

    def _toggle_sidebar(self) -> None:
        self.thumbnails.setVisible(self.act_sidebar.isChecked())

    def _update_ui(self) -> None:
        doc = self._doc
        has_doc = doc is not None
        count = doc.page_count if doc else 0
        selected = len(self.selected_rows()) if has_doc else 0

        self.act_insert_file.setEnabled(has_doc)
        self.act_insert_blank.setEnabled(has_doc)
        self.act_insert_scan.setEnabled(has_doc and scanner.is_supported())
        self.act_delete.setEnabled(0 < selected < count)
        self.act_export_image.setEnabled(selected > 0)
        self.act_rotate_left.setEnabled(selected > 0)
        self.act_rotate_right.setEnabled(selected > 0)
        self.act_save.setEnabled(has_doc and count > 0)
        self.act_save_as.setEnabled(has_doc and count > 0)
        self.act_close.setEnabled(has_doc)
        self.act_undo.setEnabled(bool(doc and doc.can_undo))
        self.act_redo.setEnabled(bool(doc and doc.can_redo))
        self.act_select_all.setEnabled(count > 0)
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_fit_width):
            action.setEnabled(count > 0)

        if doc is None:
            self.setWindowTitle(APP_NAME)
            self.setWindowModified(False)
        else:
            self.setWindowTitle(f"{doc.display_name}[*] — {APP_NAME}")
            self.setWindowModified(doc.is_modified)
        self._update_status()

    def _update_status(self) -> None:
        doc = self._doc
        if doc is None:
            self.status_label.setText("")
            return
        count = doc.page_count
        if count == 0:
            self.status_label.setText("No pages")
            return
        current = max(self.page_view.current_page(), 0) + 1
        text = f"Page {current} of {count}"
        selected = len(self.selected_rows())
        if selected > 1:
            text += f"  ·  {selected} selected"
        self.status_label.setText(text)

    def _error(self, message: str, title: str = APP_NAME) -> None:
        QMessageBox.warning(self, title, message)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>"
            "A PDF page organizer for Windows inspired by macOS Preview.<br><br>"
            "Built with PySide6 (Qt) and PyMuPDF. Licensed under the GNU GPL v3.",
        )

    def _last_dir(self) -> str:
        return str(self._settings.value("paths/lastDir", str(Path.home())))

    def _remember_dir(self, path: Path) -> None:
        self._settings.setValue("paths/lastDir", str(Path(path).parent))

    # ================================================================== window events
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
            for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Dropping a PDF on the window (outside the sidebar) opens it."""
        pdfs = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
        ]
        if pdfs:
            event.acceptProposedAction()
            self.open_file(pdfs[0])

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        self._settings.setValue("window/geometry", self.saveGeometry())
        self.set_document(None)
        event.accept()
