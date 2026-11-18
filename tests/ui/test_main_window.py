from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from tests.conftest import page_labels
from winpreview.ui.export_dialog import ExportImageDialog, ExportOptions
from winpreview.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, monkeypatch):
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(900, 700)
    win.show()
    qtbot.waitExposed(win)
    errors: list[str] = []
    monkeypatch.setattr(win, "_error", lambda message, title=None: errors.append(message))
    win.errors = errors
    # Never block on the "save changes?" prompt during teardown.
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    return win


def select(win: MainWindow, rows: list[int]) -> None:
    win._select_rows(rows)


def test_starts_empty(window):
    assert window.document() is None
    assert window.stack.currentWidget() is window.placeholder
    assert not window.act_delete.isEnabled()


def test_open_shows_thumbnails(window, make_pdf):
    assert window.open_file(make_pdf(4))
    assert window.model.rowCount() == 4
    assert window.thumbnails.selected_rows() == [0]
    assert window.stack.currentWidget() is window.splitter
    assert "doc.pdf" in window.windowTitle()


def test_delete_via_menu_action(window, make_pdf):
    window.open_file(make_pdf(4))
    select(window, [1, 2])
    assert window.act_delete.isEnabled()
    window.act_delete.trigger()
    assert page_labels(window.document()) == ["P1", "P4"]
    assert window.model.rowCount() == 2
    assert window.isWindowModified()


def test_delete_key_on_thumbnails(window, make_pdf, qtbot):
    window.open_file(make_pdf(3))
    select(window, [0])
    window.thumbnails.setFocus()
    window.activateWindow()
    qtbot.keyClick(window.thumbnails, Qt.Key.Key_Delete)
    assert window.document().page_count == 2


def test_cannot_delete_all_pages(window, make_pdf):
    window.open_file(make_pdf(2))
    window.select_all()
    assert not window.act_delete.isEnabled()


def test_move_pages_signal_reorders(window, make_pdf, qtbot):
    window.open_file(make_pdf(4))
    window.thumbnails.pagesMoved.emit([0], 4)
    assert page_labels(window.document()) == ["P2", "P3", "P4", "P1"]
    assert window.thumbnails.selected_rows() == [3]


def test_drop_row_geometry(window, make_pdf):
    window.open_file(make_pdf(3))
    view = window.thumbnails
    first = view.visualRect(window.model.index(0, 0))
    last = view.visualRect(window.model.index(2, 0))
    assert view.drop_row_at(QPoint(first.center().x(), first.top() + 2)) == 0
    assert view.drop_row_at(QPoint(first.center().x(), first.bottom() - 2)) == 1
    assert view.drop_row_at(QPoint(last.center().x(), last.bottom() + 50)) == 3


def test_insert_files_after_selection(window, make_pdf, make_png):
    window.open_file(make_pdf(2))
    select(window, [0])
    other = make_pdf(2, name="other.pdf", label="X")
    window.insert_files([other, make_png()], window.insert_position())
    labels = page_labels(window.document())
    assert labels[:3] == ["P1", "X1", "X2"]
    assert labels[4] == "P2"
    assert window.thumbnails.selected_rows() == [1, 2, 3]


def test_insert_blank_and_undo_redo(window, make_pdf):
    window.open_file(make_pdf(2))
    window.act_insert_blank.trigger()
    assert window.document().page_count == 3
    window.act_undo.trigger()
    assert window.document().page_count == 2
    assert not window.isWindowModified()
    window.act_redo.trigger()
    assert window.document().page_count == 3


def test_rotate_selected(window, make_pdf):
    window.open_file(make_pdf(2))
    select(window, [1])
    window.act_rotate_right.trigger()
    assert window.document().page_rotation(1) == 90


def test_save_clears_modified(window, make_pdf):
    path = make_pdf(3)
    window.open_file(path)
    select(window, [0])
    window.act_delete.trigger()
    window.act_save.trigger()
    assert not window.isWindowModified()
    assert not window.errors


def test_new_document_then_insert(window, make_pdf):
    window.new_document()
    assert window.document().page_count == 0
    assert not window.act_save.isEnabled()
    window.insert_files([make_pdf(1)], window.insert_position())
    assert window.document().page_count == 1
    assert window.act_save.isEnabled()


def test_zoom_actions(window, make_pdf):
    window.open_file(make_pdf(1))
    start = window.page_view.zoom()
    window.act_zoom_in.trigger()
    assert window.page_view.zoom() > start
    assert not window.page_view.is_fit_width()
    window.act_fit_width.trigger()
    assert window.page_view.is_fit_width()


# ---------------------------------------------------------------- export as image
@pytest.fixture
def export_dialogs(monkeypatch, tmp_path):
    """Answer the export dialogs without showing them; records what was asked."""
    QSettings().remove("export")  # the settings file is shared by the whole session
    calls = {"options": ExportOptions(".png", 72), "save": None, "folder": None, "asked": []}

    def get_options(parent, page_size, page_count, defaults):
        calls["asked"].append(("options", page_size, page_count, defaults))
        return calls["options"]

    def get_save(parent, caption, suggested, filters):
        calls["asked"].append(("save", Path(suggested).name, filters))
        return (str(calls["save"]) if calls["save"] else "", "")

    def get_folder(parent, caption, start):
        calls["asked"].append(("folder",))
        return str(calls["folder"]) if calls["folder"] else ""

    monkeypatch.setattr(ExportImageDialog, "get_options", get_options)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", get_save)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", get_folder)
    return calls


def test_export_action_placement_and_enabled_state(window, make_pdf):
    file_menu = window.menuBar().actions()[0].menu()
    actions = file_menu.actions()
    assert actions[actions.index(window.act_delete) + 1] is window.act_export_image
    assert not window.act_export_image.isEnabled()
    window.open_file(make_pdf(2))
    assert window.act_export_image.isEnabled()  # page 1 is selected after opening
    window.thumbnails.clearSelection()
    assert not window.act_export_image.isEnabled()


def test_export_single_page(window, make_pdf, export_dialogs, tmp_path):
    window.open_file(make_pdf(3))
    select(window, [1])
    export_dialogs["options"] = ExportOptions(".png", 150)
    export_dialogs["save"] = tmp_path / "second.png"

    window.act_export_image.trigger()

    pix = pymupdf.Pixmap(tmp_path / "second.png")
    assert (pix.width, pix.height) == (1275, 1650)
    assert export_dialogs["asked"][0] == ("options", (612.0, 792.0), 1, ExportOptions(".png", 300))
    assert export_dialogs["asked"][1][1] == "doc - Page 2.png"
    assert not window.isWindowModified()
    assert not window.document().can_undo
    assert "second.png" in window.statusBar().currentMessage()
    # The choice is remembered for next time.
    assert window._export_defaults() == ExportOptions(".png", 150)


def test_export_single_page_adds_missing_extension(window, make_pdf, export_dialogs, tmp_path):
    window.open_file(make_pdf(1))
    export_dialogs["options"] = ExportOptions(".jpg", 72)
    export_dialogs["save"] = tmp_path / "cover"
    window.export_selected_as_images()
    assert (tmp_path / "cover.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
    assert export_dialogs["asked"][1][2] == "JPEG image (*.jpg *.jpeg)"


def test_export_several_pages_to_folder(window, make_pdf, export_dialogs, tmp_path):
    window.open_file(make_pdf(4))
    select(window, [0, 2, 3])
    out = tmp_path / "out"
    out.mkdir()
    export_dialogs["folder"] = out

    window.export_selected_as_images()

    assert sorted(p.name for p in out.iterdir()) == [
        "doc - Page 1.png",
        "doc - Page 3.png",
        "doc - Page 4.png",
    ]
    assert "3 pages" in window.statusBar().currentMessage()


def test_export_asks_before_replacing_files(
    window, make_pdf, export_dialogs, tmp_path, monkeypatch
):
    window.open_file(make_pdf(2))
    window.select_all()
    export_dialogs["folder"] = tmp_path
    existing = tmp_path / "doc - Page 2.png"
    existing.write_bytes(b"old")

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.export_selected_as_images()
    assert existing.read_bytes() == b"old"
    assert not (tmp_path / "doc - Page 1.png").exists()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.export_selected_as_images()
    assert existing.read_bytes()[:4] == b"\x89PNG"
    assert (tmp_path / "doc - Page 1.png").exists()


def test_export_cancelled_in_options_dialog(window, make_pdf, export_dialogs):
    window.open_file(make_pdf(1))
    export_dialogs["options"] = None
    window.export_selected_as_images()
    assert [call[0] for call in export_dialogs["asked"]] == ["options"]


def test_export_error_is_reported(window, make_pdf, export_dialogs, tmp_path):
    window.open_file(make_pdf(1))
    export_dialogs["save"] = tmp_path / "missing" / "page.png"
    window.export_selected_as_images()
    assert window.errors and "page.png" in window.errors[0]


def test_export_dialog_shows_pixel_size(qtbot):
    dialog = ExportImageDialog((612, 792), 2, ExportOptions(".jpg", 999))
    qtbot.addWidget(dialog)
    assert dialog.options() == ExportOptions(".jpg", 300)  # unknown DPI falls back
    assert dialog.size_label.text() == "2550 × 3300 pixels"  # noqa: RUF001
    dialog.dpi_box.setCurrentIndex(dialog.dpi_box.findData(600))
    assert dialog.size_label.text() == "5100 × 6600 pixels"  # noqa: RUF001


def test_export_transparent_png(window, make_pdf, export_dialogs, tmp_path):
    window.open_file(make_pdf(1))
    export_dialogs["options"] = ExportOptions(".png", 72, transparent=True)
    export_dialogs["save"] = tmp_path / "clear.png"
    window.export_selected_as_images()
    pix = pymupdf.Pixmap(tmp_path / "clear.png")
    assert pix.alpha
    assert pix.pixel(0, 0)[3] == 0
    assert window._export_defaults() == ExportOptions(".png", 72, transparent=True)


def test_export_dialog_transparent_only_for_png(qtbot):
    dialog = ExportImageDialog((612, 792), 1, ExportOptions(".png", 300, transparent=True))
    qtbot.addWidget(dialog)
    assert dialog.transparent_box.isEnabled()
    assert dialog.options().transparent

    dialog.format_box.setCurrentIndex(dialog.format_box.findData(".jpg"))
    assert not dialog.transparent_box.isEnabled()
    assert dialog.options() == ExportOptions(".jpg", 300, transparent=False)

    dialog.format_box.setCurrentIndex(dialog.format_box.findData(".png"))
    assert dialog.options().transparent  # the tick survives a round trip through JPEG
