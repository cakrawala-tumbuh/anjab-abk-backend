"""Util ETag untuk concurrency control opsional (optimistic locking)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from .errors import PreconditionFailedError, PreconditionRequiredError


def compute_etag(payload: BaseModel | Sequence[BaseModel] | dict[str, Any]) -> str:
    """Hitung ETag kuat dari representasi JSON kanonik sebuah respons.

    Args:
        payload: Model Pydantic, daftar model (mis. daftar jawaban satu responden),
            atau dict JSON-able.

    Returns:
        Digest SHA-256 terpotong 32 hex, dibungkus tanda kutip ganda (`"<hex>"`).
    """
    if isinstance(payload, BaseModel):
        data: Any = payload.model_dump(mode="json")
    elif isinstance(payload, dict):
        data = payload
    else:
        data = [p.model_dump(mode="json") for p in payload]
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'


def check_if_match(
    current: BaseModel | Sequence[BaseModel] | dict[str, Any],
    if_match: str | None,
    required: bool,
) -> None:
    """Periksa prasyarat `If-Match` terhadap keadaan resource saat ini (RFC 7232).

    Helper bersama untuk rute tulis (PATCH/PUT/DELETE) yang memakai kunci optimistik;
    semantiknya sama dengan pemeriksa lama di router master data.

    Args:
        current: Representasi resource saat ini, sama persis dengan yang dikembalikan
            GET sumbernya (agar ETag-nya cocok).
        if_match: Nilai header `If-Match`; `None` bila header tidak dikirim.
        required: Bila True (setting `REQUIRE_IF_MATCH`), header yang absen ditolak.

    Raises:
        PreconditionRequiredError: Header absen padahal `required` (428).
        PreconditionFailedError: Tak satu pun ETag dalam daftar cocok (412). ETag lemah
            (`W/...`) dilewati; `*` selalu lolos.
    """
    if if_match is None:
        if required:
            raise PreconditionRequiredError("Header If-Match wajib disertakan.")
        return
    if_match = if_match.strip()
    if if_match == "*":
        return
    current_etag = compute_etag(current)
    for candidate in if_match.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            continue
        if candidate == current_etag:
            return
    raise PreconditionFailedError("If-Match tidak cocok; resource telah berubah.")
