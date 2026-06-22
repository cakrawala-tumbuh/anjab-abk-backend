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
from .anjab.services.sme_panel import InMemorySMEPanelService, SMEPanelService
from .config import Settings, get_settings
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
from .errors import ForbiddenError, RateLimitedError, UnauthorizedError
from .security import JwksVerifier, PlaceholderVerifier, Principal, TokenVerifier, bearer_scheme
from .services.authentik_provisioner import (
    AuthentikProvisioner,
    HttpAuthentikProvisioner,
    PlaceholderAuthentikProvisioner,
)
from .services.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from .services.ratelimit import AllowAllRateLimiter, RateLimiter
from .services.readiness import ReadinessCheck
from .taskinv.services.catalog import (
    TiCatalogService,
    UraianTugasBackedCatalogService,
)
from .taskinv.services.detail import InMemoryTiDetailService, TiDetailService
from .taskinv.services.detil_tugas import DetilTugasService, InMemoryDetilTugasService
from .taskinv.services.responden import InMemoryTiRespondenService, TiRespondenService
from .taskinv.services.seleksi import InMemoryTiSeleksiService, TiSeleksiService
from .taskinv.services.sesi import InMemoryTiSesiService, TiSesiService
from .taskinv.services.tahap2 import InMemoryTiTahap2Service, TiTahap2Service
from .taskinv.services.tugas_pokok import InMemoryTugasPokokService, TugasPokokService
from .taskinv.services.uraian_tugas import InMemoryUraianTugasService, UraianTugasService
from .ts.services.log import InMemoryTsLogService, TsLogService
from .ts.services.responden import InMemoryTsRespondenService, TsRespondenService
from .ts.services.sesi import InMemoryTsSesiService, TsSesiService
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


@lru_cache
def _sme_panel_singleton() -> InMemorySMEPanelService:
    return InMemorySMEPanelService()


def get_sme_panel_service() -> SMEPanelService:
    """SEAM: kembalikan implementasi `SMEPanelService`. Ganti di sini saja."""
    return _sme_panel_singleton()


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


# --- Task Inventory master data services (TugasPokok / DetilTugas / UraianTugas) ---


@lru_cache
def _create_ti_master_services() -> (
    tuple[
        InMemoryTugasPokokService,
        InMemoryDetilTugasService,
        InMemoryUraianTugasService,
        UraianTugasBackedCatalogService,
    ]
):
    """Factory: buat dan seed TugasPokok, DetilTugas, UraianTugas, lalu buat CatalogService."""
    from .taskinv.seed import seed_catalog_models

    tp_svc = InMemoryTugasPokokService()
    dt_svc = InMemoryDetilTugasService()
    ut_svc = InMemoryUraianTugasService()
    seed_catalog_models(tp_svc, dt_svc, ut_svc)
    catalog_svc = UraianTugasBackedCatalogService(ut_svc=ut_svc, dt_svc=dt_svc, tp_svc=tp_svc)
    return tp_svc, dt_svc, ut_svc, catalog_svc


def get_tugas_pokok_service() -> TugasPokokService:
    """SEAM: kembalikan implementasi `TugasPokokService`. Ganti di sini saja."""
    tp_svc, _, _, _ = _create_ti_master_services()
    return tp_svc


def get_detil_tugas_service() -> DetilTugasService:
    """SEAM: kembalikan implementasi `DetilTugasService`. Ganti di sini saja."""
    _, dt_svc, _, _ = _create_ti_master_services()
    return dt_svc


def get_uraian_tugas_service() -> UraianTugasService:
    """SEAM: kembalikan implementasi `UraianTugasService`. Ganti di sini saja."""
    _, _, ut_svc, _ = _create_ti_master_services()
    return ut_svc


# --- Task Inventory services ---


def get_ti_catalog_service() -> TiCatalogService:
    """SEAM: kembalikan implementasi `TiCatalogService`. Ganti di sini saja."""
    _, _, _, catalog_svc = _create_ti_master_services()
    return catalog_svc


@lru_cache
def _ti_sesi_singleton() -> InMemoryTiSesiService:
    return InMemoryTiSesiService()


def get_ti_sesi_service() -> TiSesiService:
    """SEAM: kembalikan implementasi `TiSesiService`. Ganti di sini saja."""
    return _ti_sesi_singleton()


@lru_cache
def _ti_responden_singleton() -> InMemoryTiRespondenService:
    return InMemoryTiRespondenService()


def get_ti_responden_service() -> TiRespondenService:
    """SEAM: kembalikan implementasi `TiRespondenService`. Ganti di sini saja."""
    return _ti_responden_singleton()


@lru_cache
def _ti_seleksi_singleton() -> InMemoryTiSeleksiService:
    return InMemoryTiSeleksiService()


def get_ti_seleksi_service() -> TiSeleksiService:
    """SEAM: kembalikan implementasi `TiSeleksiService`. Ganti di sini saja."""
    return _ti_seleksi_singleton()


@lru_cache
def _ti_detail_singleton() -> InMemoryTiDetailService:
    return InMemoryTiDetailService()


def get_ti_detail_service() -> TiDetailService:
    """SEAM: kembalikan implementasi `TiDetailService`. Ganti di sini saja."""
    return _ti_detail_singleton()


@lru_cache
def _ti_tahap2_singleton() -> InMemoryTiTahap2Service:
    return InMemoryTiTahap2Service()


def get_ti_tahap2_service() -> TiTahap2Service:
    """SEAM: kembalikan implementasi `TiTahap2Service`. Ganti di sini saja."""
    return _ti_tahap2_singleton()


# --- TS services ---


@lru_cache
def _ts_sesi_singleton() -> InMemoryTsSesiService:
    return InMemoryTsSesiService()


def get_ts_sesi_service() -> TsSesiService:
    """SEAM: kembalikan implementasi `TsSesiService`. Ganti di sini saja."""
    return _ts_sesi_singleton()


@lru_cache
def _ts_responden_singleton() -> InMemoryTsRespondenService:
    return InMemoryTsRespondenService()


def get_ts_responden_service() -> TsRespondenService:
    """SEAM: kembalikan implementasi `TsRespondenService`. Ganti di sini saja."""
    return _ts_responden_singleton()


@lru_cache
def _ts_log_singleton() -> InMemoryTsLogService:
    return InMemoryTsLogService()


def get_ts_log_service() -> TsLogService:
    """SEAM: kembalikan implementasi `TsLogService`. Ganti di sini saja."""
    return _ts_log_singleton()


# --- Authentik Provisioner ---


def get_authentik_provisioner(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthentikProvisioner:
    """SEAM: kembalikan provisioner Authentik.

    Mengembalikan `HttpAuthentikProvisioner` bila env AUTHENTIK_API_URL,
    AUTHENTIK_API_TOKEN, dan AUTHENTIK_PARTISIPAN_GROUP_ID sudah di-set;
    sebaliknya `PlaceholderAuthentikProvisioner` yang mengembalikan ID palsu.
    """
    if (
        settings.authentik_api_url
        and settings.authentik_api_token
        and settings.authentik_partisipan_group_id
    ):
        return HttpAuthentikProvisioner(
            api_url=settings.authentik_api_url,
            api_token=settings.authentik_api_token,
            partisipan_group_id=settings.authentik_partisipan_group_id,
        )
    return PlaceholderAuthentikProvisioner()


# --- Auth ---


@lru_cache
def _verifier_singleton() -> TokenVerifier:
    s = get_settings()
    if s.authentik_jwks_uri and s.authentik_issuer:
        return JwksVerifier(jwks_uri=s.authentik_jwks_uri, issuer=s.authentik_issuer)
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


def require_admin(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """Guard otorisasi: hanya principal dengan grup `admin` yang diizinkan."""
    if "admin" not in principal.groups:
        raise ForbiddenError("Akses ditolak: hanya admin yang dapat mengubah master data.")
    return principal


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
