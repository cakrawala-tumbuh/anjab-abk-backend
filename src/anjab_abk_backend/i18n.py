"""Seam internasionalisasi pesan error (default identitas)."""

from __future__ import annotations

from starlette.requests import Request

DEFAULT_LOCALE = "id"


def get_locale(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LOCALE
    header = request.headers.get("accept-language")
    if not header:
        return DEFAULT_LOCALE
    primary = header.split(",")[0].split(";")[0].strip()
    return primary.split("-")[0].lower() or DEFAULT_LOCALE


def translate(message: str, locale: str) -> str:
    """SEAM — kembalikan pesan terlokalisasi. Default identitas."""
    return message
