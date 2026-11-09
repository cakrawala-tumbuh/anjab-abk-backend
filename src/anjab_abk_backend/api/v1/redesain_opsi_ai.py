"""Pengajuan draf opsi redesain AI (P06) atas satu masalah redesain (khusus `tim-kajian`).

Pengajuan baru sah bila masalah lolos gerbang F4 (`ai/syarat_f4.py`, definisi sementara
`VERSI_SYARAT_F4`): klaim diperkuat, audit bukti minimal, tanpa bukti diperselisihkan. Sumber
dirakit `rakit_sumber_redesain` (dengan konfirmasi terkirim) ditambah tiap alternatif masalah
(`alternatif:<id>`), semuanya berjenis `REDESAIN`; tidak ada kuantitas terverifikasi yang
dikirim. Hasilnya hanya usulan di `ai_usulan` bersasaran `REDESAIN_MASALAH`; rute ini tidak
menulis tabel redesain dan tidak mengisi tab Alternatif. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p06 import ParameterP06
from ...ai.sumber_redesain import rakit_sumber_alternatif, rakit_sumber_redesain
from ...ai.syarat_f4 import periksa_syarat_f4
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
from ...schemas.common import ErrorDetail, ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP06
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

KODE_FUNGSI = "P06"
"""Fungsi AI yang diajukan rute ini (draf opsi redesain)."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Masalah tidak ditemukan."}}


class SyaratF4BelumTerpenuhiError(ConflictError):
    """409: masalah belum lolos gerbang F4; `details[].code` memuat kode syarat yang gagal."""

    error_code = "SYARAT_F4_BELUM_TERPENUHI"


def galat_syarat_f4(alasan: list[str]) -> SyaratF4BelumTerpenuhiError:
    """Bangun galat 409 dengan satu `ErrorDetail` per kode syarat F4 yang gagal.

    Dipakai juga rute P07 (`redesain_kartu_keputusan_ai`). Envelope galat repo hanya mengenal
    `details` berupa daftar, jadi `alasan` gerbang dipetakan
    ke `details[i].loc == ["alasan"]` dengan `details[i].code` = kode syaratnya.

    Args:
        alasan: Kode syarat yang gagal, hasil `periksa_syarat_f4` (tak kosong).

    Returns:
        Galat siap dilempar.
    """
    return SyaratF4BelumTerpenuhiError(
        "Masalah belum memenuhi syarat F4: " + ", ".join(alasan) + ".",
        details=[
            ErrorDetail(
                loc=["alasan"], msg=f"Syarat F4 gagal: {kode}.", type="syarat_f4", code=kode
            )
            for kode in alasan
        ],
    )


@router.post(
    "/{masalah_id}/opsi-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta draf opsi redesain AI untuk satu masalah yang lolos gerbang F4 (tim-kajian)",
    operation_id="redesain_masalah_opsi_ai_ajukan",
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
                "feature_disabled; SYARAT_F4_BELUM_TERPENUHI (details[].code: "
                "KLAIM_BELUM_TERVALIDASI, AUDIT_BUKTI_BELUM_MINIMAL, BUKTI_DIPERSELISIHKAN); "
                "pii_mode_belum_didukung; usulan_berjalan; fungsi_belum_aktif."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "Badan tidak sah; id masalah di luar pola parameter AI.",
        },
    },
)
def ajukan_opsi_ai(
    masalah_id: str,
    data: PengajuanP06,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P06; hasilnya hanya draf opsi, tanpa angka FTE maupun status persetujuan.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    masalah 404, gerbang F4 409 `SYARAT_F4_BELUM_TERPENUHI` (dicek sebelum run atau usulan
    dibuat), rakit sumber redesain (konfirmasi hanya yang terkirim) ditambah alternatif, id
    masalah sesuai pola parameter, lalu `AiUsulanService.ajukan` (fungsi belum terdaftar 409).
    `parameter` hanya `masalah_id`, `periode`, `versi_syarat_f4`, dan
    `source_verified_quantities` (selalu kosong).
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        if session.get(RedesainMasalahModel, masalah_id) is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        alasan = periksa_syarat_f4(session, masalah_id)
        if alasan:
            raise galat_syarat_f4(alasan)
        sumber = [
            *rakit_sumber_redesain(session, masalah_id, sertakan_konfirmasi=True),
            *rakit_sumber_alternatif(session, masalah_id),
        ]
        try:
            parameter = ParameterP06(masalah_id=masalah_id, periode=data.periode).model_dump(
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
