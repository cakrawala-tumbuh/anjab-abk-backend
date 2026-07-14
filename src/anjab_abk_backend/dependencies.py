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
from .dcs.services.instrumen import DcsInstrumenService
from .dcs.services.instrumen_sql import SqlDcsInstrumenService
from .dcs.services.jawaban import DcsJawabanService
from .dcs.services.jawaban_sql import SqlDcsJawabanService
from .dcs.services.responden import DcsRespondenService
from .dcs.services.responden_sql import SqlDcsRespondenService
from .dcs.services.subskala import DcsSubSkalaService
from .dcs.services.subskala_sql import SqlDcsSubSkalaService
from .errors import ForbiddenError, RateLimitedError, UnauthorizedError
from .opm.services.jawaban import OpmJawabanService
from .opm.services.jawaban_sql import SqlOpmJawabanService
from .opm.services.responden import OpmRespondenService
from .opm.services.responden_sql import SqlOpmRespondenService
from .opm.services.sesi import OpmSesiService
from .opm.services.sesi_sql import SqlOpmSesiService
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
from .taskinv.schemas.sesi import TiSesiRead
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
from .ts.services.penugasan import TsPenugasanService
from .ts.services.penugasan_sql import SqlTsPenugasanService
from .wcp.services.dimensi import WcpDimensiService
from .wcp.services.dimensi_sql import SqlWcpDimensiService
from .wcp.services.instrumen import WcpInstrumenService
from .wcp.services.instrumen_sql import SqlWcpInstrumenService
from .wcp.services.jawaban import WcpJawabanService
from .wcp.services.jawaban_sql import SqlWcpJawabanService
from .wcp.services.responden import WcpRespondenService
from .wcp.services.responden_sql import SqlWcpRespondenService

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


def get_wcp_instrumen_service(session: SessionDep) -> WcpInstrumenService:
    """SEAM: implementasi `WcpInstrumenService` berbasis PostgreSQL."""
    return SqlWcpInstrumenService(session)


def get_wcp_responden_service(
    session: SessionDep,
    partisipan_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    jabatan_service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> WcpRespondenService:
    """SEAM: implementasi `WcpRespondenService` berbasis PostgreSQL."""
    return SqlWcpRespondenService(session, partisipan_service, jabatan_service)


def get_wcp_jawaban_service(session: SessionDep) -> WcpJawabanService:
    """SEAM: implementasi `WcpJawabanService` berbasis PostgreSQL."""
    return SqlWcpJawabanService(session)


# --- DCS services ---


def get_dcs_subskala_service(session: SessionDep) -> DcsSubSkalaService:
    """SEAM: implementasi `DcsSubSkalaService` berbasis PostgreSQL."""
    return SqlDcsSubSkalaService(session)


def get_dcs_instrumen_service(session: SessionDep) -> DcsInstrumenService:
    """SEAM: implementasi `DcsInstrumenService` berbasis PostgreSQL."""
    return SqlDcsInstrumenService(session)


def get_dcs_responden_service(
    session: SessionDep,
    partisipan_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    jabatan_service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> DcsRespondenService:
    """SEAM: implementasi `DcsRespondenService` berbasis PostgreSQL."""
    return SqlDcsRespondenService(session, partisipan_service, jabatan_service)


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
    jabatan_svc = SqlJabatanService(session)
    return UraianTugasBackedCatalogService(
        ut_svc=ut_svc, dt_svc=dt_svc, tp_svc=tp_svc, jabatan_svc=jabatan_svc
    )


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


def get_ts_penugasan_service(session: SessionDep) -> TsPenugasanService:
    """SEAM: implementasi `TsPenugasanService` berbasis PostgreSQL."""
    return SqlTsPenugasanService(session)


def get_ts_log_service(session: SessionDep) -> TsLogService:
    """SEAM: implementasi `TsLogService` berbasis PostgreSQL."""
    return SqlTsLogService(session)


# --- OPM services ---


def get_opm_sesi_service(session: SessionDep) -> OpmSesiService:
    """SEAM: implementasi `OpmSesiService` berbasis PostgreSQL."""
    return SqlOpmSesiService(session)


def get_opm_responden_service(session: SessionDep) -> OpmRespondenService:
    """SEAM: implementasi `OpmRespondenService` berbasis PostgreSQL."""
    return SqlOpmRespondenService(session)


def get_opm_jawaban_service(session: SessionDep) -> OpmJawabanService:
    """SEAM: implementasi `OpmJawabanService` berbasis PostgreSQL."""
    return SqlOpmJawabanService(session)


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


def authorize_responden_access(
    principal: Principal,
    partisipan_id: str | None,
    par_service: PartisipanService,
) -> None:
    """Guard otorisasi object-level: admin ATAU partisipan pemilik `responden`.

    `partisipan_id` adalah pemilik responden/penugasan yang diakses (`None` untuk
    responden anonim/tanpa tautan partisipan — hanya dapat diakses admin). Dipakai
    di endpoint TI/DCS/WCP/OPM/TS agar partisipan tidak dapat membaca atau menulis
    data responden milik partisipan lain lewat penebakan ID (BOLA/IDOR).
    """
    if "admin" in principal.groups:
        return
    par = par_service.get_by_subject(principal.subject)
    if par is None or partisipan_id is None or par.id != partisipan_id:
        raise ForbiddenError("Akses ditolak: Anda bukan pemilik data responden ini.")


def authorize_sesi_access(
    principal: Principal,
    sesi: TiSesiRead,
    par_service: PartisipanService,
    rsp_service: TiRespondenService,
) -> None:
    """Guard otorisasi object-level sesi TI: admin ATAU peserta sesi ini.

    Peserta = koordinator sesi, atau partisipan yang terdaftar sebagai responden di sesi
    ini. Dipakai di endpoint baca sesi/tahap2/task-terpilih agar partisipan tidak dapat
    membaca sesi jabatan lain lewat penebakan ID (BOLA/IDOR).
    """
    if "admin" in principal.groups:
        return
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi ini.")
    if par.id == sesi.koordinator_id:
        return
    if any(r.sesi_id == sesi.id for r in rsp_service.list_by_partisipan(par.id)):
        return
    raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi ini.")


def authorize_opm_sesi_access(
    principal: Principal,
    sesi_id: str,
    par_service: PartisipanService,
    rsp_service: OpmRespondenService,
) -> None:
    """Guard otorisasi object-level sesi OPM: admin ATAU responden sesi ini.

    OPM tidak punya koordinator (beda dari Task Inventory), jadi peserta = partisipan
    yang terdaftar sebagai responden di sesi ini. Dipakai di `GET /sesi/{id}/task` agar
    partisipan tidak dapat membaca snapshot task sesi jabatan lain lewat penebakan ID
    (BOLA/IDOR).
    """
    if "admin" in principal.groups:
        return
    par = par_service.get_by_subject(principal.subject)
    if par is None or not any(r.sesi_id == sesi_id for r in rsp_service.list_by_partisipan(par.id)):
        raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi OPM ini.")


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


# --- Guard konstan untuk operasi baca ---

READ_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
"""Guard baku untuk SETIAP operasi baca (GET) di `api/v1/`.

INVARIANT: setiap operasi GET wajib memasang `dependencies=READ_GUARDS` — kecuali
`/health`, `/ready`, dan `/version` (`api/v1/system.py`) yang memang publik. Tidak ada
endpoint baca yang boleh dijangkau tanpa token valid; endpoint yang membaca data per
individu WAJIB menambah guard object-level (`authorize_*_access`) di badan fungsinya.
Ditegakkan otomatis oleh `tests/test_auth_guards.py` (memindai `app.routes`, bukan daftar
manual — endpoint GET baru yang lupa diguard langsung gagal test).

Didefinisikan di sini (bukan per modul router seperti `_WRITE_GUARDS`/`_ADMIN_GUARDS`)
agar tidak terduplikasi di 16 berkas router.
"""


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
