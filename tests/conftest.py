"""Shared fixtures. PDFs are generated on the fly so no binaries live in git."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

import pymupdf
import pytest

# Run Qt headless unless a developer explicitly wants to watch the UI tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def _isolated_qsettings(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Keep QSettings out of the real registry during tests."""
    from PySide6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path_factory.mktemp("settings")),
    )


MakePdf = Callable[..., Path]


@pytest.fixture
def make_pdf(tmp_path: Path) -> MakePdf:
    """Create a PDF whose page N contains the text ``<label>N``.

    ``sizes`` optionally gives a (width, height) per page.
    """

    def _make(
        pages: int = 3,
        name: str = "doc.pdf",
        label: str = "P",
        sizes: Sequence[tuple[float, float]] | None = None,
        password: str | None = None,
    ) -> Path:
        doc = pymupdf.open()
        for i in range(pages):
            width, height = sizes[i] if sizes else (612, 792)
            page = doc.new_page(width=width, height=height)
            page.insert_text((72, 72), f"{label}{i + 1}", fontsize=24)
        path = tmp_path / name
        if password:
            doc.save(
                path,
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw=password,
                user_pw=password,
            )
        else:
            doc.save(path)
        doc.close()
        return path

    return _make


@pytest.fixture
def make_png(tmp_path: Path) -> Callable[..., Path]:
    def _make(name: str = "image.png", width: int = 200, height: int = 100) -> Path:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
        pix.set_rect(pix.irect, (200, 30, 30))
        path = tmp_path / name
        pix.save(path)
        return path

    return _make


def page_labels(doc) -> list[str]:
    """The text label of each page of a PdfDocument, e.g. ['P1', 'P3']."""
    return [doc.page_text(i).strip() for i in range(doc.page_count)]
