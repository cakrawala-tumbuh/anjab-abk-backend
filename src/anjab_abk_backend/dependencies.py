"""Dependency injection umum: paginasi, service seam, principal auth, idempotency,
rate limiting, dan readiness check.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from .anjab.services.jabatan import InMemoryJabatanService, JabatanService
from .core.services.jenjang_pendidikan import (
    InMemoryJenjangPendidikanService,
    JenjangPendidikanService,
)
from .core.services.mata_pelajaran import InMemoryMataPelajaranService, MataPelajaranService
from .core.services.partisipan import InMemoryPartisipanService, PartisipanService
from .core.services.sekolah import InMemorySekolahService, SekolahService
from .dcs.services.jawaban import DcsJawabanService, InMemoryDcsJawabanService
from .dcs.services.responden import DcsRespondenService, InMemoryDcsRespondenService
from .dcs.services.sesi import DcsSesiService, InMemoryDcsSesiService
from .dcs.services.subskala import DcsSubSkalaService, InMemoryDcsSubSkalaService
from .errors import RateLimitedError, UnauthorizedError
from .security import PlaceholderVerifier, Principal, TokenVerifier, bearer_scheme
from .services.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from .services.ratelimit import AllowAllRateLimiter, RateLimiter
from .services.readiness import ReadinessCheck
from .wcp.services.dimensi import InMemoryWcpDimensiService, WcpDimensiService
from .wcp.services.jawaban import InMemoryWcpJawabanService, WcpJawabanService
from .wcp.services.responden import InMemoryWcpRespondenService, WcpRespondenService
from .wcp.services.sesi import InMemoryWcpSesiService, WcpSesiService


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=100, description="Maks item per halaman.")] = 20,
    offset: Annotated[int, Query(ge=0, description="Jumlah item yang dilewati.")] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


# --- Core services ---


@lru_cache
def _jenjang_singleton() -> InMemoryJenjangPendidikanService:
    return InMemoryJenjangPendidikanService()


def get_jenjang_pendidikan_service() -> JenjangPendidikanService:
    """SEAM: kembalikan implementasi `JenjangPendidikanService`. Ganti di sini saja."""
    return _jenjang_singleton()


@lru_cache
def _sekolah_singleton() -> InMemorySekolahService:
    return InMemorySekolahService()


def get_sekolah_service() -> SekolahService:
    """SEAM: kembalikan implementasi `SekolahService`. Ganti di sini saja."""
    return _sekolah_singleton()


@lru_cache
def _mata_pelajaran_singleton() -> InMemoryMataPelajaranService:
    return InMemoryMataPelajaranService()


def get_mata_pelajaran_service() -> MataPelajaranService:
    """SEAM: kembalikan implementasi `MataPelajaranService`. Ganti di sini saja."""
    return _mata_pelajaran_singleton()


@lru_cache
def _partisipan_singleton() -> InMemoryPartisipanService:
    return InMemoryPartisipanService()


def get_partisipan_service() -> PartisipanService:
    """SEAM: kembalikan implementasi `PartisipanService`. Ganti di sini saja."""
    return _partisipan_singleton()


# --- ANJAB services ---


@lru_cache
def _jabatan_singleton() -> InMemoryJabatanService:
    return InMemoryJabatanService()


def get_jabatan_service() -> JabatanService:
    """SEAM: kembalikan implementasi `JabatanService`. Ganti di sini saja."""
    return _jabatan_singleton()


# --- WCP services ---


@lru_cache
def _wcp_dimensi_singleton() -> InMemoryWcpDimensiService:
    return InMemoryWcpDimensiService()


def get_wcp_dimensi_service() -> WcpDimensiService:
    """SEAM: kembalikan implementasi `WcpDimensiService`. Ganti di sini saja."""
    return _wcp_dimensi_singleton()


@lru_cache
def _wcp_sesi_singleton() -> InMemoryWcpSesiService:
    return InMemoryWcpSesiService()


def get_wcp_sesi_service() -> WcpSesiService:
    """SEAM: kembalikan implementasi `WcpSesiService`. Ganti di sini saja."""
    return _wcp_sesi_singleton()


@lru_cache
def _wcp_responden_singleton() -> InMemoryWcpRespondenService:
    return InMemoryWcpRespondenService()


def get_wcp_responden_service() -> WcpRespondenService:
    """SEAM: kembalikan implementasi `WcpRespondenService`. Ganti di sini saja."""
    return _wcp_responden_singleton()


@lru_cache
def _wcp_jawaban_singleton() -> InMemoryWcpJawabanService:
    return InMemoryWcpJawabanService()


def get_wcp_jawaban_service() -> WcpJawabanService:
    """SEAM: kembalikan implementasi `WcpJawabanService`. Ganti di sini saja."""
    return _wcp_jawaban_singleton()


# --- DCS services ---


@lru_cache
def _dcs_subskala_singleton() -> InMemoryDcsSubSkalaService:
    return InMemoryDcsSubSkalaService()


def get_dcs_subskala_service() -> DcsSubSkalaService:
    """SEAM: kembalikan implementasi `DcsSubSkalaService`. Ganti di sini saja."""
    return _dcs_subskala_singleton()


@lru_cache
def _dcs_sesi_singleton() -> InMemoryDcsSesiService:
    return InMemoryDcsSesiService()


def get_dcs_sesi_service() -> DcsSesiService:
    """SEAM: kembalikan implementasi `DcsSesiService`. Ganti di sini saja."""
    return _dcs_sesi_singleton()


@lru_cache
def _dcs_responden_singleton() -> InMemoryDcsRespondenService:
    return InMemoryDcsRespondenService()


def get_dcs_responden_service() -> DcsRespondenService:
    """SEAM: kembalikan implementasi `DcsRespondenService`. Ganti di sini saja."""
    return _dcs_responden_singleton()


@lru_cache
def _dcs_jawaban_singleton() -> InMemoryDcsJawabanService:
    return InMemoryDcsJawabanService()


def get_dcs_jawaban_service() -> DcsJawabanService:
    """SEAM: kembalikan implementasi `DcsJawabanService`. Ganti di sini saja."""
    return _dcs_jawaban_singleton()


# --- Auth ---


@lru_cache
def _verifier_singleton() -> PlaceholderVerifier:
    return PlaceholderVerifier()


def get_token_verifier() -> TokenVerifier:
    """SEAM: kembalikan verifier token. Ganti di sini saja (diisi backend-authentik-skill)."""
    return _verifier_singleton()


def get_current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> Principal:
    if creds is None:
        raise UnauthorizedError("Token tidak ada.", headers={"WWW-Authenticate": "Bearer"})
    return verifier.verify(creds.credentials)


# --- Rate limiting ---


@lru_cache
def _rate_limiter_singleton() -> AllowAllRateLimiter:
    return AllowAllRateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter_singleton()


def rate_limit(
    request: Request,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"{request.method}:{request.url.path}:{client}"
    if not limiter.hit(key):
        raise RateLimitedError(
            "Terlalu banyak permintaan, coba lagi nanti.",
            headers={"Retry-After": "1"},
        )


# --- Readiness ---


def get_readiness_checks() -> list[ReadinessCheck]:
    """SEAM: daftar pemeriksaan kesiapan. Default kosong → langsung 'ready'."""
    return []


# --- Idempotency ---


@lru_cache
def _idempotency_store_singleton() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def get_idempotency_store() -> IdempotencyStore:
    return _idempotency_store_singleton()


@dataclass
class Idempotency:
    key: str | None
    store: IdempotencyStore

    def cached(self) -> dict[str, Any] | None:
        return self.store.get(self.key) if self.key else None

    def reserve(self) -> bool:
        return self.store.reserve(self.key) if self.key else True

    def release(self) -> None:
        if self.key:
            self.store.release(self.key)

    def remember(self, value: BaseModel) -> None:
        if self.key:
            self.store.save(self.key, value.model_dump(mode="json"))


def idempotency(
    request: Request,
    store: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Kunci idempotency opsional."),
    ] = None,
) -> Idempotency:
    scoped = f"{request.method}:{request.url.path}:{key}" if key else None
    return Idempotency(key=scoped, store=store)
