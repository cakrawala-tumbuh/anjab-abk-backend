"""Pengajuan kartu keputusan AI (P07) atas satu masalah redesain (khusus `tim-kajian`).

Pengajuan baru sah bila masalah lolos gerbang F4 dan punya minimal satu alternatif tercatat
(`periksa_syarat_p07`, MX:12). Status otorisasi (`authorization_state`) dibaca server dari
`redesain_alternatif` dan `redesain_penilaian.prioritas_final` lalu disimpan di
`ai_usulan.konteks_server`; model hanya menerima salinannya sebagai sumber `otorisasi:<id>` dan
skema keluarannya tidak punya kunci itu. Sumber lain: `rakit_sumber_redesain` (konfirmasi
terkirim), `rakit_sumber_alternatif`, dan opsional usulan P06 yang sudah diterima reviewer
(`USULAN_AI`). Hasilnya hanya usulan bersasaran `REDESAIN_MASALAH` untuk Tim; rute Yayasan
(`/redesain/yayasan`, `/redesain/ekspor`) tidak membaca `ai_usulan`. Rute ini tidak mengubah
`status_telaah` maupun `keputusan`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p07 import ParameterP07
from ...ai.otorisasi_redesain import bangun_authorization_state, sumber_otorisasi
from ...ai.sumber_redesain import (
    rakit_sumber_alternatif,
    rakit_sumber_kesiapan,
    rakit_sumber_redesain,
)
from ...ai.syarat_f4 import periksa_syarat_p07
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
from ...errors import NotFoundError, ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...models import RedesainMasalahModel
from ...schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ...schemas.common import ErrorResponse, FiturKode
from ...schemas.pengajuan_ai import PengajuanP07
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent
from .redesain_opsi_ai import galat_syarat_f4

router = APIRouter()

KODE_FUNGSI = "P07"
"""Fungsi AI yang diajukan rute ini (kartu keputusan)."""

KODE_FUNGSI_SUMBER = "P06"
"""Fungsi usulan yang boleh dirangkai lewat `usulan_p06_id`."""

_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Masalah atau usulan tidak ditemukan."}}


class UsulanBukanP06Error(ValidationAppError):
    """422: usulan yang dirujuk bukan usulan P06 bersasaran masalah ini."""

    error_code = "USULAN_BUKAN_P06"


@router.post(
    "/{masalah_id}/kartu-keputusan-ai",
    response_model=AiUsulanRingkas,
    status_code=202,
    summary="Minta kartu keputusan AI untuk satu masalah yang lolos gerbang F4 (tim-kajian)",
    operation_id="redesain_masalah_kartu_keputusan_ai_ajukan",
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
                "KLAIM_BELUM_TERVALIDASI, AUDIT_BUKTI_BELUM_MINIMAL, BUKTI_DIPERSELISIHKAN, "
                "ALTERNATIF_BELUM_ADA); USULAN_BELUM_DITERIMA (usulan P06 tanpa putusan "
                "APPROVE/REVISE); pii_mode_belum_didukung; usulan_berjalan; fungsi_belum_aktif."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Badan tidak sah; USULAN_BUKAN_P06 (fungsi usulan bukan P06 atau sasarannya "
                "masalah lain); id masalah di luar pola parameter AI."
            ),
        },
    },
)
def ajukan_kartu_keputusan_ai(
    masalah_id: str,
    data: PengajuanP07,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    usulan: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanRingkas:
    """Ajukan P07; status otorisasi pada usulan selalu cuplikan server, bukan keluaran model.

    Seluruh pemeriksaan berada di dalam aksi idempoten, jadi ulangan dengan `Idempotency-Key`
    yang sama membalas respons tersimpan (200). Urutan: flag AI (sebelum membaca apa pun),
    masalah 404, bila `usulan_p06_id` diisi: usulan 404 lalu bukan P06 atau bukan milik masalah
    ini 422 `USULAN_BUKAN_P06`; gerbang F4 + alternatif 409 `SYARAT_F4_BELUM_TERPENUHI`
    (sebelum run atau usulan dibuat); usulan P06 belum diterima 409 `USULAN_BELUM_DITERIMA`;
    rakit sumber redesain, alternatif, `otorisasi:<masalah_id>`, dan usulan P06; id masalah
    sesuai pola parameter; lalu `AiUsulanService.ajukan` dengan
    `konteks_server={"authorization_state": ...}` (fungsi belum terdaftar 409).
    """

    def _aksi() -> AiUsulanRingkas:
        if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        if session.get(RedesainMasalahModel, masalah_id) is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        if data.usulan_p06_id is not None:
            asal = usulan.get(data.usulan_p06_id)
            if (
                asal.fungsi != KODE_FUNGSI_SUMBER
                or asal.sasaran_jenis != SasaranUsulan.REDESAIN_MASALAH
                or asal.sasaran_id != masalah_id
            ):
                raise UsulanBukanP06Error("Usulan bukan usulan P06 untuk masalah ini.")
        alasan = periksa_syarat_p07(session, masalah_id)
        if alasan:
            raise galat_syarat_f4(alasan)
        sumber_usulan = (
            [usulan.sumber_dari_usulan(data.usulan_p06_id)] if data.usulan_p06_id else []
        )
        state = bangun_authorization_state(session, masalah_id, data.periode)
        sumber = [
            *rakit_sumber_redesain(session, masalah_id, sertakan_konfirmasi=True),
            *rakit_sumber_alternatif(session, masalah_id),
            *rakit_sumber_kesiapan(session, masalah_id, data.periode),
            sumber_otorisasi(masalah_id, state),
            *sumber_usulan,
        ]
        try:
            parameter = ParameterP07(
                masalah_id=masalah_id, periode=data.periode, usulan_p06_id=data.usulan_p06_id
            ).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationAppError("Id masalah tidak sesuai pola parameter AI.") from exc
        return usulan.ajukan(
            KODE_FUNGSI,
            SasaranUsulan.REDESAIN_MASALAH,
            masalah_id,
            sumber,
            parameter,
            principal,
            konteks_server={"authorization_state": state},
        )

    return run_idempotent(idem, response, AiUsulanRingkas, _aksi)
