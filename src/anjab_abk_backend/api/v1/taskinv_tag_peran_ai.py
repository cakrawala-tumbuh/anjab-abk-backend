"""Pengajuan tag peran AI (P03 versi terbatas) atas usulan P02 satu jabatan (khusus `tim-kajian`).

Sumber yang dikirim hanya dua jenis: usulan P02 yang sudah diterima reviewer (`USULAN_AI`,
lewat `AiUsulanService.sumber_dari_usulan`) dan baris mandat formal `ti_uraian_tugas_jabatan`
(`KATALOG_TI`) dari semua jabatan untuk uraian yang dirujuk usulan itu. Tidak ada sumber
penugasan aktual (`assignment_sources`): versi terbatas hanya mengenal mandat formal, dan status
aktual selalu `BELUM_DIKETAHUI`. Hasilnya hanya usulan di `ai_usulan` bersasaran `JABATAN`; rute
ini tidak menulis katalog TI. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.fungsi_p03 import ParameterP03, sumber_mandat_p03, uraian_dirujuk_p02
from ...ai.redaksi import SumberAi
from ...anjab.services.jabatan import JabatanService
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    SessionDep,
    get_ai_usulan_service,
    get_current_principal,
    get_jabatan_service,
    idempotency,
    rate_limit,
    require_tim_kajian,
)
from ...errors import ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...models import (
    JabatanModel,
    TiDetilTugasModel,
    TiTugasPokokModel,
    TiUraianTugasJabatanModel,
    TiUraianTugasModel,
)
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP03
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

KODE_FUNGSI = "P03"
"""Fungsi AI yang diajukan rute ini (tag peran, versi terbatas)."""

KODE_FUNGSI_SUMBER = "P02"
"""Fungsi usulan yang boleh dirangkai menjadi masukan P03."""

MAKS_SUMBER_P03 = 80
"""Jumlah maksimum sumber per pengajuan (satu usulan P02 ditambah baris mandat)."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Jabatan atau usulan tidak ditemukan."}}


class UsulanBukanP02Error(ValidationAppError):
    """422: usulan yang dirujuk bukan usulan P02 bersasaran jabatan ini."""

    error_code = "USULAN_BUKAN_P02"


class SumberTerlaluBanyakError(ValidationAppError):
    """422: usulan ditambah baris mandat melebihi `MAKS_SUMBER_P03`."""

    error_code = "SUMBER_TERLALU_BANYAK"


def _baris_mandat(session: Session, uraian_ids: list[str], batas: int) -> list[SumberAi]:
    """Muat baris mandat formal untuk uraian yang dirujuk, dari semua jabatan pemegangnya.

    Urut `ti_uraian_tugas_jabatan.kode` agar deterministik. Teks tiap sumber hanya memuat
    kode/nama jabatan dan field tugas (kode, unit, tugas pokok, detil tugas, uraian); nilai
    standar dan data orang tidak dibaca. Paling banyak `batas + 1` baris diambil sehingga
    pemanggil bisa mendeteksi kelebihan tanpa memuat seluruh tabel.

    Args:
        session: Sesi basis data.
        uraian_ids: Id `ti_uraian_tugas` yang dirujuk usulan P02; kosong menghasilkan daftar
            kosong tanpa kueri.
        batas: Jumlah baris maksimum yang masih sah.

    Returns:
        Sumber `KATALOG_TI` per baris mandat (bisa lebih dari `batas` satu baris).
    """
    if not uraian_ids:
        return []
    L = TiUraianTugasJabatanModel
    stmt = (
        select(
            L,
            TiUraianTugasModel.uraian,
            TiTugasPokokModel.nama.label("tugas_pokok"),
            TiDetilTugasModel.nama.label("detil_tugas"),
            JabatanModel.kode.label("jabatan_kode"),
            JabatanModel.nama.label("jabatan_nama"),
        )
        .join(TiUraianTugasModel, TiUraianTugasModel.id == L.uraian_tugas_id)
        .outerjoin(TiTugasPokokModel, TiTugasPokokModel.id == L.tugas_pokok_id)
        .outerjoin(TiDetilTugasModel, TiDetilTugasModel.id == L.detil_tugas_id)
        .outerjoin(JabatanModel, JabatanModel.id == L.jabatan_id)
        .where(L.uraian_tugas_id.in_(uraian_ids))
        .order_by(L.kode)
        .limit(batas + 1)
    )
    hasil = []
    for link, uraian, tugas_pokok, detil_tugas, jabatan_kode, jabatan_nama in session.execute(
        stmt
    ).all():
        nilai: dict[str, Any] = {
            "jabatan_kode": jabatan_kode,
            "jabatan_nama": jabatan_nama,
            "kode": link.kode,
            "unit": link.unit,
            "tugas_pokok": tugas_pokok,
            "detil_tugas": detil_tugas,
            "uraian": uraian,
        }
        hasil.append(sumber_mandat_p03(link.uraian_tugas_id, link.jabatan_id, nilai))
    return hasil


@router.post(
    "/jabatan/{jabatan_id}/tag-peran-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta tag peran AI berbasis mandat formal atas usulan P02 (tim-kajian)",
    operation_id="taskinv_jabatan_tag_peran_ai_ajukan",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "feature_disabled; USULAN_BELUM_DITERIMA (usulan P02 tanpa putusan APPROVE/"
                "REVISE); pii_mode_belum_didukung; usulan_berjalan; fungsi_belum_aktif."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Badan tidak sah; USULAN_BUKAN_P02 (fungsi usulan bukan P02 atau sasarannya "
                "bukan jabatan ini); SUMBER_TERLALU_BANYAK (> 80 sumber); kode jabatan di luar "
                "pola parameter AI."
            ),
        },
    },
)
def ajukan_tag_peran_ai(
    jabatan_id: str,
    data: PengajuanP03,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    jabatan_service: Annotated[JabatanService, Depends(get_jabatan_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P03 terbatas; hasilnya hanya usulan tag mandat formal, bukan penugasan.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    jabatan 404, usulan 404, usulan bukan P02 atau bukan milik jabatan ini 422
    `USULAN_BUKAN_P02`, usulan belum diterima 409 `USULAN_BELUM_DITERIMA`, baris mandat untuk
    uraian yang dirujuk `source_ids` usulan, lebih dari 80 sumber 422 `SUMBER_TERLALU_BANYAK`,
    kode jabatan sesuai pola parameter, lalu `AiUsulanService.ajukan` (fungsi belum terdaftar
    409). Sumber hanya `USULAN_AI` (`usulan:<id>`) dan `KATALOG_TI`
    (`uraian:<uraian_id>@<jabatan_id>`); gerbang jenis dan PII gateway berlaku seperti fungsi
    lain. `parameter` hanya `jabatan_kode` dan `periode`.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        jabatan = jabatan_service.get(jabatan_id)
        asal = usulan.get(data.usulan_p02_id)
        if (
            asal.fungsi != KODE_FUNGSI_SUMBER
            or asal.sasaran_jenis != SasaranUsulan.JABATAN
            or asal.sasaran_id != jabatan.id
        ):
            raise UsulanBukanP02Error("Usulan bukan usulan P02 untuk jabatan ini.")
        sumber_usulan = usulan.sumber_dari_usulan(asal.id)
        mandat = _baris_mandat(session, uraian_dirujuk_p02(asal.isi), MAKS_SUMBER_P03 - 1)
        if 1 + len(mandat) > MAKS_SUMBER_P03:
            raise SumberTerlaluBanyakError(
                f"Usulan dan baris mandat melebihi {MAKS_SUMBER_P03} sumber."
            )
        try:
            parameter = ParameterP03(jabatan_kode=jabatan.kode, periode=data.periode).model_dump(
                mode="json"
            )
        except ValidationError as exc:
            raise ValidationAppError("Kode jabatan tidak sesuai pola parameter AI.") from exc
        return usulan.ajukan(
            KODE_FUNGSI,
            SasaranUsulan.JABATAN,
            jabatan.id,
            [sumber_usulan, *mandat],
            parameter,
            principal,
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
