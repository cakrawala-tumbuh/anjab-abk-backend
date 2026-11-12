"""Pengajuan sintesis bukti riset AI (P08) atas satu protokol riset (khusus `tim-kajian`).

Pengajuan baru sah untuk protokol `TERKUNCI` yang punya minimal satu statistik `TERVERIFIKASI`.
Sumber dirakit `rakit_sumber_riset` (jenis `RISET`): protokol, statistik terverifikasi, kasus
negatif, dan log versi metode; statistik `DRAF` tidak pernah dikirim. Hasilnya hanya usulan di
`ai_usulan` bersasaran `PROTOKOL_RISET`; rute ini tidak menulis tabel riset. Hasil dibaca lewat
`/api/v1/ai/usulan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p08 import ParameterP08
from ...ai.gateway import FUNGSI_TERDAFTAR
from ...ai.sumber_riset import jumlah_statistik_terverifikasi, rakit_sumber_riset
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
from ...models import RisetProtokolModel
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP08
from ...schemas.riset_protokol import StatusProtokol
from ...security import Principal
from ...services.ai_usulan import AiUsulanService, FungsiAiBelumAktifError
from ...services.riset_signoff_sql import signoff_ada
from ...services.riset_statistik import ProtokolBelumTerkunciError
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

KODE_FUNGSI = "P08"
"""Fungsi AI yang diajukan rute ini (sintesis bukti riset)."""

MAKS_SUMBER_P08 = 60
"""Jumlah maksimum sumber terakit per pengajuan."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Protokol riset tidak ditemukan."}}


class SignoffPiEtikTakAdaError(ConflictError):
    """409: protokol terkunci belum punya bukti sign-off PI/etik (`SIGNOFF_PI_ETIK_TAK_ADA`)."""

    error_code = "SIGNOFF_PI_ETIK_TAK_ADA"


class StatistikTerverifikasiKosongError(ConflictError):
    """409: protokol belum punya satu pun statistik `TERVERIFIKASI`."""

    error_code = "STATISTIK_TERVERIFIKASI_KOSONG"


class SumberTerlaluBanyakError(ValidationAppError):
    """422: sumber terakit melebihi `MAKS_SUMBER_P08`."""

    error_code = "SUMBER_TERLALU_BANYAK"


@router.post(
    "/protokol/{protokol_id}/sintesis-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta sintesis bukti riset AI untuk satu protokol terkunci (tim-kajian)",
    operation_id="riset_protokol_sintesis_ai_ajukan",
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
                "feature_disabled; fungsi_belum_aktif; PROTOKOL_BELUM_TERKUNCI; "
                "SIGNOFF_PI_ETIK_TAK_ADA; "
                "STATISTIK_TERVERIFIKASI_KOSONG; pii_mode_belum_didukung; usulan_berjalan."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Badan tidak sah; SUMBER_TERLALU_BANYAK (> 60 sumber terakit); kode protokol "
                "di luar pola parameter AI."
            ),
        },
    },
)
def ajukan_sintesis_ai(
    protokol_id: str,
    data: PengajuanP08,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P08; hasilnya draf sintesis yang tiap klaim hasilnya menunjuk statistik terverifikasi.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan (semuanya sebelum run atau usulan dibuat):
    flag AI, protokol 404, fungsi belum terdaftar 409 `fungsi_belum_aktif`, protokol `DRAF` 409
    `PROTOKOL_BELUM_TERKUNCI`, tanpa sign-off PI/etik 409
    `SIGNOFF_PI_ETIK_TAK_ADA`, nol statistik terverifikasi 409 `STATISTIK_TERVERIFIKASI_KOSONG`,
    lebih dari 60 sumber 422 `SUMBER_TERLALU_BANYAK`, lalu `AiUsulanService.ajukan`. `parameter`
    hanya `protokol_kode`, `protokol_versi`, dan `periode`.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        protokol = session.get(RisetProtokolModel, protokol_id)
        if protokol is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        if KODE_FUNGSI not in FUNGSI_TERDAFTAR:
            raise FungsiAiBelumAktifError(f"Fungsi AI {KODE_FUNGSI} belum diaktifkan.")
        if protokol.status != StatusProtokol.TERKUNCI.value:
            raise ProtokolBelumTerkunciError(
                "Sintesis hanya untuk protokol berstatus TERKUNCI; kunci protokol lebih dulu."
            )
        if not signoff_ada(session, protokol_id):
            raise SignoffPiEtikTakAdaError(
                "Protokol belum punya bukti sign-off PI/etik; catat lewat .../sign-off."
            )
        if jumlah_statistik_terverifikasi(session, protokol_id) == 0:
            raise StatistikTerverifikasiKosongError(
                "Protokol belum punya statistik berstatus TERVERIFIKASI."
            )
        sumber = rakit_sumber_riset(session, protokol)
        if len(sumber) > MAKS_SUMBER_P08:
            raise SumberTerlaluBanyakError(f"Sumber terakit melebihi {MAKS_SUMBER_P08}.")
        try:
            parameter = ParameterP08(
                protokol_kode=protokol.kode,
                protokol_versi=protokol.versi,
                periode=data.periode,
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationAppError("Kode protokol tidak sesuai pola parameter AI.") from exc
        return usulan.ajukan(
            KODE_FUNGSI,
            SasaranUsulan.PROTOKOL_RISET,
            protokol_id,
            sumber,
            parameter,
            principal,
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
