"""Render the SVG app icon into a multi-resolution Windows .ico (and a 256px PNG).

Usage:  .venv\\Scripts\\python scripts\\make_icon.py

Uses only PySide6 (QtSvg) - no Pillow needed. The .ico stores PNG-compressed
images, which every Windows version since Vista supports.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parents[1] / "src" / "winpreview" / "resources" / "icons"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def build_ico(images: dict[int, bytes]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in sorted(images.items()):
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def main() -> int:
    QGuiApplication(sys.argv[:1])
    renderer = QSvgRenderer(str(ICON_DIR / "winpreview.svg"))
    if not renderer.isValid():
        print("Invalid SVG", file=sys.stderr)
        return 1
    images = {size: render_png(renderer, size) for size in SIZES}
    (ICON_DIR / "winpreview.ico").write_bytes(build_ico(images))
    (ICON_DIR / "winpreview-256.png").write_bytes(images[256])
    print(f"Wrote {ICON_DIR / 'winpreview.ico'} ({', '.join(map(str, SIZES))} px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
