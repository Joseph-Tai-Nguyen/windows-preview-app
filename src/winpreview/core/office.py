"""Converting pages to Microsoft Office files: Word (.docx) and Excel (.xlsx).

Word export uses pdf2docx, which rebuilds paragraphs, tables and images from the
page layout. Excel export finds tables with PyMuPDF and writes each one to its own
sheet with openpyxl. Both libraries are imported only when an export runs, because
pdf2docx pulls in OpenCV and would slow down every app start.

Callers go through ``PdfDocument.export_word`` / ``export_excel``, which validate
input, write atomically and turn failures into ``DocumentError``.
"""

from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import pymupdf

# Called with (steps done, total steps). Returning False cancels the export.
ProgressCallback = Callable[[int, int], bool]

# Excel refuses longer cell text, and cannot store more digits exactly.
MAX_CELL_TEXT = 32_767
MAX_EXACT_DIGITS = 15
MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH = 8, 60

# 1234 · 1,234 · 1,234.50 · -0.5 · .5 (optionally followed by % in the caller)
_NUMBER = re.compile(r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)")
# Control characters that are not allowed in the XML of an .xlsx file.
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ExportCancelled(Exception):
    """The user cancelled the export through the progress callback."""


class NothingToExport(Exception):
    """No page produced any content for the chosen format."""


@dataclass(frozen=True)
class ConversionResult:
    converted: list[int]  # 0-based indices into the converted PDF
    failed: list[int]  # pages the converter could not handle; they were left out
    tables: int = 0  # Excel only


# ---------------------------------------------------------------------- Word
def write_docx(
    pdf_bytes: bytes, target: str, progress: ProgressCallback | None = None
) -> ConversionResult:
    """Convert every page of the PDF in ``pdf_bytes`` into the Word file ``target``.

    A page that the converter fails on is left out and reported in ``failed``.
    Raises ``NothingToExport`` if no page could be converted.
    """
    with _quiet_root_logger():
        converter_class = _import_pdf2docx()
        converter = converter_class(stream=pdf_bytes)
        try:
            settings = converter.default_settings
            settings.update(multi_processing=False, ignore_page_error=True)
            converter.load_pages()
            converter.parse_document(**settings)
            pages = list(converter.pages)
            total = len(pages) + 1  # one step per page, one for writing the file
            converted: list[int] = []
            failed: list[int] = []
            for index, page in enumerate(pages):
                _report(progress, index, total)
                try:
                    page.parse(**settings)
                except Exception:
                    failed.append(index)
                else:
                    converted.append(index)
            if not converted:
                raise NothingToExport
            _report(progress, total - 1, total)
            converter.make_docx(target, **settings)
            _report(progress, total, total)
        finally:
            converter.close()
    return ConversionResult(converted, failed)


def _import_pdf2docx():
    with warnings.catch_warnings():
        # pdf2docx still imports PyMuPDF under its legacy ``fitz`` name.
        warnings.simplefilter("ignore", FutureWarning)
        from pdf2docx import Converter
    return Converter


@contextmanager
def _quiet_root_logger() -> Iterator[None]:
    """pdf2docx calls ``logging.basicConfig`` on import and logs every step to the root
    logger. A temporary NullHandler swallows that without touching the app's logging."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    root.handlers = [logging.NullHandler()]
    try:
        yield
    finally:
        root.handlers = handlers
        root.setLevel(level)


# ---------------------------------------------------------------------- Excel
def write_xlsx(
    pdf: pymupdf.Document,
    page_numbers: Sequence[int],
    target: str,
    progress: ProgressCallback | None = None,
) -> ConversionResult:
    """Write each table found in ``pdf`` to its own sheet of the workbook ``target``.

    ``page_numbers`` gives the 1-based number shown to the user for each page, used
    in the sheet names (“Page 3”, or “Page 3 (2)” for the second table on a page).
    Table detection reads unrotated page space, so pass pages with their rotation
    already removed. Raises ``NothingToExport`` if no table is found.
    """
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    total = pdf.page_count + 1
    converted: list[int] = []
    failed: list[int] = []
    tables = 0
    for index, page in enumerate(pdf):
        _report(progress, index, total)
        try:
            found = find_tables(page)
        except Exception:
            failed.append(index)
            continue
        if found:
            converted.append(index)
        for number, rows in enumerate(found, start=1):
            title = f"Page {page_numbers[index]}"
            if len(found) > 1:
                title += f" ({number})"
            _fill_sheet(workbook.create_sheet(title), rows)
            tables += 1
    if not tables:
        raise NothingToExport
    _report(progress, total - 1, total)
    workbook.save(target)
    _report(progress, total, total)
    return ConversionResult(converted, failed, tables)


def find_tables(page: pymupdf.Page) -> list[list[list[str | None]]]:
    """The tables on ``page`` as rows of cell text (None for a covered, merged cell).

    Ruled tables are found first. Only when a page has none are columns of aligned
    text tried, which catches borderless tables but ignores ordinary paragraphs.
    """
    found = []
    for strategy in ("lines", "text"):
        found = page.find_tables(strategy=strategy).tables
        if found:
            break
    tables = []
    for table in found:
        # Cell text is read from the cell rectangles: Table.extract() can split
        # punctuation such as “1,200” into separate lines.
        rows: list[list[str | None]] = []
        header = table.header
        if header.external:
            rows.append(
                [
                    _clean(page.get_textbox(cell) if cell else name)
                    for cell, name in zip(header.cells, header.names, strict=False)
                ]
            )
        for row in table.rows:
            rows.append(
                [None if cell is None else _clean(page.get_textbox(cell)) for cell in row.cells]
            )
        if any(cell for row in rows for cell in row):
            tables.append(rows)
    return tables


def cell_value(text: str) -> tuple[str | int | float, str | None]:
    """The Excel value for cell ``text`` and its number format (None = General).

    Numbers become numbers so they can be summed: “1,234.50”, “-80”, “12.5%”.
    Anything that would lose information stays text: codes with leading zeros
    (“007”), numbers too long for Excel (“4111111111111111”), and ambiguous
    formats such as “1.234,56”.
    """
    stripped = text.strip().replace("\N{MINUS SIGN}", "-")
    percent = stripped.endswith("%")
    number = stripped[:-1].rstrip() if percent else stripped
    if not _NUMBER.fullmatch(number):
        return text, None
    digits = number.lstrip("+-").replace(",", "")
    whole, _, fraction = digits.partition(".")
    if len(whole) > 1 and whole.startswith("0"):
        return text, None
    if len(whole) + len(fraction) > MAX_EXACT_DIGITS:
        return text, None

    decimals = "." + "0" * len(fraction) if fraction else ""
    value: int | float = float(number.replace(",", "")) if fraction else int(digits)
    if number.startswith("-"):
        value = -abs(value)
    if percent:
        return value / 100, f"0{decimals}%"
    if "," in number:
        return value, f"#,##0{decimals}"
    return value, f"0{decimals}" if fraction else None


def _fill_sheet(sheet, rows: list[list[str | None]]) -> None:
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    widths: dict[int, int] = {}
    for r, row in enumerate(rows, start=1):
        for c, text in enumerate(row, start=1):
            if not text:
                continue
            value, number_format = cell_value(text) if r > 1 else (text, None)
            cell = sheet.cell(row=r, column=c, value=value)
            if number_format:
                cell.number_format = number_format
            if r == 1:
                cell.font = Font(bold=True)
            if "\n" in text:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            longest = max(len(line) for line in text.splitlines())
            widths[c] = max(widths.get(c, 0), longest)
    for column, width in widths.items():
        letter = get_column_letter(column)
        sheet.column_dimensions[letter].width = min(
            max(width + 2, MIN_COLUMN_WIDTH), MAX_COLUMN_WIDTH
        )
    if len(rows) > 1:
        sheet.freeze_panes = "A2"


def _clean(text: str) -> str:
    lines = (line.strip() for line in text.splitlines())
    text = "\n".join(line for line in lines if line)
    return _ILLEGAL_XML.sub("", text)[:MAX_CELL_TEXT]


def _report(progress: ProgressCallback | None, done: int, total: int) -> None:
    if progress is not None and progress(done, total) is False:
        raise ExportCancelled
