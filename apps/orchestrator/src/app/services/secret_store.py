from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from typing import Protocol


class SecretProtector(Protocol):
    def protect(self, value: str) -> str: ...

    def unprotect(self, value: str) -> str: ...


class WindowsDpapiProtector:
    def protect(self, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("secret must be a non-empty string")
        raw = value.encode("utf-8")
        encrypted = _crypt_protect(raw)
        return base64.b64encode(encrypted).decode("ascii")

    def unprotect(self, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("protected secret must be a non-empty string")
        raw = base64.b64decode(value.encode("ascii"))
        return _crypt_unprotect(raw).decode("utf-8")


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32


def _blob_from_bytes(data: bytes) -> _DataBlob:
    if not data:
        return _DataBlob(0, None)
    buffer = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))


def _blob_to_bytes(blob: _DataBlob) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def _crypt_protect(data: bytes) -> bytes:
    in_blob = _blob_from_bytes(data)
    out_blob = _DataBlob()
    if not _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    return _blob_to_bytes(out_blob)


def _crypt_unprotect(data: bytes) -> bytes:
    in_blob = _blob_from_bytes(data)
    out_blob = _DataBlob()
    if not _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    return _blob_to_bytes(out_blob)
