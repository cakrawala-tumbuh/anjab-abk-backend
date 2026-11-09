"""Pengajuan normalisasi tugas AI (P02) atas katalog satu jabatan (khusus `tim-kajian`).

Baris `ti_uraian_tugas_jabatan` milik jabatan (opsional dipersempit `unit`) dikirim sebagai sumber
`KATALOG_TI`; hasilnya hanya usulan di `ai_usulan` bersasaran `JABATAN`. Rute ini tidak menulis
katalog TI maupun `narasi_*`. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.fungsi_p02 import ParameterP02, sumber_katalog_ti
from ...ai.redaksi import SumberAi
from ...anjab.services.jabatan import JabatanService
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    SessionDep,
    get_ai_usulan_service,
    get_current_principal,
    get_jabatan_service,
    get_narasi_sumber_service,
    idempotency,
    rate_limit,
    require_tim_kajian,
)
from ...errors import ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...models import (
    TiDetilTugasModel,
    TiTugasPokokModel,
    TiUraianTugasJabatanModel,
    TiUraianTugasModel,
)
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP02
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .narasi_draf_ai import IzinSumberTidakAdaError

router = APIRouter()

KODE_FUNGSI = "P02"
"""Fungsi AI yang diajukan rute ini (normalisasi tugas)."""

MAKS_URAIAN_P02 = 80
"""Jumlah maksimum baris katalog per pengajuan; lebih dari ini persempit dengan `unit`."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {
    404: {"model": ErrorResponse, "description": "Jabatan atau sumber dokumen tidak ditemukan."}
}


class TanpaUraianError(ValidationAppError):
    """422: jabatan (dan `unit`) tidak punya satu pun baris katalog."""

    error_code = "TANPA_URAIAN"


class UraianTerlaluBanyakError(ValidationAppError):
    """422: baris katalog melebihi `MAKS_URAIAN_P02`; persempit dengan `unit`."""

    error_code = "URAIAN_TERLALU_BANYAK"


def _baris_katalog(session: Session, jabatan_id: str, unit: str | None) -> list[SumberAi]:
    """Muat baris katalog jabatan sebagai sumber `KATALOG_TI`, urut `urutan` lalu `kode`.

    Hanya field tugas (kode, unit, tugas pokok, detil tugas, uraian) dan nilai standar yang
    dibaca; kolom lain tidak ikut terkirim.

    Args:
        session: Sesi basis data.
        jabatan_id: Id jabatan.
        unit: Kode unit penyempit, atau `None`.

    Returns:
        Sumber per baris; daftar kosong bila tidak ada baris.

    Raises:
        UraianTerlaluBanyakError: lebih dari `MAKS_URAIAN_P02` baris (422).
    """
    L = TiUraianTugasJabatanModel
    stmt = (
        select(
            L,
            TiUraianTugasModel.uraian,
            TiTugasPokokModel.nama.label("tugas_pokok"),
            TiDetilTugasModel.nama.label("detil_tugas"),
        )
        .join(TiUraianTugasModel, TiUraianTugasModel.id == L.uraian_tugas_id)
        .outerjoin(TiTugasPokokModel, TiTugasPokokModel.id == L.tugas_pokok_id)
        .outerjoin(TiDetilTugasModel, TiDetilTugasModel.id == L.detil_tugas_id)
        .where(L.jabatan_id == jabatan_id)
        .order_by(L.urutan, L.kode)
        .limit(MAKS_URAIAN_P02 + 1)
    )
    if unit is not None:
        stmt = stmt.where(L.unit == unit)
    rows = session.execute(stmt).all()
    if len(rows) > MAKS_URAIAN_P02:
        raise UraianTerlaluBanyakError(
            f"Katalog jabatan memuat lebih dari {MAKS_URAIAN_P02} uraian; persempit dengan unit."
        )
    hasil = []
    for link, uraian, tugas_pokok, detil_tugas in rows:
        nilai: dict[str, Any] = {
            "kode": link.kode,
            "unit": link.unit,
            "tugas_pokok": tugas_pokok,
            "detil_tugas": detil_tugas,
            "uraian": uraian,
            "std_sumber_bukti": link.std_sumber_bukti,
            "std_kondisi": link.std_kondisi,
            "std_frekuensi_teks": link.std_frekuensi_teks,
            "std_durasi_per_kali": link.std_durasi_per_kali,
            "std_jam_per_minggu": link.std_jam_per_minggu,
            "std_peak4w_hours": link.std_peak4w_hours,
            "std_va_type": link.std_va_type,
            "std_opm_importance": link.std_opm_importance,
            "std_opm_frequency": link.std_opm_frequency,
            "std_opm_criticality": link.std_opm_criticality,
        }
        hasil.append(sumber_katalog_ti(link.uraian_tugas_id, nilai))
    return hasil


@router.post(
    "/jabatan/{jabatan_id}/normalisasi-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta normalisasi tugas AI atas katalog satu jabatan (tim-kajian)",
    operation_id="taskinv_jabatan_normalisasi_ai_ajukan",
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
                "feature_disabled; izin_sumber_tidak_ada; pii_mode_belum_didukung; "
                "usulan_berjalan; fungsi_belum_aktif."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Badan tidak sah; TANPA_URAIAN (0 baris katalog); URAIAN_TERLALU_BANYAK "
                "(> 80 baris, persempit dengan unit); kode jabatan di luar pola parameter AI."
            ),
        },
    },
)
def ajukan_normalisasi_ai(
    jabatan_id: str,
    data: PengajuanP02,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    jabatan_service: Annotated[JabatanService, Depends(get_jabatan_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P02 atas katalog satu jabatan; hasilnya hanya usulan AI, bukan perubahan katalog.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    jabatan 404, sumber dokumen (tak ada 404, tanpa izin AI 409), baris katalog (0 -> 422
    `TANPA_URAIAN`, > 80 -> 422 `URAIAN_TERLALU_BANYAK`), kode jabatan sesuai pola parameter,
    lalu `AiUsulanService.ajukan`. Baris katalog dikirim sebagai sumber `KATALOG_TI`
    (`uraian:<id>`), dokumen dengan jenisnya sendiri; gerbang jenis dan PII gateway berlaku
    seperti fungsi lain. `parameter` hanya `jabatan_kode`, `unit`, `periode`.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        jabatan = jabatan_service.get(jabatan_id)
        dokumen = [sumber_service.get(sid) for sid in dict.fromkeys(data.sumber_dokumen_ids)]
        tanpa_izin = [d.id for d in dokumen if not d.izin_ai]
        if tanpa_izin:
            raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {', '.join(tanpa_izin)}.")
        katalog = _baris_katalog(session, jabatan.id, data.unit)
        if not katalog:
            raise TanpaUraianError("Jabatan tidak punya uraian tugas pada katalog.")
        try:
            parameter = ParameterP02(
                jabatan_kode=jabatan.kode, unit=data.unit, periode=data.periode
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationAppError("Kode jabatan tidak sesuai pola parameter AI.") from exc
        calon = katalog + [
            SumberAi(source_id=d.id, source_hash=d.teks_hash, jenis=d.jenis.value, teks=d.teks)
            for d in dokumen
        ]
        return usulan.ajukan(
            KODE_FUNGSI, SasaranUsulan.JABATAN, jabatan.id, calon, parameter, principal
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
