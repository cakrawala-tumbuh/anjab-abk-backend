"""Endpoint unduhan DOCX: Ringkasan Telaah Prioritas Yayasan dan Lembar Konfirmasi pra-isi."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Row, select

from ...dependencies import (
    READ_GUARDS,
    SessionDep,
    get_alternatif_service,
    get_bukti_service,
    get_cakupan_jabatan_service,
    get_konfirmasi_service,
    get_konteks_service,
    get_koreksi_service,
    get_masalah_service,
    get_penilaian_service,
    get_proses_service,
    get_ringkasan_yayasan_service,
    get_sesi_service,
    get_versi_metode_service,
    require_tim_kajian,
)
from ...errors import NotFoundError
from ...models import (
    JabatanModel,
    JenjangPendidikanModel,
    SekolahModel,
    TiUraianTugasJabatanModel,
)
from ...redesain.ekspor_docx import (
    DOCX_MEDIA_TYPE,
    DataLembar,
    bangun_lembar_konfirmasi,
    bangun_ringkasan,
)
from ...redesain.ekspor_xlsx import XLSX_MEDIA_TYPE, DataRegister, bangun_register
from ...redesain.services.alternatif import AlternatifService
from ...redesain.services.bukti import BuktiService
from ...redesain.services.cakupan_jabatan import CakupanJabatanService
from ...redesain.services.konfirmasi import KonfirmasiService
from ...redesain.services.konteks import KonteksService
from ...redesain.services.koreksi import KoreksiService
from ...redesain.services.masalah import MasalahService
from ...redesain.services.penilaian import PenilaianService
from ...redesain.services.proses import ProsesService
from ...redesain.services.sesi import SesiService
from ...redesain.services.versi_metode import VersiMetodeService
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


_XLSX = {
    200: {
        "description": "Berkas XLSX register 14 sheet.",
        "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
    },
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."},
    429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."},
}
_T = TypeVar("_T")
_BATAS = 100_000


def _semua(ambil: Callable[..., tuple[list[_T], int]]) -> list[_T]:
    """Ambil seluruh baris sebuah service `list(limit=, offset=)` dalam satu panggilan."""
    return ambil(limit=_BATAS, offset=0)[0]


def _peta(baris: Sequence[Row[tuple[str, str]]]) -> dict[str, str]:
    """Ubah baris `(id, nama)` menjadi peta id -> nama."""
    return {b[0]: b[1] for b in baris}


def _peta(baris: Sequence[Row[tuple[str, str]]]) -> dict[str, str]:
    """Ubah baris `(id, nama)` menjadi peta id -> nama."""
    return {b[0]: b[1] for b in baris}


@router.get(
    "/register.xlsx",
    summary="Unduh register terintegrasi, XLSX 14 sheet (tim-kajian)",
    operation_id="redesain_ekspor_register",
    dependencies=_READ,
    responses=_XLSX,
    response_class=Response,
)
def ekspor_register(
    session: SessionDep,
    konteks: Annotated[KonteksService, Depends(get_konteks_service)],
    masalah: Annotated[MasalahService, Depends(get_masalah_service)],
    proses: Annotated[ProsesService, Depends(get_proses_service)],
    konfirmasi: Annotated[KonfirmasiService, Depends(get_konfirmasi_service)],
    koreksi: Annotated[KoreksiService, Depends(get_koreksi_service)],
    bukti: Annotated[BuktiService, Depends(get_bukti_service)],
    penilaian: Annotated[PenilaianService, Depends(get_penilaian_service)],
    alternatif: Annotated[AlternatifService, Depends(get_alternatif_service)],
    sesi: Annotated[SesiService, Depends(get_sesi_service)],
    cakupan: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
    versi: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
    yayasan: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
) -> Response:
    """Satu workbook XLSX 14 sheet bernilai (tanpa rumus), hanya kode orang, urut kode.

    Seluruh data dibaca lewat seam service yang sama dengan endpoint masing-masing entitas.
    """
    daftar_proses = _semua(proses.list)
    koreksi_per_langkah = {
        la.id: koreksi.list_by_langkah(la.id, limit=_BATAS, offset=0)[0]
        for p in daftar_proses
        for la in p.langkah
    }
    uraian_kode: dict[str, list[str]] = {}
    for uid, kode in session.execute(
        select(TiUraianTugasJabatanModel.uraian_tugas_id, TiUraianTugasJabatanModel.kode)
    ).all():
        uraian_kode.setdefault(uid, []).append(kode)
    data = DataRegister(
        konteks=_semua(konteks.list),
        masalah=_semua(masalah.list),
        proses=daftar_proses,
        konfirmasi=_semua(konfirmasi.list_semua),
        koreksi=koreksi_per_langkah,
        bukti=_semua(bukti.list),
        penilaian=_semua(penilaian.list),
        alternatif=_semua(alternatif.list),
        sesi=_semua(sesi.list),
        cakupan=_semua(cakupan.list),
        versi_metode=_semua(versi.list),
        yayasan=_semua(yayasan.list),
        sekolah=_peta(session.execute(select(SekolahModel.id, SekolahModel.nama)).all()),
        jabatan=_peta(session.execute(select(JabatanModel.id, JabatanModel.nama)).all()),
        uraian_kode=uraian_kode,
    )
    nama = f"register-redesain-{date.today():%Y%m%d}.xlsx"
    return Response(
        content=bangun_register(data),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nama}"'},
    )
