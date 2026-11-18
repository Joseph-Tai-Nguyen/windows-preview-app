from __future__ import annotations

import pymupdf
import pytest

from winpreview.core import office


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1200", (1200, None)),
        ("1,200", (1200, "#,##0")),
        ("1,350.50", (1350.5, "#,##0.00")),
        ("-80", (-80, None)),
        ("\N{MINUS SIGN}80", (-80, None)),
        ("+3", (3, None)),
        ("0.5", (0.5, "0.0")),
        (".25", (0.25, "0.00")),
        ("0", (0, None)),
        ("12.5%", (0.125, "0.0%")),
        ("7 %", (0.07, "0%")),
        ("-1,000.5", (-1000.5, "#,##0.0")),
    ],
)
def test_cell_value_converts_numbers(text, expected):
    value, number_format = office.cell_value(text)
    assert value == pytest.approx(expected[0])
    assert type(value) is type(expected[0])
    assert number_format == expected[1]


@pytest.mark.parametrize(
    "text",
    [
        "North",
        "",
        "007",  # a code, not a number
        "02134",
        "4111111111111111",  # too many digits for Excel to keep exactly
        "1.234,56",  # ambiguous decimal comma
        "12,34",
        "1,2345",
        "$100",
        "1 200",
        "n/a",
        "1-2",
    ],
)
def test_cell_value_keeps_text(text):
    assert office.cell_value(text) == (text, None)


def test_find_tables_ignores_prose():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 720), "Plain prose, no table. " * 80)
    assert office.find_tables(page) == []


def test_fill_sheet_formats_header_numbers_and_wrapped_text():
    from openpyxl import Workbook

    sheet = Workbook().active
    rows = [["Note", "2026"], ["first line\nsecond line", "1,000"], [None, "x" * 200]]
    office._fill_sheet(sheet, rows)

    assert sheet["B1"].value == "2026"  # the header row stays text
    assert sheet["A1"].font.bold and not sheet["A2"].font.bold
    assert sheet["B2"].value == 1000
    assert sheet["A2"].alignment.wrap_text
    assert sheet["A3"].value is None
    assert sheet.column_dimensions["A"].width == len("second line") + 2
    assert sheet.column_dimensions["B"].width == office.MAX_COLUMN_WIDTH
    assert sheet.freeze_panes == "A2"


def test_clean_strips_lines_and_illegal_characters():
    assert office._clean("  a \n\n b\x01 \n") == "a\nb"
    assert len(office._clean("x" * 40_000)) == office.MAX_CELL_TEXT
