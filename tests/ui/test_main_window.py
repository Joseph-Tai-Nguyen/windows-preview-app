from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from tests.conftest import page_labels
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
