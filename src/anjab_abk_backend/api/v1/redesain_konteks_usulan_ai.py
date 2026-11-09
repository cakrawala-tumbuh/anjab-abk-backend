"""Pengajuan usulan kandidat konteks redesain oleh AI (P11 Pengusul Konteks, khusus `tim-kajian`).

Sumber dirakit `rakit_sumber_konteks` (jenis `REDESAIN`): setiap konteks aktif (`konteks:<id>`)
dan, bila diminta, setiap masalah yang konteksnya aktif (`masalah:<id>`, tanpa sekolah maupun
kode orang). Dokumen `narasi_sumber` pendukung ikut dengan jenisnya sendiri. Hasilnya hanya usulan
di `ai_usulan` bersasaran `REDESAIN_KONTEKS` dengan `sasaran_id` `KATALOG`; rute ini tidak
menulis `redesain_konteks`. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p11 import SASARAN_KATALOG_KONTEKS, ParameterP11
from ...ai.redaksi import SumberAi
from ...ai.sumber_konteks import rakit_sumber_konteks
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
from ...errors import ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP11
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .narasi_draf_ai import IzinSumberTidakAdaError

router = APIRouter()

KODE_FUNGSI = "P11"
"""Fungsi AI yang diajukan rute ini (pengusul konteks)."""

MAKS_SUMBER_P11 = 60
"""Jumlah maksimum sumber redesain terakit (konteks + masalah) per pengajuan."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Sumber dokumen tidak ditemukan."}}


class TanpaKonteksError(ValidationAppError):
    """422: tidak ada satu pun konteks redesain aktif untuk dijadikan sumber."""

    error_code = "TANPA_KONTEKS"


class SumberTerlaluBanyakError(ValidationAppError):
    """422: sumber redesain terakit melebihi `MAKS_SUMBER_P11`."""

    error_code = "SUMBER_TERLALU_BANYAK"


@router.post(
    "/usulan-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta usulan kandidat konteks redesain dari AI (tim-kajian)",
    operation_id="redesain_konteks_usulan_ai_ajukan",
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
                "Badan tidak sah; TANPA_KONTEKS (0 konteks aktif); SUMBER_TERLALU_BANYAK "
                "(> 60 sumber redesain terakit); kode konteks di luar pola parameter AI."
            ),
        },
    },
)
def ajukan_usulan_konteks_ai(
    data: PengajuanP11,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P11; hasilnya hanya kandidat konteks di `ai_usulan`, bukan konteks baru.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    sumber dokumen (tak ada 404, tanpa izin AI 409 `izin_sumber_tidak_ada`), rakit sumber
    konteks aktif (0 konteks 422 `TANPA_KONTEKS`, lebih dari 60 sumber redesain 422
    `SUMBER_TERLALU_BANYAK`), lalu `AiUsulanService.ajukan` (fungsi belum terdaftar 409
    `fungsi_belum_aktif`). Sumber redesain berjenis `REDESAIN`, dokumen dengan jenisnya sendiri;
    gerbang jenis dan PII gateway berlaku seperti fungsi lain. `parameter` hanya
    `jumlah_kandidat`, `sertakan_masalah`, dan `kode_konteks_ada`; dua yang terakhir disimpan
    juga di `ai_usulan.konteks_server` sebagai batas pemeriksaan `aturan_p11`.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        dokumen = [sumber_service.get(sid) for sid in dict.fromkeys(data.sumber_dokumen_ids)]
        tanpa_izin = [d.id for d in dokumen if not d.izin_ai]
        if tanpa_izin:
            raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {', '.join(tanpa_izin)}.")
        rakitan = rakit_sumber_konteks(session, sertakan_masalah=data.sertakan_masalah)
        if not rakitan.kode_konteks:
            raise TanpaKonteksError("Tidak ada konteks redesain aktif.")
        if len(rakitan.sumber) > MAKS_SUMBER_P11:
            raise SumberTerlaluBanyakError(f"Sumber redesain terakit melebihi {MAKS_SUMBER_P11}.")
        try:
            parameter = ParameterP11(
                jumlah_kandidat=data.jumlah_kandidat,
                sertakan_masalah=data.sertakan_masalah,
                kode_konteks_ada=rakitan.kode_konteks,
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationAppError("Kode konteks tidak sesuai pola parameter AI.") from exc
        calon = rakitan.sumber + [
            SumberAi(source_id=d.id, source_hash=d.teks_hash, jenis=d.jenis.value, teks=d.teks)
            for d in dokumen
        ]
        return usulan.ajukan(
            KODE_FUNGSI,
            SasaranUsulan.REDESAIN_KONTEKS,
            SASARAN_KATALOG_KONTEKS,
            calon,
            parameter,
            principal,
            konteks_server={
                "jumlah_kandidat": parameter["jumlah_kandidat"],
                "kode_konteks_ada": parameter["kode_konteks_ada"],
            },
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
