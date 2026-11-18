from __future__ import annotations

import pytest

from tests.conftest import page_labels
from winpreview.core import DocumentError, PasswordRequiredError, PdfDocument


# ---------------------------------------------------------------- opening
def test_open_reads_pages_and_is_clean(make_pdf):
    doc = PdfDocument.open(make_pdf(4))
    assert doc.page_count == 4
    assert page_labels(doc) == ["P1", "P2", "P3", "P4"]
    assert not doc.is_modified
    assert not doc.can_undo


def test_open_rejects_non_pdf(tmp_path):
    bogus = tmp_path / "notes.pdf"
    bogus.write_text("hello")
    with pytest.raises(DocumentError):
        PdfDocument.open(bogus)


def test_open_missing_file(tmp_path):
    with pytest.raises(DocumentError):
        PdfDocument.open(tmp_path / "missing.pdf")


def test_open_encrypted_requires_password(make_pdf):
    path = make_pdf(2, password="secret")
    with pytest.raises(PasswordRequiredError) as missing:
        PdfDocument.open(path)
    assert not missing.value.wrong_password
    with pytest.raises(PasswordRequiredError) as wrong:
        PdfDocument.open(path, "nope")
    assert wrong.value.wrong_password
    assert PdfDocument.open(path, "secret").page_count == 2


def test_open_does_not_lock_file(make_pdf):
    path = make_pdf(1)
    doc = PdfDocument.open(path)
    path.unlink()  # would fail on Windows if the file were held open
    assert doc.page_count == 1


# ---------------------------------------------------------------- delete
def test_delete_pages(make_pdf):
    doc = PdfDocument.open(make_pdf(5))
    selection = doc.delete_pages([1, 3])
    assert page_labels(doc) == ["P1", "P3", "P5"]
    assert selection == [1]
    assert doc.is_modified


def test_delete_last_page_selects_new_last(make_pdf):
    doc = PdfDocument.open(make_pdf(3))
    assert doc.delete_pages([2]) == [1]


def test_cannot_delete_every_page(make_pdf):
    doc = PdfDocument.open(make_pdf(2))
    with pytest.raises(DocumentError):
        doc.delete_pages([0, 1])
    assert doc.page_count == 2
    assert not doc.is_modified


def test_delete_out_of_range(make_pdf):
    doc = PdfDocument.open(make_pdf(2))
    with pytest.raises(IndexError):
        doc.delete_pages([5])


# ---------------------------------------------------------------- move
@pytest.mark.parametrize(
    ("rows", "destination", "expected", "selection"),
    [
        ([0], 5, ["P2", "P3", "P4", "P5", "P1"], [4]),
        ([4], 0, ["P5", "P1", "P2", "P3", "P4"], [0]),
        ([1, 3], 0, ["P2", "P4", "P1", "P3", "P5"], [0, 1]),
        ([0, 2], 4, ["P2", "P4", "P1", "P3", "P5"], [2, 3]),
        ([3], 2, ["P1", "P2", "P4", "P3", "P5"], [2]),
    ],
)
def test_move_pages(make_pdf, rows, destination, expected, selection):
    doc = PdfDocument.open(make_pdf(5))
    assert doc.move_pages(rows, destination) == selection
    assert page_labels(doc) == expected


@pytest.mark.parametrize("destination", [1, 2])
def test_move_onto_itself_is_noop(make_pdf, destination):
    doc = PdfDocument.open(make_pdf(3))
    assert doc.move_pages([1], destination) == [1]
    assert not doc.is_modified
    assert not doc.can_undo


# ---------------------------------------------------------------- insert
def test_insert_blank_page_uses_neighbour_size(make_pdf):
    doc = PdfDocument.open(make_pdf(2, sizes=[(300, 400), (500, 500)]))
    assert doc.insert_blank_page(1) == [1]
    assert doc.page_count == 3
    assert doc.page_size(1) == (300, 400)
    assert doc.page_text(1).strip() == ""


def test_insert_pdf_at_position(make_pdf):
    doc = PdfDocument.open(make_pdf(3))
    other = make_pdf(2, name="other.pdf", label="X")
    assert doc.insert_file(other, 1) == [1, 2]
    assert page_labels(doc) == ["P1", "X1", "X2", "P2", "P3"]


def test_insert_pdf_at_end(make_pdf):
    doc = PdfDocument.open(make_pdf(1))
    doc.insert_file(make_pdf(1, name="b.pdf", label="B"), doc.page_count)
    assert page_labels(doc) == ["P1", "B1"]


def test_insert_encrypted_pdf(make_pdf):
    doc = PdfDocument.open(make_pdf(1))
    locked = make_pdf(1, name="locked.pdf", label="L", password="pw")
    with pytest.raises(PasswordRequiredError):
        doc.insert_file(locked, 1)
    assert not doc.is_modified
    doc.insert_file(locked, 1, password="pw")
    assert page_labels(doc) == ["P1", "L1"]


def test_insert_image_as_page(make_pdf, make_png):
    doc = PdfDocument.open(make_pdf(1))
    assert doc.insert_file(make_png(width=200, height=100), 0) == [0]
    assert doc.page_count == 2
    width, height = doc.page_size(0)
    assert width > height


def test_insert_unsupported_type(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    text_file = tmp_path / "a.txt"
    text_file.write_text("x")
    with pytest.raises(DocumentError):
        doc.insert_file(text_file, 0)


# ---------------------------------------------------------------- rotate
def test_rotate_pages(make_pdf):
    doc = PdfDocument.open(make_pdf(2))
    doc.rotate_pages([0], 90)
    assert doc.page_rotation(0) == 90
    assert doc.page_size(0) == (792, 612)
    doc.rotate_pages([0], -180)
    assert doc.page_rotation(0) == 270
    assert doc.page_rotation(1) == 0


def test_rotate_requires_right_angles(make_pdf):
    doc = PdfDocument.open(make_pdf(1))
    with pytest.raises(ValueError):
        doc.rotate_pages([0], 45)


# ---------------------------------------------------------------- undo / redo
def test_undo_redo_round_trip(make_pdf):
    doc = PdfDocument.open(make_pdf(3))
    doc.delete_pages([0])
    doc.move_pages([1], 0)
    assert page_labels(doc) == ["P3", "P2"]

    doc.undo()
    assert page_labels(doc) == ["P2", "P3"]
    doc.undo()
    assert page_labels(doc) == ["P1", "P2", "P3"]
    assert not doc.is_modified  # back at the saved state
    assert doc.can_redo

    doc.redo()
    assert page_labels(doc) == ["P2", "P3"]
    assert doc.is_modified


def test_new_operation_clears_redo(make_pdf):
    doc = PdfDocument.open(make_pdf(3))
    doc.delete_pages([0])
    doc.undo()
    doc.rotate_pages([0], 90)
    assert not doc.can_redo


def test_undo_limit(make_pdf):
    doc = PdfDocument.open(make_pdf(1), undo_limit=2)
    for _ in range(4):
        doc.insert_blank_page(0)
    doc.undo()
    doc.undo()
    assert not doc.can_undo
    assert doc.page_count == 3


# ---------------------------------------------------------------- saving
def test_save_in_place(make_pdf):
    path = make_pdf(3)
    doc = PdfDocument.open(path)
    doc.delete_pages([1])
    doc.save()
    assert not doc.is_modified
    assert page_labels(PdfDocument.open(path)) == ["P1", "P3"]


def test_save_as_and_undo_marks_modified(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(2))
    doc.delete_pages([0])
    target = tmp_path / "out.pdf"
    doc.save(target)
    assert doc.path == target.resolve()
    doc.undo()
    assert doc.is_modified  # the saved file has one page, the document two


def test_new_document_workflow(make_pdf, tmp_path):
    doc = PdfDocument.new()
    assert doc.page_count == 0
    assert doc.display_name == "Untitled"
    with pytest.raises(DocumentError):
        doc.save()
    with pytest.raises(DocumentError):
        doc.save(tmp_path / "empty.pdf")

    doc.insert_file(make_pdf(2), 0)
    doc.undo()
    assert doc.page_count == 0
    doc.redo()
    doc.save(tmp_path / "new.pdf")
    assert PdfDocument.open(tmp_path / "new.pdf").page_count == 2


def test_render_page(make_pdf):
    doc = PdfDocument.open(make_pdf(1))
    page = doc.render_page(0, 0.5)
    assert (page.width, page.height) == (306, 396)
    assert len(page.samples) == page.stride * page.height
