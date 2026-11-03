"""Perangkat bersama kunci optimistik (If-Match/ETag) dan Idempotency-Key untuk rute tulis.

Dipakai ulang oleh rute tulis WCP/DCS dan kelompok lain (OPM/TI/redesain). Pemeriksaan
`If-Match` sendiri ada di `anjab_abk_backend.etag.check_if_match`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from fastapi import Header, Response, status
from pydantic import TypeAdapter

from ..dependencies import Idempotency
from ..errors import ConflictError
from ..schemas.common import ErrorResponse

T = TypeVar("T")

IfMatchHeader = Annotated[
    str | None, Header(alias="If-Match", description="ETag untuk concurrency control.")
]
"""Anotasi parameter header `If-Match` (opsional kecuali `REQUIRE_IF_MATCH=true`)."""

PRECONDITION_RESPONSES: dict[int | str, dict[str, Any]] = {
    412: {"model": ErrorResponse, "description": "If-Match tidak cocok."},
    428: {"model": ErrorResponse, "description": "If-Match wajib (REQUIRE_IF_MATCH=true)."},
}
"""Blok `responses` OpenAPI untuk rute ber-If-Match."""

IDEMPOTENCY_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": "Idempotency-Key ini sedang diproses (atau konflik state).",
    },
}
"""Blok `responses` OpenAPI untuk rute POST ber-Idempotency-Key."""


def run_idempotent(
    idem: Idempotency,
    response: Response,
    response_type: Any,
    action: Callable[[], T],
) -> T:
    """Jalankan `action` sekali per Idempotency-Key; ulangan mengembalikan hasil tersimpan.

    Args:
        idem: Dependency `idempotency` (key sudah di-scope `{method}:{path}:{key}`).
        response: Objek `Response` rute, dipakai menurunkan status ke 200 saat replay.
        response_type: Tipe respons (mis. `list[X]`, `BulkAssignResult[X]`) untuk
            serialisasi/validasi ulang hasil tersimpan.
        action: Callable tanpa argumen yang melakukan operasi sebenarnya.

    Returns:
        Hasil `action`, atau hasil tersimpan (status 200) bila key sudah selesai.

    Raises:
        ConflictError: Key yang sama masih diproses request lain (409).

    Note:
        Tanpa header `Idempotency-Key`, `action` dijalankan apa adanya. Bila `action`
        gagal, reservasi dilepas supaya key dapat dicoba lagi.
    """
    adapter: TypeAdapter[Any] = TypeAdapter(response_type)
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return adapter.validate_python(cached["result"])
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        result = action()
    except Exception:
        idem.release()
        raise
    if idem.key:
        idem.store.save(idem.key, {"result": adapter.dump_python(result, mode="json")})
    return result
