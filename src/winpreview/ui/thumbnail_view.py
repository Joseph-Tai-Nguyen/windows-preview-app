"""The sidebar of page thumbnails (selection, drag-to-reorder, file drops).

Drag and drop is handled entirely here instead of through the model's
``dropMimeData``: Qt's built-in internal-move machinery removes the source
rows itself, which fights with our "rebuild the document, then reset the
model" approach. Instead the view works out the destination row, draws its own
insertion line and emits ``pagesMoved`` / ``filesDropped`` for the main window
to act on.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from winpreview.core.document import filter_insertable
from winpreview.ui.page_model import PAGE_MIME_TYPE, PAGE_SIZE_ROLE
from winpreview.ui.renderer import PixmapCache

THUMB_WIDTH = 110
THUMB_MAX_HEIGHT = int(THUMB_WIDTH * 1.42)
PADDING = 10
LABEL_HEIGHT = 22
AUTOSCROLL_MARGIN = 28
AUTOSCROLL_STEP = 18


def thumbnail_scale(page_width: float, page_height: float) -> float:
    return min(THUMB_WIDTH / page_width, THUMB_MAX_HEIGHT / page_height)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cache = PixmapCache(capacity=400)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width, height = index.data(PAGE_SIZE_ROLE) or (612.0, 792.0)
        scale = thumbnail_scale(width, height)
        return QSize(THUMB_WIDTH + 2 * PADDING, round(height * scale) + 2 * PADDING + LABEL_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        doc = index.model().document()
        if doc is None:
            return
        width, height = index.data(PAGE_SIZE_ROLE)
        scale = thumbnail_scale(width, height)
        tw, th = round(width * scale), round(height * scale)
        rect = option.rect
        target = QRect(rect.x() + (rect.width() - tw) // 2, rect.y() + PADDING, tw, th)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        dpr = option.widget.devicePixelRatioF() if option.widget else 1.0

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        highlight = palette.highlight().color()
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(highlight)
            painter.drawRoundedRect(target.adjusted(-5, -5, 5, 5), 5, 5)

        painter.drawPixmap(target, self.cache.get(doc, index.row(), scale, dpr))
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target.adjusted(0, 0, -1, -1))

        label = index.data(Qt.ItemDataRole.DisplayRole)
        label_rect = QRect(rect.x(), target.bottom() + 6, rect.width(), LABEL_HEIGHT - 4)
        if selected:
            metrics = painter.fontMetrics()
            pill_w = metrics.horizontalAdvance(label) + 14
            pill = QRect(
                label_rect.center().x() - pill_w // 2, label_rect.y(), pill_w, label_rect.height()
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(highlight)
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.setPen(palette.highlightedText().color())
        else:
            painter.setPen(palette.text().color())
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class ThumbnailView(QListView):
    pagesMoved = Signal(list, int)  # source rows, destination row (insert-before)
    filesDropped = Signal(list, int)  # list[Path], destination row

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("thumbnailView")
        self.setAccessibleName("Page thumbnails")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(False)
        self.setSpacing(0)  # gaps would make indexAt() miss between items
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(False)  # we paint our own insertion line
        self.setMinimumWidth(THUMB_WIDTH + 2 * PADDING + 20)

        self.thumbnail_delegate = ThumbnailDelegate(self)
        self.setItemDelegate(self.thumbnail_delegate)
        self._drop_row: int | None = None

    def setModel(self, model) -> None:
        super().setModel(model)
        model.modelReset.connect(self.thumbnail_delegate.cache.clear)

    # ------------------------------------------------------------------ helpers
    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.selectionModel().selectedIndexes()})

    def drop_row_at(self, pos: QPoint) -> int:
        """Insert-before row for a drop at viewport position ``pos``."""
        count = self.model().rowCount() if self.model() else 0
        if count == 0:
            return 0
        x = self.visualRect(self.model().index(0, 0)).center().x()
        index = self.indexAt(QPoint(x, pos.y()))
        if not index.isValid():
            first = self.visualRect(self.model().index(0, 0))
            return 0 if pos.y() < first.top() else count
        rect = self.visualRect(index)
        return index.row() + (1 if pos.y() > rect.center().y() else 0)

    def _drop_kind(self, event) -> str | None:
        mime = event.mimeData()
        if event.source() is self and mime.hasFormat(PAGE_MIME_TYPE):
            return "move"
        if mime.hasUrls() and self._dropped_paths(event):
            return "files"
        return None

    @staticmethod
    def _dropped_paths(event) -> list[Path]:
        local = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        return filter_insertable(local)

    def _autoscroll(self, pos: QPoint) -> None:
        bar = self.verticalScrollBar()
        if pos.y() < AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() - AUTOSCROLL_STEP)
        elif pos.y() > self.viewport().height() - AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() + AUTOSCROLL_STEP)

    # ------------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        kind = self._drop_kind(event)
        if kind is None:
            event.ignore()
            return
        event.setDropAction(
            Qt.DropAction.MoveAction if kind == "move" else Qt.DropAction.CopyAction
        )
        event.accept()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        kind = self._drop_kind(event)
        if kind is None:
            event.ignore()
            return
        pos = event.position().toPoint()
        self._autoscroll(pos)
        self._drop_row = self.drop_row_at(pos)
        self.viewport().update()
        event.setDropAction(
            Qt.DropAction.MoveAction if kind == "move" else Qt.DropAction.CopyAction
        )
        event.accept()

    def dragLeaveEvent(self, event) -> None:
        self._drop_row = None
        self.viewport().update()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        kind = self._drop_kind(event)
        destination = self.drop_row_at(event.position().toPoint())
        self._drop_row = None
        self.viewport().update()
        if kind is None:
            event.ignore()
            return
        # Report CopyAction so QAbstractItemView.startDrag() does not try to
        # remove the dragged rows itself; the document does the move.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        # Defer: the model is reset in response, which must not happen while
        # Qt is still inside the drag's event loop.
        if kind == "move":
            rows = self.selected_rows()
            QTimer.singleShot(0, lambda: self.pagesMoved.emit(rows, destination))
        else:
            paths = self._dropped_paths(event)
            QTimer.singleShot(0, lambda: self.filesDropped.emit(paths, destination))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_row is None or self.model() is None:
            return
        count = self.model().rowCount()
        if count == 0:
            y = 4
        elif self._drop_row < count:
            y = self.visualRect(self.model().index(self._drop_row, 0)).top()
        else:
            y = self.visualRect(self.model().index(count - 1, 0)).bottom() + 1
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().highlight().color(), 3, cap=Qt.PenCapStyle.RoundCap))
        painter.drawLine(12, y, self.viewport().width() - 12, y)
        painter.end()
