"""Scanner access through Windows Image Acquisition (WIA).

Uses the WIA Automation COM API (``WIA.CommonDialog``) via pywin32, which shows
the standard Windows scan dialog and works with any WIA-compatible scanner or
multifunction printer. The import of pywin32 is lazy so the rest of the app
(and the tests) work on machines without it.

Must be called from the GUI thread: WIA's dialog needs a single-threaded COM
apartment, which Qt's main thread already provides.
"""

from __future__ import annotations

import sys
from pathlib import Path

# WIA Automation constants (wiaaut.dll).
WIA_DEVICE_TYPE_SCANNER = 1
WIA_INTENT_COLOR = 1
WIA_BIAS_MAX_QUALITY = 131072
WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"

_WIA_ERRORS = {
    0x80210015: "No scanner was found. Check that it is connected and turned on.",
    0x80210005: "The scanner is offline.",
    0x80210006: "The scanner is busy. Try again in a moment.",
    0x80210003: "The document feeder is empty.",
    0x80210002: "The scanner has a paper jam.",
    0x8021000A: "The scanner is warming up. Try again in a moment.",
}


class ScannerError(Exception):
    """Scanning failed with a user-facing message."""


class ScannerUnavailableError(ScannerError):
    """Scanning is not possible on this machine (no WIA, no pywin32 or no device)."""


def is_supported() -> bool:
    """True if this platform can attempt a WIA scan at all."""
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def acquire_image(dest_dir: str | Path) -> Path | None:
    """Show the Windows scan dialog and save one scanned page into ``dest_dir``.

    Returns the image path, or ``None`` if the user cancelled.
    """
    if not is_supported():
        raise ScannerUnavailableError("Scanning requires Windows with the pywin32 package.")

    import pywintypes
    import win32com.client

    try:
        dialog = win32com.client.Dispatch("WIA.CommonDialog")
        image = dialog.ShowAcquireImage(
            WIA_DEVICE_TYPE_SCANNER,
            WIA_INTENT_COLOR,
            WIA_BIAS_MAX_QUALITY,
            WIA_FORMAT_PNG,
            False,  # AlwaysSelectDevice
            True,  # UseCommonUI
            False,  # CancelError: return None on cancel instead of raising
        )
    except pywintypes.com_error as exc:
        raise _translate(exc) from exc

    if image is None:
        return None

    # The device may not honour the PNG request; use whatever it produced.
    extension = str(getattr(image, "FileExtension", "") or "png").lower()
    dest = Path(dest_dir) / f"scan.{extension}"
    dest.unlink(missing_ok=True)  # WIA's SaveFile refuses to overwrite
    try:
        image.SaveFile(str(dest))
    except pywintypes.com_error as exc:
        raise _translate(exc) from exc
    return dest


def _translate(exc: Exception) -> ScannerError:
    codes = {getattr(exc, "hresult", 0) & 0xFFFFFFFF}
    excepinfo = getattr(exc, "excepinfo", None)
    if excepinfo and len(excepinfo) > 5 and excepinfo[5]:
        codes.add(excepinfo[5] & 0xFFFFFFFF)
    for code in codes:
        if code == 0x80210015:
            return ScannerUnavailableError(_WIA_ERRORS[code])
        if code in _WIA_ERRORS:
            return ScannerError(_WIA_ERRORS[code])
    return ScannerError(f"The scan failed.\n\n{exc}")
