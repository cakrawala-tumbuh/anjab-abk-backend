"""Endpoint konfirmasi sekolah redesain (sheet KONFIRMASI / Lembar Konfirmasi).

Dua router: `router_sekolah` di-mount ke `/redesain/sekolah` (daftar masalah untuk
sekolah pemanggil) dan `router` ke `/redesain/konfirmasi` (draf & aksi berurutan).
Pengisi adalah grup `sekolah-pengisi`; urutan cerita-dikunci → dugaan-ditampilkan →
penilaian → kirim ditegakkan di seam service. Tidak ada PUT/DELETE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_service,
    get_konfirmasi_service,
    get_koreksi_service,
    get_partisipan_service,
    pagination_params,
    rate_limit,
    require_sekolah_pengisi,
    require_tim_kajian_atau_pengisi,
)
from ...errors import ForbiddenError
from ...redesain.schemas.konfirmasi import (
    DugaanRead,
    KonfirmasiCreate,
    KonfirmasiRead,
    KonfirmasiUpdate,
    MasalahSekolahRead,
)
from ...redesain.schemas.koreksi import AlurRead
from ...redesain.schemas.kosakata import GRUP_TIM_KAJIAN
from ...redesain.services.kode_orang import KodeOrangService
from ...redesain.services.konfirmasi import KonfirmasiService
from ...redesain.services.koreksi import KoreksiService
from ...schemas.common import ErrorResponse, Page
from ...security import Principal

router = APIRouter()
router_sekolah = APIRouter()

_WRITE = [Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {
        "model": ErrorResponse,
        "description": "Bukan sekolah pengisi, di luar sekolah Anda, atau bukan milik Anda.",
    }
}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Konfirmasi tidak ditemukan."}}
_TERKIRIM = {
    409: {
        "model": ErrorResponse,
        "description": "Konfirmasi sudah terkirim (`KONFIRMASI_SUDAH_TERKIRIM`).",
    }
}


@dataclass(frozen=True)
class Pengisi:
    """Identitas pengisi konfirmasi: kode pseudonim + sekolah partisipannya."""

    kode_orang: str
    sekolah_id: str


def get_pengisi(
    principal: Annotated[Principal, Depends(require_sekolah_pengisi)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Pengisi:
    """Resolusi pemanggil `sekolah-pengisi` ke kode orang (get-or-create) & sekolahnya.

    Raises:
        ForbiddenError: bukan grup `sekolah-pengisi`, tak punya record partisipan, atau
            partisipan tanpa sekolah.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None or not par.sekolah_id:
        raise ForbiddenError("Akses ditolak: pemanggil tidak terdaftar pada sekolah mana pun.")
    return Pengisi(kode_orang=ko_service.untuk_partisipan(par.id).kode, sekolah_id=par.sekolah_id)


PengisiDep = Annotated[Pengisi, Depends(get_pengisi)]
ServiceDep = Annotated[KonfirmasiService, Depends(get_konfirmasi_service)]


@router_sekolah.get(
    "/masalah",
    response_model=Page[MasalahSekolahRead],
    summary="Daftar masalah yang dibuka untuk konfirmasi sekolah Anda (sekolah-pengisi)",
    operation_id="redesain_sekolah_masalah_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_masalah_sekolah(
    pengisi: PengisiDep,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: ServiceDep,
) -> Page[MasalahSekolahRead]:
    """Masalah `dibuka_untuk_konfirmasi=true` milik sekolah pemanggil, terurut `kode`.

    Hanya bagian A Lembar Konfirmasi — `rumusan_hipotesis` sengaja tidak ikut agar dugaan
    Tim tidak terlihat sebelum cerita pengisi dikunci.
    """
    items, total = service.list_masalah_sekolah(
        pengisi.sekolah_id, limit=page.limit, offset=page.offset
    )
    return Page[MasalahSekolahRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=KonfirmasiRead,
    status_code=201,
    summary="Mulai draf konfirmasi untuk satu masalah (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Masalah tidak ditemukan."},
        409: {
            "model": ErrorResponse,
            "description": "Sudah ada draf/terkirim untuk masalah ini (`KONFIRMASI_SUDAH_ADA`).",
        },
    },
)
def create_konfirmasi(
    data: KonfirmasiCreate, pengisi: PengisiDep, service: ServiceDep
) -> KonfirmasiRead:
    """Buat draf `daring` untuk masalah sekolah pemanggil; `sekolah_id` disalin dari partisipan.

    Masalah sekolah lain atau belum dibuka → 403; satu orang hanya satu draf/terkirim per
    masalah → 409.
    """
    return service.create(
        data.masalah_id, kode_orang=pengisi.kode_orang, sekolah_id=pengisi.sekolah_id
    )


@router.get(
    "/{konfirmasi_id}",
    response_model=KonfirmasiRead,
    summary="Detail konfirmasi (pemilik atau tim-kajian)",
    operation_id="redesain_konfirmasi_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_konfirmasi(
    konfirmasi_id: str,
    principal: Annotated[Principal, Depends(require_tim_kajian_atau_pengisi)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    service: ServiceDep,
) -> KonfirmasiRead:
    """Ambil satu konfirmasi beserta `dugaan_diperlihatkan` (`Ya`/`Belum`).

    `tim-kajian` boleh membaca semua; `sekolah-pengisi` hanya miliknya sendiri (403).
    Rumusan hipotesis tidak pernah ikut di respons ini.
    """
    konf = service.get(konfirmasi_id)
    if GRUP_TIM_KAJIAN in principal.groups:
        return konf
    par = par_service.get_by_subject(principal.subject)
    if par is None or ko_service.untuk_partisipan(par.id).kode != konf.kode_orang:
        raise ForbiddenError("Akses ditolak: konfirmasi ini bukan milik Anda.")
    return konf


@router.patch(
    "/{konfirmasi_id}",
    response_model=KonfirmasiRead,
    summary="Ubah draf konfirmasi milik sendiri (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_update",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "`KONFIRMASI_SUDAH_TERKIRIM`, `CERITA_SUDAH_DIKUNCI`, atau "
                "`DUGAAN_BELUM_DITAMPILKAN`."
            ),
        },
    },
)
def update_konfirmasi(
    konfirmasi_id: str, data: KonfirmasiUpdate, pengisi: PengisiDep, service: ServiceDep
) -> KonfirmasiRead:
    """Ubah parsial draf; `cerita_sebelum` hanya sebelum dikunci, bagian C–E hanya setelah
    dugaan ditampilkan. Riwayat `aksi="update"` dicatat."""
    return service.update(konfirmasi_id, data, kode_orang=pengisi.kode_orang)


@router.post(
    "/{konfirmasi_id}/kunci-cerita",
    response_model=KonfirmasiRead,
    summary="Kunci cerita bebas sebelum dugaan ditampilkan (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_kunci_cerita",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        **_TERKIRIM,
        422: {"model": ErrorResponse, "description": "`cerita_sebelum` kosong/spasi."},
    },
)
def kunci_cerita(konfirmasi_id: str, pengisi: PengisiDep, service: ServiceDep) -> KonfirmasiRead:
    """Isi `cerita_dikunci_pada`; setelahnya `cerita_sebelum` tidak dapat diubah."""
    return service.kunci_cerita(konfirmasi_id, kode_orang=pengisi.kode_orang)


@router.post(
    "/{konfirmasi_id}/tampilkan-dugaan",
    response_model=DugaanRead,
    summary="Tampilkan rumusan dugaan Tim setelah cerita dikunci (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_tampilkan_dugaan",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": "Cerita belum dikunci (`CERITA_BELUM_DIKUNCI`).",
        },
    },
)
def tampilkan_dugaan(konfirmasi_id: str, pengisi: PengisiDep, service: ServiceDep) -> DugaanRead:
    """Kembalikan `rumusan_hipotesis`; panggilan pertama mengisi `dugaan_ditampilkan_pada`."""
    return service.tampilkan_dugaan(konfirmasi_id, kode_orang=pengisi.kode_orang)


@router.post(
    "/{konfirmasi_id}/kirim",
    response_model=KonfirmasiRead,
    summary="Kirim konfirmasi (final, tidak dapat diubah) (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_kirim",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        **_TERKIRIM,
        422: {"model": ErrorResponse, "description": "Field wajib kosong (disebut per field)."},
    },
)
def kirim_konfirmasi(
    konfirmasi_id: str, pengisi: PengisiDep, service: ServiceDep
) -> KonfirmasiRead:
    """Kirim: wajib `peran`, `kesesuaian`, `k1`…`k4`, `indikasi_risiko`.

    Membekukan `masalah.status_awal` (bila belum) dan menandai `masalah.eskalasi_pada`
    bila `indikasi_risiko="Ada indikasi"`. Riwayat `aksi="kirim"` dicatat.
    """
    return service.kirim(konfirmasi_id, kode_orang=pengisi.kode_orang)


@router.get(
    "/{konfirmasi_id}/alur",
    response_model=AlurRead,
    summary="Peta langkah alur sekolah Anda setelah dugaan tampil (sekolah-pengisi)",
    operation_id="redesain_konfirmasi_alur",
    dependencies=READ_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": "Dugaan belum ditampilkan (`DUGAAN_BELUM_DITAMPILKAN`).",
        },
    },
)
def get_alur_konfirmasi(
    konfirmasi_id: str,
    pengisi: PengisiDep,
    service: Annotated[KoreksiService, Depends(get_koreksi_service)],
) -> AlurRead:
    """Proses dengan `masalah_id` dan `sekolah_id` sama dengan konfirmasi, beserta langkahnya.

    Hanya pemilik konfirmasi; proses sekolah lain tidak pernah ikut. Sebelum dugaan
    ditampilkan → 409.
    """
    return service.alur_untuk_konfirmasi(konfirmasi_id, kode_orang=pengisi.kode_orang)
