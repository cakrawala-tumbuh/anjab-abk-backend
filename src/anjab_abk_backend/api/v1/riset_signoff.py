"""Endpoint sign-off PI/etik protokol riset: khusus `tim-kajian`, append-only.

Bukti berupa PDF persetujuan etik plus tanggal wajib, dicatat satu kali per protokol
`TERKUNCI`. Tidak ada sunting/hapus/ganti. Pencatat menyatakan diri sebagai PI lewat
`pi_nama`; server hanya merekam `dicatat_oleh` (tanpa grup baru, tanpa verifikasi jabatan).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    get_current_principal,
    get_riset_signoff_service,
    rate_limit,
    require_tim_kajian,
)
from ...schemas.common import ErrorResponse
from ...schemas.riset_signoff import BATAS_NOMOR_ETIK, BATAS_PI_NAMA, SignoffRead
from ...security import Principal
from ...services.riset_signoff import RisetSignoffService

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {
    404: {
        "model": ErrorResponse,
        "description": "Protokol tak ada, atau (GET) belum ada sign-off (`SIGNOFF_TAK_ADA`).",
    }
}


@router.post(
    "/{protokol_id}/sign-off",
    response_model=SignoffRead,
    status_code=201,
    summary="Catat bukti sign-off PI/etik protokol terkunci (tim-kajian)",
    operation_id="riset_protokol_signoff_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Protokol riset tidak ditemukan."},
        409: {
            "model": ErrorResponse,
            "description": "`PROTOKOL_BELUM_TERKUNCI` atau `SIGNOFF_SUDAH_ADA`.",
        },
        413: {"model": ErrorResponse, "description": "Body melebihi batas rute sign-off."},
        422: {
            "model": ErrorResponse,
            "description": (
                "`LAMPIRAN_BUKAN_PDF`, `LAMPIRAN_TERLALU_BESAR`, atau validasi form/tanggal."
            ),
        },
    },
)
def create_signoff(
    protokol_id: str,
    service: Annotated[RisetSignoffService, Depends(get_riset_signoff_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    pi_nama: Annotated[
        str, Form(min_length=1, max_length=BATAS_PI_NAMA, description="Nama PI penandatangan.")
    ],
    tanggal_persetujuan_etik: Annotated[
        date, Form(description="Tanggal persetujuan etik (YYYY-MM-DD, tidak di masa depan).")
    ],
    lampiran: Annotated[UploadFile, File(description="PDF persetujuan etik.")],
    nomor_persetujuan_etik: Annotated[
        str | None, Form(max_length=BATAS_NOMOR_ETIK, description="Nomor surat persetujuan.")
    ] = None,
) -> SignoffRead:
    """Catat sign-off satu kali; PDF disimpan di PostgreSQL beserta SHA-256-nya.

    Urutan cek: 404, 409 `PROTOKOL_BELUM_TERKUNCI`, 409 `SIGNOFF_SUDAH_ADA`, 422
    `LAMPIRAN_BUKAN_PDF` (content-type dan byte awal `%PDF-`), 422 `LAMPIRAN_TERLALU_BESAR`,
    422 tanggal di masa depan. Berkas dibaca paling banyak batas + 1 byte.
    """
    maks = settings.riset_signoff_max_bytes
    isi = lampiran.file.read(maks + 1)
    return service.create(
        protokol_id,
        pi_nama=pi_nama.strip(),
        tanggal_persetujuan_etik=tanggal_persetujuan_etik,
        nomor_persetujuan_etik=(nomor_persetujuan_etik or "").strip() or None,
        lampiran_nama=lampiran.filename or "signoff.pdf",
        content_type=lampiran.content_type,
        isi=isi,
        maks_bytes=maks,
        dicatat_oleh=principal.subject,
    )


@router.get(
    "/{protokol_id}/sign-off",
    response_model=SignoffRead,
    summary="Metadata sign-off PI/etik protokol (tim-kajian)",
    operation_id="riset_protokol_signoff_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_signoff(
    protokol_id: str,
    service: Annotated[RisetSignoffService, Depends(get_riset_signoff_service)],
) -> SignoffRead:
    """Metadata sign-off tanpa byte berkas; 404 `SIGNOFF_TAK_ADA` bila belum dicatat."""
    return service.get(protokol_id)


@router.get(
    "/{protokol_id}/sign-off/lampiran",
    summary="Unduh PDF sign-off PI/etik (tim-kajian)",
    operation_id="riset_protokol_signoff_lampiran",
    dependencies=_READ,
    response_class=Response,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        200: {"content": {"application/pdf": {}}, "description": "Byte PDF apa adanya."},
    },
)
def unduh_lampiran(
    protokol_id: str,
    service: Annotated[RisetSignoffService, Depends(get_riset_signoff_service)],
) -> Response:
    """Kembalikan PDF sebagai `attachment`; header `ETag` = SHA-256 berkas."""
    lampiran = service.lampiran(protokol_id)
    nama_aman = "".join(c if c.isalnum() or c in "._-" else "_" for c in lampiran.nama)
    return Response(
        content=lampiran.isi,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nama_aman}"',
            "ETag": f'"{lampiran.sha256}"',
        },
    )
