"""Agregasi router dengan prefix versi `/api/v1`."""

from __future__ import annotations

from fastapi import APIRouter

from .v1 import (
    dcs_hasil,
    dcs_responden,
    dcs_sesi,
    dcs_subskala,
    jabatan,
    jenjang_pendidikan,
    mata_pelajaran,
    partisipan,
    sekolah,
    system,
    wcp_dimensi,
    wcp_hasil,
    wcp_responden,
    wcp_sesi,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router, tags=["system"])
api_router.include_router(
    jenjang_pendidikan.router,
    prefix="/jenjang-pendidikan",
    tags=["core.jenjang-pendidikan"],
)
api_router.include_router(
    sekolah.router,
    prefix="/sekolah",
    tags=["core.sekolah"],
)
api_router.include_router(
    mata_pelajaran.router,
    prefix="/mata-pelajaran",
    tags=["core.mata-pelajaran"],
)
api_router.include_router(
    partisipan.router,
    prefix="/partisipan",
    tags=["core.partisipan"],
)
api_router.include_router(
    jabatan.router,
    prefix="/jabatan",
    tags=["anjab.jabatan"],
)
api_router.include_router(
    wcp_dimensi.router,
    prefix="/wcp/dimensi",
    tags=["wcp.dimensi"],
)
api_router.include_router(
    wcp_sesi.router,
    prefix="/wcp/sesi",
    tags=["wcp.sesi"],
)
api_router.include_router(
    wcp_responden.router,
    prefix="/wcp/sesi",
    tags=["wcp.responden"],
)
api_router.include_router(
    wcp_hasil.router,
    prefix="/wcp/sesi",
    tags=["wcp.hasil"],
)
api_router.include_router(
    dcs_subskala.router,
    prefix="/dcs/sub-skala",
    tags=["dcs.sub-skala"],
)
api_router.include_router(
    dcs_sesi.router,
    prefix="/dcs/sesi",
    tags=["dcs.sesi"],
)
api_router.include_router(
    dcs_responden.router,
    prefix="/dcs/sesi",
    tags=["dcs.responden"],
)
api_router.include_router(
    dcs_hasil.router,
    prefix="/dcs/sesi",
    tags=["dcs.hasil"],
)
