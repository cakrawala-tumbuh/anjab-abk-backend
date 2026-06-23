"""Dependency injection umum: paginasi, service seam, principal auth, idempotency,
rate limiting, dan readiness check.

Provider data (sekolah, jabatan, sesi, dst.) kini terikat **sesi PostgreSQL per
request** (lihat `db.get_session`): semua provider yang `Depends(get_session)`
berbagi satu `Session` → satu unit-of-work/transaksi per request (commit di
teardown setelah respons terbentuk). Verifier token & rate limiter tetap singleton
(`lru_cache`) karena bukan data.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .anjab.services.jabatan import JabatanService
from .anjab.services.jabatan_sql import SqlJabatanService
from .anjab.services.sme_panel import SMEPanelService
from .anjab.services.sme_panel_sql import SqlSMEPanelService
from .config import Settings, get_settings
from .core.services.jenjang_pendidikan import JenjangPendidikanService
from .core.services.jenjang_pendidikan_sql import SqlJenjangPendidikanService
from .core.services.mata_pelajaran import MataPelajaranService
from .core.services.mata_pelajaran_sql import SqlMataPelajaranService
from .core.services.partisipan import PartisipanService
from .core.services.partisipan_sql import SqlPartisipanService
from .core.services.sekolah import SekolahService
from .core.services.sekolah_sql import SqlSekolahService
from .db import get_session
from .dcs.services.jawaban import DcsJawabanService
from .dcs.services.jawaban_sql import SqlDcsJawabanService
from .dcs.services.responden import DcsRespondenService
from .dcs.services.responden_sql import SqlDcsRespondenService
from .dcs.services.sesi import DcsSesiService
from .dcs.services.sesi_sql import SqlDcsSesiService
from .dcs.services.subskala import DcsSubSkalaService
from .dcs.services.subskala_sql import SqlDcsSubSkalaService
from .errors import ForbiddenError, RateLimitedError, UnauthorizedError
from .security import JwksVerifier, PlaceholderVerifier, Principal, TokenVerifier, bearer_scheme
from .services.authentik_provisioner import (
    AuthentikProvisioner,
    HttpAuthentikProvisioner,
    PlaceholderAuthentikProvisioner,
)
from .services.idempotency import IdempotencyStore
from .services.idempotency_sql import SqlIdempotencyStore
from .services.ratelimit import AllowAllRateLimiter, RateLimiter
from .services.readiness import ReadinessCheck
from .services.readiness_db import DatabaseReadinessCheck
from .taskinv.services.catalog import TiCatalogService, UraianTugasBackedCatalogService
from .taskinv.services.detail import TiDetailService
from .taskinv.services.detail_sql import SqlTiDetailService
from .taskinv.services.detil_tugas import DetilTugasService
from .taskinv.services.detil_tugas_sql import SqlDetilTugasService
from .taskinv.services.responden import TiRespondenService
from .taskinv.services.responden_sql import SqlTiRespondenService
from .taskinv.services.seleksi import TiSeleksiService
from .taskinv.services.seleksi_sql import SqlTiSeleksiService
from .taskinv.services.sesi import TiSesiService
from .taskinv.services.sesi_sql import SqlTiSesiService
from .taskinv.services.tahap2 import TiTahap2Service
from .taskinv.services.tahap2_sql import SqlTiTahap2Service
from .taskinv.services.tugas_pokok import TugasPokokService
from .taskinv.services.tugas_pokok_sql import SqlTugasPokokService
from .taskinv.services.uraian_tugas import UraianTugasService
from .taskinv.services.uraian_tugas_sql import SqlUraianTugasService
from .ts.services.log import TsLogService
from .ts.services.log_sql import SqlTsLogService
from .ts.services.responden import TsRespondenService
from .ts.services.responden_sql import SqlTsRespondenService
from .ts.services.sesi import TsSesiService
from .ts.services.sesi_sql import SqlTsSesiService
from .wcp.services.dimensi import WcpDimensiService
from .wcp.services.dimensi_sql import SqlWcpDimensiService
from .wcp.services.jawaban import WcpJawabanService
from .wcp.services.jawaban_sql import SqlWcpJawabanService
from .wcp.services.responden import WcpRespondenService
from .wcp.services.responden_sql import SqlWcpRespondenService
from .wcp.services.sesi import WcpSesiService
from .wcp.services.sesi_sql import SqlWcpSesiService

SessionDep = Annotated[Session, Depends(get_session)]


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=500, description="Maks item per halaman.")] = 20,
    offset: Annotated[int, Query(ge=0, description="Jumlah item yang dilewati.")] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


# --- Core services ---


def get_jenjang_pendidikan_service(session: SessionDep) -> JenjangPendidikanService:
    """SEAM: implementasi `JenjangPendidikanService` berbasis PostgreSQL."""
    return SqlJenjangPendidikanService(session)


def get_sekolah_service(session: SessionDep) -> SekolahService:
    """SEAM: implementasi `SekolahService` berbasis PostgreSQL."""
    return SqlSekolahService(session)


def get_mata_pelajaran_service(session: SessionDep) -> MataPelajaranService:
    """SEAM: implementasi `MataPelajaranService` berbasis PostgreSQL."""
    return SqlMataPelajaranService(session)


def get_partisipan_service(session: SessionDep) -> PartisipanService:
    """SEAM: implementasi `PartisipanService` berbasis PostgreSQL."""
    return SqlPartisipanService(session)


# --- ANJAB services ---


def get_jabatan_service(session: SessionDep) -> JabatanService:
    """SEAM: implementasi `JabatanService` berbasis PostgreSQL."""
    return SqlJabatanService(session)


def get_sme_panel_service(session: SessionDep) -> SMEPanelService:
    """SEAM: implementasi `SMEPanelService` berbasis PostgreSQL."""
    return SqlSMEPanelService(session)


# --- WCP services ---


def get_wcp_dimensi_service(session: SessionDep) -> WcpDimensiService:
    """SEAM: implementasi `WcpDimensiService` berbasis PostgreSQL."""
    return SqlWcpDimensiService(session)


def get_wcp_sesi_service(session: SessionDep) -> WcpSesiService:
    """SEAM: implementasi `WcpSesiService` berbasis PostgreSQL."""
    return SqlWcpSesiService(session)


def get_wcp_responden_service(session: SessionDep) -> WcpRespondenService:
    """SEAM: implementasi `WcpRespondenService` berbasis PostgreSQL."""
    return SqlWcpRespondenService(session)


def get_wcp_jawaban_service(session: SessionDep) -> WcpJawabanService:
    """SEAM: implementasi `WcpJawabanService` berbasis PostgreSQL."""
    return SqlWcpJawabanService(session)


# --- DCS services ---


def get_dcs_subskala_service(session: SessionDep) -> DcsSubSkalaService:
    """SEAM: implementasi `DcsSubSkalaService` berbasis PostgreSQL."""
    return SqlDcsSubSkalaService(session)


def get_dcs_sesi_service(session: SessionDep) -> DcsSesiService:
    """SEAM: implementasi `DcsSesiService` berbasis PostgreSQL."""
    return SqlDcsSesiService(session)


def get_dcs_responden_service(session: SessionDep) -> DcsRespondenService:
    """SEAM: implementasi `DcsRespondenService` berbasis PostgreSQL."""
    return SqlDcsRespondenService(session)


def get_dcs_jawaban_service(session: SessionDep) -> DcsJawabanService:
    """SEAM: implementasi `DcsJawabanService` berbasis PostgreSQL."""
    return SqlDcsJawabanService(session)


# --- Task Inventory master data services (TugasPokok / DetilTugas / UraianTugas) ---


def get_tugas_pokok_service(session: SessionDep) -> TugasPokokService:
    """SEAM: implementasi `TugasPokokService` berbasis PostgreSQL."""
    return SqlTugasPokokService(session)


def get_detil_tugas_service(session: SessionDep) -> DetilTugasService:
    """SEAM: implementasi `DetilTugasService` berbasis PostgreSQL."""
    return SqlDetilTugasService(session)


def get_uraian_tugas_service(session: SessionDep) -> UraianTugasService:
    """SEAM: implementasi `UraianTugasService` berbasis PostgreSQL."""
    return SqlUraianTugasService(session)


def get_ti_catalog_service(session: SessionDep) -> TiCatalogService:
    """SEAM: katalog Task Inventory dirakit live dari UraianTugas/DetilTugas/TugasPokok (DB)."""
    tp_svc = SqlTugasPokokService(session)
    dt_svc = SqlDetilTugasService(session)
    ut_svc = SqlUraianTugasService(session)
    return UraianTugasBackedCatalogService(ut_svc=ut_svc, dt_svc=dt_svc, tp_svc=tp_svc)


# --- Task Inventory services ---


def get_ti_sesi_service(session: SessionDep) -> TiSesiService:
    """SEAM: implementasi `TiSesiService` berbasis PostgreSQL."""
    return SqlTiSesiService(session)


def get_ti_responden_service(session: SessionDep) -> TiRespondenService:
    """SEAM: implementasi `TiRespondenService` berbasis PostgreSQL."""
    return SqlTiRespondenService(session)


def get_ti_seleksi_service(session: SessionDep) -> TiSeleksiService:
    """SEAM: implementasi `TiSeleksiService` berbasis PostgreSQL."""
    return SqlTiSeleksiService(session)


def get_ti_detail_service(session: SessionDep) -> TiDetailService:
    """SEAM: implementasi `TiDetailService` berbasis PostgreSQL."""
    return SqlTiDetailService(session)


def get_ti_tahap2_service(session: SessionDep) -> TiTahap2Service:
    """SEAM: implementasi `TiTahap2Service` berbasis PostgreSQL."""
    return SqlTiTahap2Service(session)


# --- TS services ---


def get_ts_sesi_service(session: SessionDep) -> TsSesiService:
    """SEAM: implementasi `TsSesiService` berbasis PostgreSQL."""
    return SqlTsSesiService(session)


def get_ts_responden_service(session: SessionDep) -> TsRespondenService:
    """SEAM: implementasi `TsRespondenService` berbasis PostgreSQL."""
    return SqlTsRespondenService(session)


def get_ts_log_service(session: SessionDep) -> TsLogService:
    """SEAM: implementasi `TsLogService` berbasis PostgreSQL."""
    return SqlTsLogService(session)


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
    """SEAM: pemeriksaan kesiapan. `/ready` kini ping PostgreSQL (503 bila DB mati)."""
    return [DatabaseReadinessCheck()]


# --- Idempotency ---


def get_idempotency_store(session: SessionDep) -> IdempotencyStore:
    """SEAM: store idempotency berbasis PostgreSQL (reserve via INSERT ON CONFLICT)."""
    return SqlIdempotencyStore(session)


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
