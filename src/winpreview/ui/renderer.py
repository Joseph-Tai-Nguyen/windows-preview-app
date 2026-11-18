"""Converts rendered pages into QPixmaps and caches them (LRU)."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QImage, QPixmap

from winpreview.core import PdfDocument


class PixmapCache:
    """Renders pages on demand at a given scale and keeps the most recent ones.

    Keys are (page index, effective scale). The cache must be cleared whenever
    the document's pages change, because indices then refer to other pages.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._items: OrderedDict[tuple[int, float], QPixmap] = OrderedDict()

    def get(self, doc: PdfDocument, row: int, scale: float, device_pixel_ratio: float) -> QPixmap:
        effective = round(scale * device_pixel_ratio, 4)
        key = (row, effective)
        pixmap = self._items.get(key)
        if pixmap is not None:
            self._items.move_to_end(key)
            return pixmap

        page = doc.render_page(row, effective)
        image = QImage(
            page.samples, page.width, page.height, page.stride, QImage.Format.Format_RGB888
        ).copy()  # detach from the Python bytes buffer
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(device_pixel_ratio)

        self._items[key] = pixmap
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)
        return pixmap

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
