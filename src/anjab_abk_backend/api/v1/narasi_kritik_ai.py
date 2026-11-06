"""Pengajuan kritik AI (P09) atas satu versi narasi (khusus `tim-kajian`).

Kritik hanya menjadi usulan di `ai_usulan`: bukan bukti, bukan tinjauan, bukan persetujuan.
Rute ini tidak menulis `narasi_versi`, `narasi_versi_sumber`, `narasi_event`, maupun
`narasi_ai_permintaan`, dan tidak mengubah status kasus. Hasil dibaca lewat `/api/v1/ai/usulan`.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...ai.fungsi_p09 import ParameterP09, id_sumber_versi
from ...ai.redaksi import SumberAi
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    SessionDep,
    get_ai_usulan_service,
    get_current_principal,
    get_narasi_service,
    get_narasi_sumber_service,
    idempotency,
    rate_limit,
    require_tim_kajian,
)
from ...errors import ConflictError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...narasi.schemas.permintaan_ai import KritikAiCreate
from ...narasi.services.narasi import NarasiService, NarasiTanpaTeksError, VersiBasiError
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .narasi_draf_ai import IzinSumberTidakAdaError

router = APIRouter()

KODE_FUNGSI = "P09"
"""Fungsi AI yang diajukan rute ini (kritik AI atas versi narasi)."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."}}


class KritikTanpaSumberError(ConflictError):
    """409: versi yang dikritik tidak menautkan sumber apa pun."""

    error_code = "kritik_tanpa_sumber"


@router.post(
    "/{narasi_id}/kritik-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta kritik AI atas versi narasi (tim-kajian)",
    operation_id="narasi_kasus_kritik_ai_ajukan",
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
                "feature_disabled; versi_basi; narasi_tanpa_teks; kritik_tanpa_sumber; "
                "izin_sumber_tidak_ada; pii_mode_belum_didukung; usulan_berjalan; "
                "fungsi_belum_aktif."
            ),
        },
        422: {"model": ErrorResponse, "description": "narasi_versi_id tidak sah."},
    },
)
def ajukan_kritik_ai(
    narasi_id: str,
    data: KritikAiCreate,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P09 atas satu versi; hasilnya hanya usulan AI, bukan bukti atau tinjauan.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan
    `Idempotency-Key` yang sama membalas respons tersimpan (200), bukan `versi_basi`
    atau `usulan_berjalan`. Urutan: flag AI (sebelum membaca apa pun), kasus 404, versi
    terbaru, versi bertulis teks, versi bersumber, sumber berizin AI, lalu
    `AiUsulanService.ajukan`. Draf dikirim sebagai sumber `versi:<id>` agar ikut gerbang
    PII; tidak ada tabel `narasi_*` yang ditulis.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        service.get_kasus(narasi_id)
        terbaru = service.versi_terbaru(narasi_id)
        if terbaru is None or terbaru.id != data.narasi_versi_id:
            raise VersiBasiError("Versi yang dikritik bukan versi terbaru kasus.")
        if terbaru.teks is None or not terbaru.teks.strip():
            raise NarasiTanpaTeksError("Versi tanpa teks tidak dapat dikritik.")
        sumber_ids = list(dict.fromkeys(t.sumber_id for t in service.sumber_versi(terbaru.id)))
        if not sumber_ids:
            raise KritikTanpaSumberError("Versi ini tidak menautkan sumber apa pun.")
        sumber = [sumber_service.get(sid) for sid in sumber_ids]
        tanpa_izin = [s.id for s in sumber if not s.izin_ai]
        if tanpa_izin:
            daftar = ", ".join(tanpa_izin[:5]) + ("..." if len(tanpa_izin) > 5 else "")
            raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {daftar}.")
        calon = [
            SumberAi(source_id=s.id, source_hash=s.teks_hash, jenis=s.jenis.value, teks=s.teks)
            for s in sumber
        ]
        calon.append(
            SumberAi(
                source_id=id_sumber_versi(terbaru.id),
                source_hash=hashlib.sha256(terbaru.teks.encode("utf-8")).hexdigest(),
                jenis=sumber[0].jenis.value,
                teks=terbaru.teks,
            )
        )
        parameter = ParameterP09(narasi_versi_id=terbaru.id).model_dump(mode="json")
        return usulan.ajukan(
            KODE_FUNGSI, SasaranUsulan.NARASI_KASUS, narasi_id, calon, parameter, principal
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
