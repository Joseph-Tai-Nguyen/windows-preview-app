"""The main, continuously scrolling page view."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from winpreview.ui.page_model import PAGE_SIZE_ROLE
from winpreview.ui.renderer import PixmapCache

PAGE_MARGIN = 14
MIN_ZOOM = 0.1
MAX_ZOOM = 6.0
ZOOM_STEP = 1.25


class PageDelegate(QStyledItemDelegate):
    def __init__(self, view: PageView) -> None:
        super().__init__(view)
        self._view = view
        self.cache = PixmapCache(capacity=16)

    def _page_rect_size(self, index: QModelIndex) -> tuple[int, int]:
        width, height = index.data(PAGE_SIZE_ROLE) or (612.0, 792.0)
        zoom = self._view.zoom()
        return round(width * zoom), round(height * zoom)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        pw, ph = self._page_rect_size(index)
        # Span at least the viewport so pages are centred horizontally.
        width = max(pw + 2 * PAGE_MARGIN, self._view.viewport().width())
        return QSize(width, ph + PAGE_MARGIN)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        doc = index.model().document()
        if doc is None:
            return
        pw, ph = self._page_rect_size(index)
        rect = option.rect
        target = QRect(rect.x() + (rect.width() - pw) // 2, rect.y() + PAGE_MARGIN, pw, ph)
        dpr = option.widget.devicePixelRatioF() if option.widget else 1.0

        painter.save()
        painter.fillRect(target.translated(2, 2), QColor(0, 0, 0, 50))  # drop shadow
        painter.drawPixmap(target, self.cache.get(doc, index.row(), self._view.zoom(), dpr))
        painter.setPen(QPen(QColor(0, 0, 0, 70), 1))
        painter.drawRect(target.adjusted(0, 0, -1, -1))
        painter.restore()


class PageView(QListView):
    """Shows every page top-to-bottom; zoom is either 'fit width' or fixed."""

    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageView")
        self.setAccessibleName("Pages")
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setUniformItemSizes(False)
        self.setSpacing(0)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setStyleSheet("QListView#pageView { background: palette(mid); }")
        self.verticalScrollBar().setSingleStep(24)

        self._zoom = 1.0
        self._fit_width = True
        self._widest_page: float | None = None
        self._current_page = -1

        self.page_delegate = PageDelegate(self)
        self.setItemDelegate(self.page_delegate)
        self.verticalScrollBar().valueChanged.connect(self._update_current_page)

    def setModel(self, model) -> None:
        super().setModel(model)
        model.modelReset.connect(self._on_model_reset)

    # ------------------------------------------------------------------ zoom
    def zoom(self) -> float:
        return self._zoom

    def is_fit_width(self) -> bool:
        return self._fit_width

    def set_zoom(self, zoom: float) -> None:
        self._fit_width = False
        self._apply_zoom(zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / ZOOM_STEP)

    def fit_width(self) -> None:
        self._fit_width = True
        self._apply_fit_width()

    def _apply_zoom(self, zoom: float) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        anchor = self.current_page()
        changed = abs(zoom - self._zoom) > 1e-4
        self._zoom = zoom
        self.doItemsLayout()
        if changed:
            if anchor >= 0:
                self.scroll_to_page(anchor)
            self.zoomChanged.emit(zoom)

    def _apply_fit_width(self) -> None:
        widest = self._widest()
        if widest:
            available = self.viewport().width() - 2 * PAGE_MARGIN - 2
            self._apply_zoom(available / widest)

    def _widest(self) -> float:
        if self._widest_page is None:
            model = self.model()
            doc = model.document() if model is not None else None
            if doc is None or doc.page_count == 0:
                return 0.0
            self._widest_page = max(doc.page_size(i)[0] for i in range(doc.page_count))
        return self._widest_page

    # ------------------------------------------------------------------ navigation
    def scroll_to_page(self, row: int) -> None:
        model = self.model()
        if model is not None and 0 <= row < model.rowCount():
            self.scrollTo(model.index(row, 0), QAbstractItemView.ScrollHint.PositionAtTop)

    def current_page(self) -> int:
        """The page under the upper third of the viewport, or -1."""
        if self.model() is None or self.model().rowCount() == 0:
            return -1
        index = self.indexAt(QPoint(self.viewport().width() // 2, self.viewport().height() // 3))
        if not index.isValid():
            index = self.indexAt(QPoint(self.viewport().width() // 2, 1))
        return index.row() if index.isValid() else 0

    def _update_current_page(self) -> None:
        page = self.current_page()
        if page != self._current_page:
            self._current_page = page
            self.currentPageChanged.emit(page)

    def _on_model_reset(self) -> None:
        self.page_delegate.cache.clear()
        self._widest_page = None
        self._current_page = -1
        if self._fit_width:
            self._apply_fit_width()

    # ------------------------------------------------------------------ events
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_width:
            self._apply_fit_width()
        else:
            self.doItemsLayout()  # item widths track the viewport
        self._update_current_page()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            elif event.angleDelta().y() < 0:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)
