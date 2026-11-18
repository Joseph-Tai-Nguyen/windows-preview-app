"""Qt-free document logic. Nothing in this package may import PySide6."""

from winpreview.core.document import (
    DocumentError,
    PasswordRequiredError,
    PdfDocument,
    RenderedPage,
)

__all__ = ["DocumentError", "PasswordRequiredError", "PdfDocument", "RenderedPage"]
