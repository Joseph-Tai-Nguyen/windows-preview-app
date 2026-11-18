"""Qt list model exposing the pages of a ``PdfDocument``.

One model instance is shared by the thumbnail sidebar and the main page view.
Any change to the document is followed by ``refresh()`` (a full model reset);
page operations re-read everything anyway, and a reset keeps both views and
their pixmap caches trivially consistent.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QPersistentModelIndex, Qt

from winpreview.core import PdfDocument

PAGE_SIZE_ROLE = Qt.ItemDataRole.UserRole + 1
PAGE_MIME_TYPE = "application/x-winpreview-pages"

_Index = QModelIndex | QPersistentModelIndex


class PageListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc: PdfDocument | None = None

    # ------------------------------------------------------------------ document
    def document(self) -> PdfDocument | None:
        return self._doc

    def set_document(self, doc: PdfDocument | None) -> None:
        self.beginResetModel()
        self._doc = doc
        self.endResetModel()

    def refresh(self) -> None:
        """Call after any change to the document's pages."""
        self.beginResetModel()
        self.endResetModel()

    # ------------------------------------------------------------------ Qt model API
    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid() or self._doc is None:
            return 0
        return self._doc.page_count

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._doc is None:
            return None
        row = index.row()
        if role == Qt.ItemDataRole.DisplayRole:
            return str(row + 1)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Page {row + 1}"
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"Page {row + 1} of {self._doc.page_count}"
        if role == PAGE_SIZE_ROLE:
            return self._doc.page_size(row)
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        )

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:
        return [PAGE_MIME_TYPE]

    def mimeData(self, indexes) -> QMimeData:
        rows = sorted({i.row() for i in indexes if i.isValid()})
        mime = QMimeData()
        mime.setData(PAGE_MIME_TYPE, ",".join(map(str, rows)).encode("ascii"))
        return mime
