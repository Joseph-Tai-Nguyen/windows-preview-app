"""The editable PDF document model.

``PdfDocument`` wraps a PyMuPDF document and exposes the page operations the UI
needs (delete, move, insert, rotate) plus snapshot-based undo/redo and
dirty-state tracking. It is deliberately free of Qt so it can be unit tested
headlessly and reused from scripts.

Conventions:
* Page indices are 0-based everywhere in this module.
* Every mutating method records an undo snapshot first and returns the indices
  the UI should select afterwards.
* Files are read fully into memory, so the source file is never locked on
  Windows and "Save" can atomically replace it.
"""

from __future__ import annotations

import itertools
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"})
PDF_EXTENSIONS = frozenset({".pdf"})
INSERTABLE_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS

# US Letter in PDF points; used for blank pages in an empty document.
DEFAULT_PAGE_SIZE = (612.0, 792.0)
DEFAULT_UNDO_LIMIT = 30

_revision_counter = itertools.count(1)


class DocumentError(Exception):
    """A user-facing error raised by a document operation."""


class PasswordRequiredError(DocumentError):
    """The file is encrypted and needs a (different) password."""

    def __init__(self, path: Path, *, wrong_password: bool = False) -> None:
        self.path = Path(path)
        self.wrong_password = wrong_password
        reason = "The password is incorrect" if wrong_password else "A password is required"
        super().__init__(f"{reason} to open “{self.path.name}”.")


@dataclass(frozen=True)
class RenderedPage:
    """Raw RGB888 pixels of a rendered page (no Qt types, see ui.renderer)."""

    width: int
    height: int
    stride: int
    samples: bytes


@dataclass(frozen=True)
class _Snapshot:
    data: bytes | None  # None means "document with zero pages"
    revision: int


def _open_pdf_bytes(data: bytes, path: Path, password: str | None) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentError(f"“{path.name}” is not a readable PDF file.\n\n{exc}") from exc
    if doc.needs_pass:
        if password is None:
            doc.close()
            raise PasswordRequiredError(path)
        if not doc.authenticate(password):
            doc.close()
            raise PasswordRequiredError(path, wrong_password=True)
    return doc


def _read_bytes(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise DocumentError(f"Could not read “{Path(path).name}”.\n\n{exc}") from exc


def load_insertable(path: str | os.PathLike[str], password: str | None = None) -> pymupdf.Document:
    """Open a PDF or an image file as a PDF document suitable for ``insert_pdf``."""
    path = Path(path)
    suffix = path.suffix.lower()
    data = _read_bytes(path)
    if suffix in IMAGE_EXTENSIONS:
        try:
            with pymupdf.open(stream=data, filetype=suffix.lstrip(".")) as image_doc:
                pdf_bytes = image_doc.convert_to_pdf()
        except Exception as exc:
            raise DocumentError(f"“{path.name}” is not a readable image.\n\n{exc}") from exc
        return pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if suffix in PDF_EXTENSIONS:
        return _open_pdf_bytes(data, path, password)
    raise DocumentError(f"“{path.name}” is not a PDF or a supported image type.")


class PdfDocument:
    """An in-memory, editable PDF with undo/redo."""

    def __init__(
        self,
        doc: pymupdf.Document,
        path: Path | None = None,
        *,
        undo_limit: int = DEFAULT_UNDO_LIMIT,
    ) -> None:
        self._doc = doc
        self._path = Path(path) if path is not None else None
        self._undo_limit = undo_limit
        self._undo: list[_Snapshot] = []
        self._redo: list[_Snapshot] = []
        self._revision = next(_revision_counter)
        self._saved_revision = self._revision if path is not None else -1

    # ------------------------------------------------------------------ factories
    @classmethod
    def open(
        cls,
        path: str | os.PathLike[str],
        password: str | None = None,
        *,
        undo_limit: int = DEFAULT_UNDO_LIMIT,
    ) -> PdfDocument:
        path = Path(path)
        doc = _open_pdf_bytes(_read_bytes(path), path, password)
        if doc.page_count == 0:
            doc.close()
            raise DocumentError(f"“{path.name}” does not contain any pages.")
        return cls(doc, path, undo_limit=undo_limit)

    @classmethod
    def new(cls) -> PdfDocument:
        """An untitled document with no pages (pages must be inserted before saving)."""
        return cls(pymupdf.open(), None)

    # ------------------------------------------------------------------ properties
    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def display_name(self) -> str:
        return self._path.name if self._path else "Untitled"

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def is_modified(self) -> bool:
        return self._revision != self._saved_revision

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def page_size(self, index: int) -> tuple[float, float]:
        """Displayed (rotation-aware) page size in PDF points."""
        rect = self._doc[index].rect
        return rect.width, rect.height

    def page_text(self, index: int) -> str:
        return self._doc[index].get_text()

    def page_rotation(self, index: int) -> int:
        return self._doc[index].rotation

    # ------------------------------------------------------------------ rendering
    def render_page(self, index: int, scale: float) -> RenderedPage:
        pix = self._doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return RenderedPage(pix.width, pix.height, pix.stride, bytes(pix.samples))

    # ------------------------------------------------------------------ page operations
    def delete_pages(self, indices: Iterable[int]) -> list[int]:
        rows = self._normalize(indices)
        if not rows:
            return []
        if len(rows) >= self.page_count:
            raise DocumentError("A document must keep at least one page.")
        self._checkpoint()
        self._doc.delete_pages(rows)
        return [min(rows[0], self.page_count - 1)]

    def move_pages(self, indices: Iterable[int], destination: int) -> list[int]:
        """Move ``indices`` so they sit, in order, before the page that was at
        ``destination`` (``destination == page_count`` means "to the end")."""
        rows = self._normalize(indices)
        if not rows:
            return []
        destination = max(0, min(destination, self.page_count))
        moving = set(rows)
        order = [i for i in range(self.page_count) if i not in moving]
        insert_at = destination - sum(1 for r in rows if r < destination)
        order[insert_at:insert_at] = rows
        new_rows = list(range(insert_at, insert_at + len(rows)))
        if order == list(range(self.page_count)):
            return new_rows  # nothing actually moved; don't dirty the document
        self._checkpoint()
        self._doc.select(order)
        return new_rows

    def insert_blank_page(self, at: int, size: tuple[float, float] | None = None) -> list[int]:
        at = max(0, min(at, self.page_count))
        if size is None:
            size = self._neighbour_size(at)
        self._checkpoint()
        self._doc.new_page(pno=at, width=size[0], height=size[1])
        return [at]

    def insert_file(
        self, path: str | os.PathLike[str], at: int, password: str | None = None
    ) -> list[int]:
        """Insert every page of a PDF, or an image as a single page, before ``at``."""
        at = max(0, min(at, self.page_count))
        source = load_insertable(path, password)
        try:
            count = source.page_count
            if count == 0:
                raise DocumentError(f"“{Path(path).name}” does not contain any pages.")
            self._checkpoint()
            self._doc.insert_pdf(source, start_at=at)
        finally:
            source.close()
        return list(range(at, at + count))

    def rotate_pages(self, indices: Iterable[int], degrees: int) -> list[int]:
        if degrees % 90:
            raise ValueError("Rotation must be a multiple of 90 degrees.")
        rows = self._normalize(indices)
        if not rows:
            return []
        self._checkpoint()
        for row in rows:
            page = self._doc[row]
            page.set_rotation((page.rotation + degrees) % 360)
        return rows

    # ------------------------------------------------------------------ undo / redo
    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    # ------------------------------------------------------------------ saving
    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Write the document to ``path`` (default: its current path) atomically."""
        target = Path(path) if path is not None else self._path
        if target is None:
            raise DocumentError("This document has not been saved yet; choose a file name.")
        if self.page_count == 0:
            raise DocumentError("Add at least one page before saving.")
        target = target.resolve()
        fd, tmp_name = tempfile.mkstemp(suffix=".pdf.tmp", dir=target.parent)
        os.close(fd)
        try:
            self._doc.save(tmp_name, garbage=3, deflate=True)
            os.replace(tmp_name, target)
        except Exception as exc:
            Path(tmp_name).unlink(missing_ok=True)
            raise DocumentError(f"Could not save “{target.name}”.\n\n{exc}") from exc
        self._path = target
        self._saved_revision = self._revision

    def close(self) -> None:
        self._doc.close()

    # ------------------------------------------------------------------ internals
    def _normalize(self, indices: Iterable[int]) -> list[int]:
        rows = sorted(set(indices))
        for row in rows:
            if not 0 <= row < self.page_count:
                raise IndexError(f"Page index {row} out of range (0..{self.page_count - 1}).")
        return rows

    def _neighbour_size(self, at: int) -> tuple[float, float]:
        if self.page_count == 0:
            return DEFAULT_PAGE_SIZE
        neighbour = at - 1 if at > 0 else 0
        return self.page_size(neighbour)

    def _snapshot(self) -> _Snapshot:
        data = self._doc.tobytes() if self.page_count else None
        return _Snapshot(data, self._revision)

    def _checkpoint(self) -> None:
        self._undo.append(self._snapshot())
        if len(self._undo) > self._undo_limit:
            del self._undo[0]
        self._redo.clear()
        self._revision = next(_revision_counter)

    def _restore(self, snapshot: _Snapshot) -> None:
        old = self._doc
        if snapshot.data is None:
            self._doc = pymupdf.open()
        else:
            self._doc = pymupdf.open(stream=snapshot.data, filetype="pdf")
        self._revision = snapshot.revision
        old.close()


def is_insertable(path: str | os.PathLike[str]) -> bool:
    return Path(path).suffix.lower() in INSERTABLE_EXTENSIONS


def filter_insertable(paths: Sequence[str | os.PathLike[str]]) -> list[Path]:
    """Keep only insertable files, preserving the caller's order."""
    return [Path(p) for p in paths if is_insertable(p)]
