"""Pengajuan hipotesis proses AI (P05) atas satu masalah redesain (khusus `tim-kajian`).

Sumber dirakit `rakit_sumber_redesain` (jenis `REDESAIN`): masalah, proses, langkah, bukti,
koreksi, dan konfirmasi sekolah yang sudah terkirim (tanpa `cerita_sebelum`). Pengajuan baru sah
sesudah sumber proses terhubung (MX:10): masalah punya minimal satu proses dengan minimal satu
langkah. Hasilnya hanya usulan di `ai_usulan` bersasaran `REDESAIN_MASALAH`; rute ini tidak
menulis tabel redesain. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p05 import ParameterP05
from ...ai.sumber_redesain import proses_terhubung, rakit_sumber_redesain
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    SessionDep,
    get_ai_usulan_service,
    get_current_principal,
    idempotency,
    rate_limit,
    require_tim_kajian,
)
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...models import RedesainMasalahModel
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP05
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

KODE_FUNGSI = "P05"
"""Fungsi AI yang diajukan rute ini (hipotesis proses dan masalah)."""

MAKS_SUMBER_P05 = 60
"""Jumlah maksimum sumber terakit per pengajuan."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Masalah tidak ditemukan."}}


class SumberProsesBelumTerhubungError(ConflictError):
    """409: masalah belum punya proses dengan minimal satu langkah (MX:10)."""

    error_code = "SUMBER_PROSES_BELUM_TERHUBUNG"


class SumberTerlaluBanyakError(ValidationAppError):
    """422: sumber terakit melebihi `MAKS_SUMBER_P05`."""

    error_code = "SUMBER_TERLALU_BANYAK"


@router.post(
    "/{masalah_id}/hipotesis-proses-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta hipotesis proses dan masalah AI untuk satu masalah redesain (tim-kajian)",
    operation_id="redesain_masalah_hipotesis_proses_ai_ajukan",
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
                "feature_disabled; SUMBER_PROSES_BELUM_TERHUBUNG (belum ada proses dengan "
                "langkah); pii_mode_belum_didukung; usulan_berjalan; fungsi_belum_aktif."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Badan tidak sah; SUMBER_TERLALU_BANYAK (> 60 sumber terakit); id masalah di "
                "luar pola parameter AI."
            ),
        },
    },
)
def ajukan_hipotesis_proses_ai(
    masalah_id: str,
    data: PengajuanP05,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P05; hasilnya hanya usulan hipotesis, bukan akar penyebab terbukti.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    masalah 404, belum ada proses berlangkah 409 `SUMBER_PROSES_BELUM_TERHUBUNG`, rakit sumber
    (konfirmasi hanya yang terkirim), lebih dari 60 sumber 422 `SUMBER_TERLALU_BANYAK`, id
    masalah sesuai pola parameter, lalu `AiUsulanService.ajukan` (fungsi belum terdaftar 409).
    Semua sumber berjenis `REDESAIN`; gerbang jenis dan PII gateway berlaku seperti fungsi lain.
    `parameter` hanya `masalah_id` dan `periode`.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        if session.get(RedesainMasalahModel, masalah_id) is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        if not proses_terhubung(session, masalah_id):
            raise SumberProsesBelumTerhubungError(
                "Masalah belum punya proses dengan minimal satu langkah."
            )
        sumber = rakit_sumber_redesain(session, masalah_id, sertakan_konfirmasi=True)
        if len(sumber) > MAKS_SUMBER_P05:
            raise SumberTerlaluBanyakError(f"Sumber terakit melebihi {MAKS_SUMBER_P05}.")
        try:
            parameter = ParameterP05(masalah_id=masalah_id, periode=data.periode).model_dump(
                mode="json"
            )
        except ValidationError as exc:
            raise ValidationAppError("Id masalah tidak sesuai pola parameter AI.") from exc
        return usulan.ajukan(
            KODE_FUNGSI,
            SasaranUsulan.REDESAIN_MASALAH,
            masalah_id,
            sumber,
            parameter,
            principal,
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
