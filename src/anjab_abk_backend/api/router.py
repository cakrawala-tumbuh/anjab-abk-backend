"""Agregasi router dengan prefix versi `/api/v1`."""

from __future__ import annotations

from fastapi import APIRouter

from .v1 import jabatan, jenjang_pendidikan, mata_pelajaran, partisipan, sekolah, system

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
