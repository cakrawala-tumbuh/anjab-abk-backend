"""Endpoint admin: backup (unduh dump) & restore basis data penuh (backlog 025).

Aksi sistem, bukan resource CRUD — sengaja TIDAK menambah endpoint list/get/delete;
lihat `## Keputusan Desain` issue 025. Server tidak menyimpan salinan cadangan apa pun:
`backup` mengalirkan langsung keluaran `pg_dump`, `restore` hanya menulis berkas
sementara sekali-pakai yang dihapus otomatis begitu selesai diproses.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from ...dependencies import get_backup_service, rate_limit, require_admin
from ...schemas.backup import RestoreResult
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...services.backup import BackupService

router = APIRouter()

logger = logging.getLogger("anjab_abk_backend.api.v1.system_backup")

_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_KONFIRMASI_INVALID = {
    422: {
        "model": ErrorResponse,
        "description": (
            "Konfirmasi tidak cocok dengan nama basis data, atau berkas bukan dump valid."
        ),
    }
}
_TERLALU_BESAR = {
    413: {"model": ErrorResponse, "description": "Berkas melebihi batas ukuran unggahan restore."}
}


@router.post(
    "/backup",
    summary="Unduh cadangan penuh basis data",
    operation_id="system_backup",
    dependencies=_ADMIN_GUARDS,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "Dump `pg_dump --format=custom` (biner), dialirkan langsung.",
        },
        **_AUTH,
        **_FORBIDDEN,
        **_RATE,
    },
)
def backup(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[BackupService, Depends(get_backup_service)],
) -> StreamingResponse:
    """Streaming `pg_dump --format=custom --no-acl --no-owner` sebagai unduhan.

    Server tidak menahan salinan dump di memori/disk — setiap potongan langsung
    diteruskan ke klien begitu diterima dari subprocess `pg_dump`.
    """
    logger.warning("system_backup", extra={"actor": principal.subject})
    filename = service.backup_filename()
    return StreamingResponse(
        service.stream_dump(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/restore",
    response_model=RestoreResult,
    summary="Pulihkan basis data penuh dari cadangan",
    operation_id="system_restore",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_FORBIDDEN, **_RATE, **_KONFIRMASI_INVALID, **_TERLALU_BESAR},
)
def restore(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[BackupService, Depends(get_backup_service)],
    berkas: Annotated[
        UploadFile, File(description="Berkas dump `pg_dump --format=custom` yang diunggah.")
    ],
    konfirmasi: Annotated[
        str,
        Form(
            description=(
                "Nama basis data tujuan (dari `DATABASE_URL`) — harus diketik PERSIS sama"
                " untuk mengonfirmasi restore destruktif."
            )
        ),
    ],
) -> RestoreResult:
    """DESTRUKTIF: mengganti SELURUH isi basis data dengan isi `berkas`.

    Menolak (422) tanpa menyentuh basis data bila `konfirmasi` tidak persis sama
    dengan nama basis data tujuan. Skema TIDAK di-upgrade otomatis setelah restore —
    lihat `RestoreResult.peringatan` bila revisi Alembic hasil restore berbeda dari
    head aplikasi.
    """
    logger.warning("system_restore", extra={"actor": principal.subject})
    return service.restore(berkas.file, konfirmasi)
