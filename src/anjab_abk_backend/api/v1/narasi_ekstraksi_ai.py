"""Pengajuan ekstraksi AI (P01) atas satu sumber narasi (khusus `tim-kajian`).

Ekstraksi hanya menjadi usulan di `ai_usulan` bersasaran `NARASI_SUMBER`. Rute ini tidak
mengubah `narasi_sumber` dan tidak menulis `narasi_kasus`, `narasi_versi`, `narasi_event`.
Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...ai.fungsi_p01 import ParameterP01
from ...ai.redaksi import SumberAi
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    SessionDep,
    get_ai_usulan_service,
    get_current_principal,
    get_narasi_sumber_service,
    idempotency,
    rate_limit,
    require_tim_kajian,
)
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...narasi.schemas.permintaan_ai import EkstraksiAiCreate
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .narasi_draf_ai import IzinSumberTidakAdaError

router = APIRouter()

KODE_FUNGSI = "P01"
"""Fungsi AI yang diajukan rute ini (ekstraksi fakta dari dokumen sumber)."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Sumber narasi tidak ditemukan."}}


@router.post(
    "/{sumber_id}/ekstraksi-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta ekstraksi fakta AI atas satu sumber (tim-kajian)",
    operation_id="narasi_sumber_ekstraksi_ai_ajukan",
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
        422: {"model": ErrorResponse, "description": "peran_ref atau periode tidak sah."},
    },
)
def ajukan_ekstraksi_ai(
    sumber_id: str,
    data: EkstraksiAiCreate,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P01 atas satu sumber; hasilnya hanya usulan AI, bukan narasi.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan
    `Idempotency-Key` yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum
    membaca apa pun), sumber 404, izin AI sumber, lalu `AiUsulanService.ajukan`. Gerbang
    jenis dan PII berlaku seperti fungsi lain. Tidak ada tabel `narasi_*` yang ditulis.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        sumber = sumber_service.get(sumber_id)
        if not sumber.izin_ai:
            raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {sumber.id}.")
        calon = [
            SumberAi(
                source_id=sumber.id,
                source_hash=sumber.teks_hash,
                jenis=sumber.jenis.value,
                teks=sumber.teks,
            )
        ]
        parameter = ParameterP01(peran_ref=data.peran_ref, periode=data.periode).model_dump(
            mode="json"
        )
        return usulan.ajukan(
            KODE_FUNGSI, SasaranUsulan.NARASI_SUMBER, sumber.id, calon, parameter, principal
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
