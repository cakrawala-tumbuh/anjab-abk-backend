"""Endpoint analisis dan hasil DCS."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from ...dcs.schemas.hasil import DcsHasilRespondenRead, DcsHasilSesiRead
from ...dcs.services.analisis import compute_hasil_responden, compute_hasil_sesi
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.sesi import DcsSesiService
from ...dependencies import (
    get_current_principal,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_dcs_sesi_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...wcp.seed import DIMENSI
from ...wcp.services.analisis import compute_hasil_responden as wcp_compute_responden
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi DCS tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}

# Kode dimensi risiko WCP (is_risk=True): CH, SD, PI
_WCP_RISK_KODES = frozenset(kode for kode, _, _, is_risk in DIMENSI if is_risk)


def _compute_wcp_risk_score(
    wcp_sesi_id: str,
    wcp_rsp_service: WcpRespondenService,
    wcp_jwb_service: WcpJawabanService,
) -> float:
    """Hitung skor risiko WCP ternormalisasi (0–1) dari rata-rata dimensi risiko (CH/SD/PI)."""
    submitted = [r for r in wcp_rsp_service.list_by_sesi(wcp_sesi_id) if r.sudah_submit]
    if not submitted:
        return 0.0

    risk_scores: list[float] = []
    for rsp in submitted:
        raw = wcp_jwb_service.get_raw_by_responden(rsp.id)
        hasil = wcp_compute_responden(rsp.id, raw)
        for dim in hasil.dimensi:
            if dim.dimensi_kode in _WCP_RISK_KODES:
                # Dimensi risiko: skor tinggi = risiko tinggi; normalisasi ke 0–1
                risk_scores.append((dim.skor - 1.0) / 4.0)

    return round(sum(risk_scores) / len(risk_scores), 4) if risk_scores else 0.0


@router.post(
    "/{sesi_id}/analisis",
    response_model=DcsHasilSesiRead,
    summary="Jalankan analisis DCS (CLOSED → ANALYZED)",
    operation_id="dcs_analisis_run",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_SESI},
)
def run_analisis(
    sesi_id: Annotated[str, Path(description="ID sesi DCS.")],
    sesi_service: Annotated[DcsSesiService, Depends(get_dcs_sesi_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    wcp_rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    wcp_jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    wcp_sesi_id: Annotated[
        str | None,
        Query(
            description=(
                "ID sesi WCP yang bersesuaian untuk menghitung K-Index. "
                "Jika tidak disertakan, k_index akan bernilai null."
            )
        ),
    ] = None,
) -> DcsHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Analisis hanya dapat dijalankan saat sesi berstatus CLOSED atau ANALYZED"
            f" (saat ini: {sesi.status})."
        )

    responden_list = rsp_service.list_by_sesi(sesi_id)
    submitted = [r for r in responden_list if r.sudah_submit]

    if len(submitted) < sesi.min_responden:
        raise ValidationAppError(
            f"Analisis membutuhkan minimal {sesi.min_responden} responden yang sudah submit,"
            f" baru ada {len(submitted)}."
        )

    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    wcp_risk: float | None = None
    if wcp_sesi_id:
        wcp_risk = _compute_wcp_risk_score(wcp_sesi_id, wcp_rsp_service, wcp_jwb_service)

    if sesi.status == "CLOSED":
        sesi_service.transition(sesi_id, "ANALYZED")

    return compute_hasil_sesi(sesi, responden_raw, wcp_risk)


@router.get(
    "/{sesi_id}/hasil",
    response_model=DcsHasilSesiRead,
    summary="Lihat hasil analisis sesi DCS",
    operation_id="dcs_hasil_sesi_get",
    responses=_NOT_FOUND_SESI,
)
def get_hasil_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi DCS.")],
    sesi_service: Annotated[DcsSesiService, Depends(get_dcs_sesi_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    wcp_rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    wcp_jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    wcp_sesi_id: Annotated[
        str | None,
        Query(description="ID sesi WCP untuk menyertakan K-Index dalam respons."),
    ] = None,
) -> DcsHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan"
            f" (status saat ini: {sesi.status})."
        )
    responden_list = rsp_service.list_by_sesi(sesi_id)
    submitted = [r for r in responden_list if r.sudah_submit]
    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    wcp_risk: float | None = None
    if wcp_sesi_id:
        wcp_risk = _compute_wcp_risk_score(wcp_sesi_id, wcp_rsp_service, wcp_jwb_service)

    return compute_hasil_sesi(sesi, responden_raw, wcp_risk)


@router.get(
    "/responden/{responden_id}/hasil",
    response_model=DcsHasilRespondenRead,
    summary="Lihat hasil analisis per responden DCS",
    operation_id="dcs_hasil_responden_get",
    responses=_NOT_FOUND_RSP,
)
def get_hasil_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
) -> DcsHasilRespondenRead:
    responden = rsp_service.get(responden_id)
    if not responden.sudah_submit:
        raise ValidationAppError("Responden belum mengirimkan jawaban.")
    raw = jwb_service.get_raw_by_responden(responden_id)
    return compute_hasil_responden(responden_id, raw)
