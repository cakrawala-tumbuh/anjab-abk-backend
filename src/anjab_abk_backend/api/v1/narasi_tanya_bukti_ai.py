"""Pengajuan usulan pertanyaan bukti AI (P04) atas satu kasus narasi (khusus `tim-kajian`).

Hasilnya hanya usulan di `ai_usulan`: tidak dikirim ke siapa pun, tidak membuat permintaan
bukti, dan tidak memanggil notifikasi. Rute ini tidak menulis `narasi_*` dan tidak mengubah
status kasus. Hasil dibaca lewat `/api/v1/ai/usulan`; reviewer memutuskan lewat putusan usulan.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...ai.fungsi_p04 import (
    ParameterP04,
    id_sumber_keputusan,
    id_sumber_klaim,
    kode_periode_p04,
)
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
from ...errors import NotFoundError, ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...narasi.schemas.permintaan_ai import TanyaBuktiAiCreate
from ...narasi.services.narasi import NarasiService
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .narasi_draf_ai import IzinSumberTidakAdaError

router = APIRouter()

KODE_FUNGSI = "P04"
"""Fungsi AI yang diajukan rute ini (pengusul pertanyaan bukti)."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."}}


def _sumber_teks(source_id: str, teks: str, jenis: str) -> SumberAi:
    """Bungkus teks bebas klien sebagai sumber agar melewati gerbang PII."""
    return SumberAi(
        source_id=source_id,
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=jenis,
        teks=teks,
    )


@router.post(
    "/{narasi_id}/tanya-bukti-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta usulan satu pertanyaan bukti AI (tim-kajian, tanpa pengiriman)",
    operation_id="narasi_kasus_tanya_bukti_ai_ajukan",
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
            "description": "Badan tidak sah atau sumber tak dikenal.",
        },
    },
)
def ajukan_tanya_bukti_ai(
    narasi_id: str,
    data: TanyaBuktiAiCreate,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P04 atas satu kasus; hasilnya hanya usulan AI yang tidak terkirim ke siapa pun.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan
    `Idempotency-Key` yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum
    membaca apa pun), kasus 404, sumber (tak dikenal 422, tanpa izin AI 409), lalu
    `AiUsulanService.ajukan`. `klaim` dan `keputusan_terkait` dikirim sebagai sumber
    `klaim:<uuid>` dan `keputusan:<uuid>` (jenis = jenis sumber pertama) agar ikut gerbang PII;
    keduanya tidak masuk `parameter`. Tidak ada tabel `narasi_*` yang ditulis dan tidak ada
    notifikasi.
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        kasus = service.get_kasus(narasi_id)
        sumber = []
        for sid in dict.fromkeys(data.sumber_ids):
            try:
                sumber.append(sumber_service.get(sid))
            except NotFoundError as exc:
                raise ValidationAppError(f"Sumber '{sid}' tidak ditemukan.") from exc
        tanpa_izin = [s.id for s in sumber if not s.izin_ai]
        if tanpa_izin:
            daftar = ", ".join(tanpa_izin[:5]) + ("..." if len(tanpa_izin) > 5 else "")
            raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {daftar}.")
        jenis = sumber[0].jenis.value
        calon = [
            SumberAi(source_id=s.id, source_hash=s.teks_hash, jenis=s.jenis.value, teks=s.teks)
            for s in sumber
        ]
        calon.append(_sumber_teks(id_sumber_klaim(data.klaim), data.klaim, jenis))
        calon.append(
            _sumber_teks(id_sumber_keputusan(data.keputusan_terkait), data.keputusan_terkait, jenis)
        )
        parameter = ParameterP04(
            narasi_id=kasus.id, periode=kode_periode_p04(kasus.periode)
        ).model_dump(mode="json")
        return usulan.ajukan(
            KODE_FUNGSI, SasaranUsulan.NARASI_KASUS, kasus.id, calon, parameter, principal
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
