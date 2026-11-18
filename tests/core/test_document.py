from __future__ import annotations

import logging
import os

import pymupdf
import pytest

from tests.conftest import docx_text, page_labels
from winpreview.core import DocumentError, PasswordRequiredError, PdfDocument, office


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


# ---------------------------------------------------------------- export page image
def test_export_page_image_png_at_300_dpi(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(2))
    target = doc.export_page_image(1, tmp_path / "page2.png")

    assert target == (tmp_path / "page2.png").resolve()
    pix = pymupdf.Pixmap(target)
    assert (pix.width, pix.height) == (2550, 3300)  # US Letter at 300 DPI
    assert (pix.xres, pix.yres) == (300, 300)
    assert not pix.alpha
    assert not doc.is_modified
    assert not doc.can_undo


def test_export_page_image_renders_the_right_page(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(2, sizes=[(612, 792), (300, 200)]))
    pix = pymupdf.Pixmap(doc.export_page_image(1, tmp_path / "p.png", dpi=144))
    assert (pix.width, pix.height) == (600, 400)


def test_export_page_image_jpeg(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    target = doc.export_page_image(0, tmp_path / "page.JPG", dpi=150, jpeg_quality=80)
    assert target.read_bytes()[:3] == b"\xff\xd8\xff"
    pix = pymupdf.Pixmap(target)
    assert (pix.width, pix.height) == (1275, 1650)


def test_export_page_image_respects_rotation(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    doc.rotate_pages([0], 90)
    pix = pymupdf.Pixmap(doc.export_page_image(0, tmp_path / "rot.png", dpi=72))
    assert (pix.width, pix.height) == (792, 612)


def test_export_page_image_overwrites_and_leaves_no_temp_files(make_pdf, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "page.png"
    target.write_bytes(b"old")
    doc = PdfDocument.open(make_pdf(1))
    doc.export_page_image(0, target, dpi=72)
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert [p.name for p in out_dir.iterdir()] == ["page.png"]


@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("page.gif", {}),
        ("page", {}),
        ("page.png", {"dpi": 35}),
        ("page.png", {"dpi": 1201}),
        ("page.jpg", {"jpeg_quality": 0}),
        ("page.jpg", {"jpeg_quality": 101}),
    ],
)
def test_export_page_image_rejects_bad_options(make_pdf, tmp_path, name, kwargs):
    doc = PdfDocument.open(make_pdf(1))
    with pytest.raises(DocumentError):
        doc.export_page_image(0, tmp_path / name, **kwargs)
    assert list(tmp_path.glob("page*")) == []


def test_export_page_image_rejects_huge_render(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1, sizes=[(14400, 14400)]))  # 200 x 200 inches
    with pytest.raises(DocumentError, match="lower resolution"):
        doc.export_page_image(0, tmp_path / "huge.png", dpi=300)


def test_export_page_image_rejects_bad_index(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(2))
    with pytest.raises(IndexError):
        doc.export_page_image(2, tmp_path / "page.png")


def test_export_page_image_missing_folder(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    with pytest.raises(DocumentError):
        doc.export_page_image(0, tmp_path / "missing" / "page.png")


def test_export_page_image_transparent_png(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    target = doc.export_page_image(0, tmp_path / "t.png", dpi=72, transparent=True)
    pix = pymupdf.Pixmap(target)
    assert pix.alpha
    assert pix.pixel(pix.width - 1, pix.height - 1)[3] == 0  # empty area is see-through
    assert max(pix.samples[pix.n - 1 :: pix.n]) == 255  # the text is opaque


def test_export_page_image_transparent_keeps_painted_background(tmp_path):
    source = pymupdf.open()
    page = source.new_page()
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    source.save(tmp_path / "white.pdf")
    doc = PdfDocument.open(tmp_path / "white.pdf")
    pix = pymupdf.Pixmap(doc.export_page_image(0, tmp_path / "w.png", dpi=72, transparent=True))
    assert pix.pixel(0, 0)[3] == 255


def test_export_page_image_transparent_requires_png(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(1))
    with pytest.raises(DocumentError, match="PNG"):
        doc.export_page_image(0, tmp_path / "page.jpg", transparent=True)
    assert not (tmp_path / "page.jpg").exists()


# ---------------------------------------------------------------- export to Word / Excel
SALES = [["Region", "Q1", "Share"], ["North", "1,200", "12.5%"], ["South", "-80", "7%"]]
PARTS = [["Part", "Qty"], ["Bolt", "1,500"], ["Nut", "20"]]


def landscape_sideways_pdf(path):
    """A landscape page stored the way some generators do it: a portrait page whose
    content is drawn sideways, with /Rotate 90 to show it upright."""
    source = pymupdf.open()
    landscape = source.new_page(width=792, height=612)
    for r, row in enumerate(PARTS):
        for c, text in enumerate(row):
            cell = pymupdf.Rect(72 + c * 120, 72 + r * 22, 192 + c * 120, 94 + r * 22)
            landscape.draw_rect(cell, width=0.8)
            landscape.insert_text((cell.x0 + 4, cell.y1 - 6), text, fontsize=10)
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.show_pdf_page(page.rect, source, 0, rotate=90)
    page.set_rotation(90)
    doc.save(path)
    return path


def test_export_word_converts_selected_pages_in_order(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(4))
    result = doc.export_word([3, 1], tmp_path / "out.docx")

    assert result.path == (tmp_path / "out.docx").resolve()
    assert result.pages == [1, 3]
    assert result.failed == []
    text = docx_text(result.path)
    assert "P2" in text and "P4" in text
    assert "P1" not in text and "P3" not in text
    assert text.index("P2") < text.index("P4")
    assert not doc.is_modified
    assert not doc.can_undo


def test_export_word_keeps_tables(make_table_pdf, tmp_path):
    import docx

    doc = PdfDocument.open(make_table_pdf([[SALES]]))
    target = doc.export_word([0], tmp_path / "table.docx").path
    tables = docx.Document(str(target)).tables
    assert len(tables) == 1
    assert [[cell.text for cell in row.cells] for row in tables[0].rows] == SALES


def test_export_word_from_encrypted_document(make_pdf, tmp_path):
    doc = PdfDocument.open(make_pdf(2, password="secret"), "secret")
    target = doc.export_word([0, 1], tmp_path / "out.docx").path
    assert "P1" in docx_text(target)


def test_export_word_reads_rotated_landscape_page(tmp_path):
    doc = PdfDocument.open(landscape_sideways_pdf(tmp_path / "landscape.pdf"))
    text = docx_text(doc.export_word([0], tmp_path / "out.docx").path)
    assert "Bolt" in text and "1,500" in text


def test_export_word_reports_progress_and_replaces_file(make_pdf, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "out.docx"
    target.write_bytes(b"old")
    calls = []
    doc = PdfDocument.open(make_pdf(2))
    doc.export_word([0, 1], target, progress=lambda done, total: calls.append((done, total)))

    assert calls[0] == (0, 3)
    assert calls[-1] == (3, 3)
    assert target.read_bytes()[:2] == b"PK"  # a .docx is a zip file
    assert [p.name for p in out_dir.iterdir()] == ["out.docx"]


def test_export_word_cancel_writes_nothing(make_pdf, tmp_path):
    target = tmp_path / "out.docx"
    target.write_bytes(b"old")
    doc = PdfDocument.open(make_pdf(2))
    with pytest.raises(office.ExportCancelled):
        doc.export_word([0, 1], target, progress=lambda done, total: done < 1)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob("*.docx")) == [target]


def test_export_word_leaves_out_pages_that_fail(make_pdf, tmp_path, monkeypatch):
    from pdf2docx.page.Page import Page

    original = Page.parse

    def parse(self, **kwargs):
        if self.id == 1:
            raise RuntimeError("broken page")
        return original(self, **kwargs)

    monkeypatch.setattr(Page, "parse", parse)
    doc = PdfDocument.open(make_pdf(3))
    result = doc.export_word([0, 1, 2], tmp_path / "out.docx")
    assert result.pages == [0, 2]
    assert result.failed == [1]
    assert "P2" not in docx_text(result.path)


def test_export_word_fails_if_no_page_converts(make_pdf, tmp_path, monkeypatch):
    from pdf2docx.page.Page import Page

    def parse(self, **kwargs):
        raise RuntimeError("broken page")

    monkeypatch.setattr(Page, "parse", parse)
    doc = PdfDocument.open(make_pdf(1))
    with pytest.raises(DocumentError, match="None of the selected pages"):
        doc.export_word([0], tmp_path / "out.docx")
    assert list(tmp_path.glob("*.docx")) == []


def test_export_word_does_not_leak_logging(make_pdf, tmp_path):
    root = logging.getLogger()
    before = (root.handlers[:], root.level)
    PdfDocument.open(make_pdf(1)).export_word([0], tmp_path / "out.docx")
    assert (root.handlers, root.level) == before


def test_export_excel_writes_one_sheet_per_table(make_table_pdf, tmp_path):
    import openpyxl

    path = make_table_pdf([[SALES], "Just a paragraph of prose. " * 20, [SALES, PARTS]])
    doc = PdfDocument.open(path)
    result = doc.export_excel([0, 1, 2], tmp_path / "out.xlsx")

    assert (result.pages, result.tables, result.failed) == ([0, 2], 3, [])
    book = openpyxl.load_workbook(result.path)
    assert book.sheetnames == ["Page 1", "Page 3 (1)", "Page 3 (2)"]
    sheet = book["Page 1"]
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    assert values == [["Region", "Q1", "Share"], ["North", 1200, 0.125], ["South", -80, 0.07]]
    assert sheet["B2"].number_format == "#,##0"
    assert sheet["C2"].number_format == "0.0%"
    assert sheet["A1"].font.bold
    assert sheet.freeze_panes == "A2"
    assert [[c.value for c in row] for row in book["Page 3 (2)"].iter_rows()][1] == ["Bolt", 1500]
    assert not doc.is_modified


def test_export_excel_names_sheets_by_document_page(make_table_pdf, tmp_path):
    import openpyxl

    doc = PdfDocument.open(make_table_pdf([[SALES], [PARTS]]))
    result = doc.export_excel([1], tmp_path / "out.xlsx")
    assert result.pages == [1]
    assert openpyxl.load_workbook(result.path).sheetnames == ["Page 2"]


def test_export_excel_finds_borderless_tables(make_table_pdf, tmp_path):
    import openpyxl

    # Without grid lines a table is recognised by its aligned columns, which needs a
    # few rows: PyMuPDF does not treat three rows of two words as a table.
    table = [*PARTS, ["Washer", "7"]]
    doc = PdfDocument.open(make_table_pdf([[table]], ruled=False))
    book = openpyxl.load_workbook(doc.export_excel([0], tmp_path / "out.xlsx").path)
    values = [[cell.value for cell in row] for row in book.active.iter_rows()]
    assert values == [["Part", "Qty"], ["Bolt", 1500], ["Nut", 20], ["Washer", 7]]


def test_export_excel_reads_rotated_landscape_page(tmp_path):
    import openpyxl

    doc = PdfDocument.open(landscape_sideways_pdf(tmp_path / "landscape.pdf"))
    book = openpyxl.load_workbook(doc.export_excel([0], tmp_path / "out.xlsx").path)
    assert [cell.value for cell in next(book.active.iter_rows())] == ["Part", "Qty"]


def test_export_excel_without_tables_writes_nothing(make_pdf, tmp_path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    doc = PdfDocument.open(make_pdf(2))
    with pytest.raises(DocumentError, match="No tables were found"):
        doc.export_excel([0, 1], target)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob("*.xlsx")) == [target]


def test_export_excel_cancel_writes_nothing(make_table_pdf, tmp_path):
    doc = PdfDocument.open(make_table_pdf([[SALES], [PARTS]]))
    with pytest.raises(office.ExportCancelled):
        doc.export_excel([0, 1], tmp_path / "out.xlsx", progress=lambda done, total: False)
    assert list(tmp_path.glob("*.xlsx")) == []


@pytest.mark.parametrize("method", ["export_word", "export_excel"])
@pytest.mark.parametrize(
    ("name", "rows"), [("out.pdf", [0]), ("out", [0]), ("out.doc", [0]), (None, [])]
)
def test_export_office_rejects_bad_input(make_pdf, tmp_path, method, name, rows):
    doc = PdfDocument.open(make_pdf(1))
    suffix = ".docx" if method == "export_word" else ".xlsx"
    with pytest.raises(DocumentError):
        getattr(doc, method)(rows, tmp_path / (name or f"out{suffix}"))
    assert list(tmp_path.glob("out*")) == []


@pytest.mark.parametrize("method", ["export_word", "export_excel"])
def test_export_office_rejects_bad_index(make_pdf, tmp_path, method):
    doc = PdfDocument.open(make_pdf(1))
    suffix = ".docx" if method == "export_word" else ".xlsx"
    with pytest.raises(IndexError):
        getattr(doc, method)([1], tmp_path / f"out{suffix}")


def test_export_office_missing_folder(make_table_pdf, tmp_path):
    doc = PdfDocument.open(make_table_pdf([[SALES]]))
    with pytest.raises(DocumentError, match=r"out.docx"):
        doc.export_word([0], tmp_path / "missing" / "out.docx")
    with pytest.raises(DocumentError, match=r"out.xlsx"):
        doc.export_excel([0], tmp_path / "missing" / "out.xlsx")


def test_export_office_explains_a_locked_file(make_table_pdf, tmp_path, monkeypatch):
    def replace(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(os, "replace", replace)
    doc = PdfDocument.open(make_table_pdf([[SALES]]))
    with pytest.raises(DocumentError, match="close it and try again"):
        doc.export_excel([0], tmp_path / "out.xlsx")
    assert list(tmp_path.glob("*.xlsx")) == []
