from __future__ import annotations

import pytest

from winpreview.core import scanner


class FakeComError(Exception):
    def __init__(self, hresult: int, scode: int | None = None) -> None:
        super().__init__("com error")
        self.hresult = hresult - (1 << 32) if hresult & 0x80000000 else hresult
        self.excepinfo = (0, "WIA", "desc", None, 0, scode) if scode is not None else None


def test_is_supported_returns_bool():
    assert isinstance(scanner.is_supported(), bool)


def test_no_device_is_unavailable():
    error = scanner._translate(FakeComError(0x80210015))
    assert isinstance(error, scanner.ScannerUnavailableError)


def test_error_inside_dispatch_exception():
    # DISP_E_EXCEPTION wrapping a WIA "busy" code in excepinfo.
    error = scanner._translate(FakeComError(0x80020009, scode=0x80210006))
    assert type(error) is scanner.ScannerError
    assert "busy" in str(error)


def test_unknown_error_is_generic():
    error = scanner._translate(FakeComError(0x80004005))
    assert type(error) is scanner.ScannerError


def test_acquire_without_support_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner, "is_supported", lambda: False)
    with pytest.raises(scanner.ScannerUnavailableError):
        scanner.acquire_image(tmp_path)
