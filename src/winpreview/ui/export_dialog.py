"""The “Export as Image” options dialog: format, resolution, background."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QWidget,
)

from winpreview.core.document import DEFAULT_EXPORT_DPI

# (label, extension) — the extension also selects the format in PdfDocument.export_page_image.
FORMATS = [("PNG (best for text)", ".png"), ("JPEG (smaller files)", ".jpg")]
RESOLUTIONS = [
    (72, "72 DPI (screen)"),
    (150, "150 DPI"),
    (300, "300 DPI (print)"),
    (600, "600 DPI (high-quality print)"),
]


@dataclass(frozen=True)
class ExportOptions:
    extension: str  # ".png" or ".jpg"
    dpi: int
    transparent: bool = False  # PNG only


class ExportImageDialog(QDialog):
    def __init__(
        self,
        page_size: tuple[float, float],
        page_count: int,
        defaults: ExportOptions,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export as Image")
        self._page_size = page_size

        self.format_box = QComboBox()
        for label, ext in FORMATS:
            self.format_box.addItem(label, ext)
        self.format_box.setCurrentIndex(max(self.format_box.findData(defaults.extension), 0))

        self.dpi_box = QComboBox()
        for dpi, label in RESOLUTIONS:
            self.dpi_box.addItem(label, dpi)
        index = self.dpi_box.findData(defaults.dpi)
        if index < 0:
            index = self.dpi_box.findData(DEFAULT_EXPORT_DPI)
        self.dpi_box.setCurrentIndex(index)

        self.size_label = QLabel()
        self.dpi_box.currentIndexChanged.connect(self._update_size)
        self._update_size()

        self.transparent_box = QCheckBox("&Transparent background")
        self.transparent_box.setChecked(defaults.transparent)
        self.transparent_box.setToolTip(
            "Leave the page background see-through instead of white (PNG only). "
            "Pages that paint their own white background stay white."
        )
        self.format_box.currentIndexChanged.connect(self._update_transparent)
        self._update_transparent()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        pages = "1 page" if page_count == 1 else f"{page_count} pages"
        layout.addRow(QLabel(f"Export {pages} as images."))
        layout.addRow("&Format:", self.format_box)
        layout.addRow("&Resolution:", self.dpi_box)
        layout.addRow("Image size:", self.size_label)
        layout.addRow("", self.transparent_box)
        layout.addRow(buttons)

    def options(self) -> ExportOptions:
        extension = self.format_box.currentData()
        transparent = extension == ".png" and self.transparent_box.isChecked()
        return ExportOptions(extension, self.dpi_box.currentData(), transparent)

    def _update_transparent(self) -> None:
        # Keep the tick while JPEG is chosen so switching back to PNG restores it.
        self.transparent_box.setEnabled(self.format_box.currentData() == ".png")

    def _update_size(self) -> None:
        dpi = self.dpi_box.currentData()
        width, height = (round(side * dpi / 72) for side in self._page_size)
        self.size_label.setText(f"{width} × {height} pixels")  # noqa: RUF001

    @classmethod
    def get_options(
        cls,
        parent: QWidget | None,
        page_size: tuple[float, float],
        page_count: int,
        defaults: ExportOptions,
    ) -> ExportOptions | None:
        """Show the dialog modally; None means the user cancelled."""
        dialog = cls(page_size, page_count, defaults, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.options()
