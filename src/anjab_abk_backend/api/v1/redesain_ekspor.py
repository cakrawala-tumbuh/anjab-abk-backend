"""Endpoint unduhan DOCX: Ringkasan Telaah Prioritas Yayasan dan Lembar Konfirmasi pra-isi."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from ...dependencies import (
    READ_GUARDS,
    SessionDep,
    get_masalah_service,
    get_ringkasan_yayasan_service,
    require_tim_kajian,
)
from ...errors import NotFoundError
from ...models import JenjangPendidikanModel, SekolahModel
from ...redesain.ekspor_docx import (
    DOCX_MEDIA_TYPE,
    DataLembar,
    bangun_lembar_konfirmasi,
    bangun_ringkasan,
)
from ...redesain.services.masalah import MasalahService
from ...redesain.services.yayasan import RingkasanYayasanService
from ...schemas.common import ErrorResponse

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_DOCX = {
    200: {
        "description": "Berkas DOCX.",
        "content": {DOCX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
    },
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."},
    404: {"model": ErrorResponse, "description": "Masalah/penilaian tidak ditemukan."},
    429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."},
}
_STATUS_AGENDA = "Siap untuk telaah yayasan"


def _docx(isi: bytes, nama: str) -> Response:
    """Bungkus bytes DOCX sebagai respons unduhan."""
    return Response(
        content=isi,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nama}"'},
    )


@router.get(
    "/ringkasan-yayasan",
    summary="Unduh ringkasan yayasan seluruh agenda, satu DOCX (tim-kajian)",
    operation_id="redesain_ekspor_ringkasan_batch",
    dependencies=_READ,
    responses=_DOCX,
    response_class=Response,
)
def ekspor_ringkasan_batch(
    service: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
    status_penilaian: Annotated[
        str, Query(description="Status penilaian yang diekspor.")
    ] = _STATUS_AGENDA,
) -> Response:
    """Satu DOCX, satu masalah per halaman, urut kode masalah; tanpa hasil -> 404."""
    rows, _ = service.search(
        domain=[("status_penilaian", "=", status_penilaian)],
        order=[],
        limit=10_000,
        offset=0,
    )
    if not rows:
        raise NotFoundError(f"Tidak ada penilaian berstatus '{status_penilaian}'.")
    rows.sort(key=lambda r: r.masalah_kode)
    return _docx(bangun_ringkasan(rows), "agenda-yayasan.docx")


@router.get(
    "/ringkasan-yayasan/{masalah_id}",
    summary="Unduh ringkasan yayasan satu masalah (tim-kajian)",
    operation_id="redesain_ekspor_ringkasan",
    dependencies=_READ,
    responses=_DOCX,
    response_class=Response,
)
def ekspor_ringkasan(
    masalah_id: str,
    service: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
) -> Response:
    """Satu halaman ringkasan untuk satu masalah (bersumber hanya dari read-model yayasan)."""
    r = service.get(masalah_id)
    return _docx(bangun_ringkasan([r]), f"{r.masalah_kode}.docx")


@router.get(
    "/lembar-konfirmasi/{masalah_id}",
    summary="Unduh Lembar Konfirmasi pra-isi bagian A (tim-kajian)",
    operation_id="redesain_ekspor_lembar_konfirmasi",
    dependencies=_READ,
    responses=_DOCX,
    response_class=Response,
)
def ekspor_lembar_konfirmasi(
    masalah_id: str,
    session: SessionDep,
    yayasan: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
    masalah_service: Annotated[MasalahService, Depends(get_masalah_service)],
) -> Response:
    """Lembar Konfirmasi dengan bagian A terisi; bagian B-E isian kosong."""
    r = yayasan.get(masalah_id)
    m = masalah_service.get(masalah_id)
    jenjang = None
    if m.sekolah_id:
        jenjang = session.scalar(
            select(JenjangPendidikanModel.nama)
            .join(SekolahModel, SekolahModel.jenjang_pendidikan_id == JenjangPendidikanModel.id)
            .where(SekolahModel.id == m.sekolah_id)
        )
    data = DataLembar(
        masalah_kode=r.masalah_kode,
        konteks_kode=r.konteks_kode,
        proses_kode=r.proses_kode,
        sekolah=r.sekolah_konteks,
        jenjang=jenjang,
        periode_acuan=r.periode_acuan,
        sumber_awal=r.sumber_awal_keterbatasan,
        status_awal=m.status_awal,
        rumusan_hipotesis=r.rumusan_hipotesis,
    )
    return _docx(bangun_lembar_konfirmasi(data), f"{r.masalah_kode}.docx")
