"""Dependency injection umum: paginasi, service seam, principal auth, idempotency,
rate limiting, dan readiness check.

Provider data (sekolah, jabatan, sesi, dst.) kini terikat **sesi PostgreSQL per
request** (lihat `db.get_session`): semua provider yang `Depends(get_session)`
berbagi satu `Session` → satu unit-of-work/transaksi per request (commit di
teardown setelah respons terbentuk). Verifier token & rate limiter tetap singleton
(`lru_cache`) karena bukan data.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .ai.gateway import AiGateway
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
from .db import get_db_settings, get_session
from .dcs.services.instrumen import DcsInstrumenService
from .dcs.services.instrumen_sql import SqlDcsInstrumenService
from .dcs.services.jawaban import DcsJawabanService
from .dcs.services.jawaban_sql import SqlDcsJawabanService
from .dcs.services.responden import DcsRespondenService
from .dcs.services.responden_sql import SqlDcsRespondenService
from .dcs.services.subskala import DcsSubSkalaService
from .dcs.services.subskala_sql import SqlDcsSubSkalaService
from .errors import ForbiddenError, RateLimitedError, UnauthorizedError
from .logging import AUDIT_LOGGER_NAME
from .narasi.services.klarifikasi import KlarifikasiService
from .narasi.services.klarifikasi_sql import SqlKlarifikasiService
from .narasi.services.metrik import NarasiMetrikService
from .narasi.services.metrik_sql import SqlNarasiMetrikService
from .narasi.services.narasi import NarasiService
from .narasi.services.narasi_sql import SqlNarasiService
from .narasi.services.permintaan_ai import PermintaanAiService
from .narasi.services.permintaan_ai_sql import SqlPermintaanAiService
from .narasi.services.sumber import NarasiSumberService
from .narasi.services.sumber_sql import SqlNarasiSumberService
from .opm.services.jawaban import OpmJawabanService
from .opm.services.jawaban_sql import SqlOpmJawabanService
from .opm.services.responden import OpmRespondenService
from .opm.services.responden_sql import SqlOpmRespondenService
from .opm.services.sesi import OpmSesiService
from .opm.services.sesi_sql import SqlOpmSesiService
from .redesain.schemas.kosakata import GRUP_SEKOLAH_PENGISI, GRUP_TIM_KAJIAN
from .redesain.services.alternatif import AlternatifService
from .redesain.services.alternatif_sql import SqlAlternatifService
from .redesain.services.bukti import BuktiService
from .redesain.services.bukti_sql import SqlBuktiService
from .redesain.services.cakupan_jabatan import CakupanJabatanService
from .redesain.services.cakupan_jabatan_sql import SqlCakupanJabatanService
from .redesain.services.kode_orang import KodeOrangService
from .redesain.services.kode_orang_sql import SqlKodeOrangService
from .redesain.services.konfirmasi import KonfirmasiService
from .redesain.services.konfirmasi_sql import SqlKonfirmasiService
from .redesain.services.konteks import KonteksService
from .redesain.services.konteks_sql import SqlKonteksService
from .redesain.services.koreksi import KoreksiService
from .redesain.services.koreksi_sql import SqlKoreksiService
from .redesain.services.masalah import MasalahService
from .redesain.services.masalah_sql import SqlMasalahService
from .redesain.services.penilaian import PenilaianService
from .redesain.services.penilaian_sql import SqlPenilaianService
from .redesain.services.proses import ProsesService
from .redesain.services.proses_sql import SqlProsesService
from .redesain.services.riwayat import RiwayatService
from .redesain.services.riwayat_sql import SqlRiwayatService
from .redesain.services.sesi import SesiService
from .redesain.services.sesi_sql import SqlSesiService
from .redesain.services.versi_metode import VersiMetodeService
from .redesain.services.versi_metode_sql import SqlVersiMetodeService
from .redesain.services.yayasan import RingkasanYayasanService
from .redesain.services.yayasan_sql import SqlRingkasanYayasanService
from .security import JwksVerifier, PlaceholderVerifier, Principal, TokenVerifier, bearer_scheme
from .services.ai_penyedia_sql import SqlAiPenyediaService
from .services.ai_run import AiRunService
from .services.ai_run_sql import SqlAiRunService
from .services.ai_saklar import SaklarAiService
from .services.ai_saklar_sql import SqlSaklarAiService
from .services.ai_usulan import AiUsulanService
from .services.ai_usulan_sql import SqlAiUsulanService
from .services.async_job import AsyncJobService
from .services.async_job_sql import SqlAsyncJobService
from .services.authentik_provisioner import (
    AuthentikProvisioner,
    HttpAuthentikProvisioner,
    PlaceholderAuthentikProvisioner,
)
from .services.backup import BackupService
from .services.idempotency import IdempotencyStore
from .services.idempotency_sql import SqlIdempotencyStore
from .services.ratelimit import AllowAllRateLimiter, RateLimiter
from .services.readiness import ReadinessCheck
from .services.readiness_db import DatabaseReadinessCheck
from .services.riset_kasus_negatif import RisetKasusNegatifService
from .services.riset_kasus_negatif_sql import SqlRisetKasusNegatifService
from .services.riset_protokol import RisetProtokolService
from .services.riset_protokol_sql import SqlRisetProtokolService
from .services.riset_signoff import RisetSignoffService
from .services.riset_signoff_sql import SqlRisetSignoffService
from .services.riset_statistik import RisetStatistikService
from .services.riset_statistik_sql import SqlRisetStatistikService
from .services.skema_db import SkemaDbService
from .services.skema_db_sql import SqlSkemaDbService
from .taskinv.schemas.sesi import TiSesiRead
from .taskinv.services.catalog import TiCatalogService, UraianTugasBackedCatalogService
from .taskinv.services.detail import TiDetailService
from .taskinv.services.detail_sql import SqlTiDetailService
from .taskinv.services.detil_tugas import DetilTugasService
from .taskinv.services.detil_tugas_sql import SqlDetilTugasService
from .taskinv.services.prabank import TiPrabankService
from .taskinv.services.prabank_sql import SqlTiPrabankService
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
from .taskinv.services.usulan import TiUsulanService
from .taskinv.services.usulan_sql import SqlTiUsulanService
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


def get_ti_sesi_service(
    session: SessionDep,
    partisipan_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    sekolah_service: Annotated[SekolahService, Depends(get_sekolah_service)],
) -> TiSesiService:
    """SEAM: implementasi `TiSesiService` berbasis PostgreSQL.

    `partisipan_service`/`sekolah_service` disuntik untuk gerbang cabang
    koordinator & penyaringan cabang auto-populate responden
    (backlog `anjab-abk-backend#41`).
    """
    return SqlTiSesiService(session, partisipan_service, sekolah_service)


def get_ti_responden_service(
    session: SessionDep,
    partisipan_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    sekolah_service: Annotated[SekolahService, Depends(get_sekolah_service)],
) -> TiRespondenService:
    """SEAM: implementasi `TiRespondenService` berbasis PostgreSQL.

    `partisipan_service`/`sekolah_service` disuntik untuk gerbang cabang pada
    penambahan responden tunggal (backlog `anjab-abk-backend#41`).
    """
    return SqlTiRespondenService(session, partisipan_service, sekolah_service)


def get_ti_seleksi_service(session: SessionDep) -> TiSeleksiService:
    """SEAM: implementasi `TiSeleksiService` berbasis PostgreSQL."""
    return SqlTiSeleksiService(session)


def get_ti_prabank_service(session: SessionDep) -> TiPrabankService:
    """SEAM: implementasi `TiPrabankService` (cerita pra-bank + log paparan) di PostgreSQL."""
    return SqlTiPrabankService(session)


def get_ti_detail_service(session: SessionDep) -> TiDetailService:
    """SEAM: implementasi `TiDetailService` berbasis PostgreSQL."""
    return SqlTiDetailService(session)


def get_ti_tahap2_service(session: SessionDep) -> TiTahap2Service:
    """SEAM: implementasi `TiTahap2Service` berbasis PostgreSQL."""
    return SqlTiTahap2Service(session)


def get_ti_usulan_service(session: SessionDep) -> TiUsulanService:
    """SEAM: implementasi `TiUsulanService` berbasis PostgreSQL.

    Menyuntik `TugasPokokService`/`DetilTugasService` (pola sama dengan
    `get_ti_catalog_service`) agar `TiUsulanRead.tugas_pokok`/`.detil_tugas` bisa
    diresolusi live tanpa menyimpan snapshot nama di tabel usulan.
    """
    return SqlTiUsulanService(
        session, tp_svc=SqlTugasPokokService(session), dt_svc=SqlDetilTugasService(session)
    )


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


# --- Redesain services ---


def get_riwayat_service(session: SessionDep) -> RiwayatService:
    """SEAM: implementasi `RiwayatService` berbasis PostgreSQL."""
    return SqlRiwayatService(session)


def get_konteks_service(session: SessionDep) -> KonteksService:
    """SEAM: implementasi `KonteksService` berbasis PostgreSQL (riwayat sesi yang sama)."""
    return SqlKonteksService(session, SqlRiwayatService(session))


def get_masalah_service(session: SessionDep) -> MasalahService:
    """SEAM: `MasalahService` PostgreSQL; rujukan uraian tugas & sekolah lewat seam domainnya."""
    return SqlMasalahService(
        session,
        SqlRiwayatService(session),
        SqlUraianTugasService(session),
        SqlSekolahService(session),
    )


def get_alternatif_service(session: SessionDep) -> AlternatifService:
    """SEAM: `AlternatifService` PostgreSQL (riwayat sesi yang sama; jabatan via seam anjab)."""
    return SqlAlternatifService(session, SqlRiwayatService(session), SqlJabatanService(session))


def get_cakupan_jabatan_service(session: SessionDep) -> CakupanJabatanService:
    """SEAM: `CakupanJabatanService` PostgreSQL (riwayat sesi yang sama; jabatan via seam anjab)."""
    return SqlCakupanJabatanService(session, SqlRiwayatService(session), SqlJabatanService(session))


def get_versi_metode_service(session: SessionDep) -> VersiMetodeService:
    """SEAM: `VersiMetodeService` PostgreSQL (riwayat sesi yang sama)."""
    return SqlVersiMetodeService(session, SqlRiwayatService(session))


def get_sesi_service(session: SessionDep) -> SesiService:
    """SEAM: `SesiService` PostgreSQL (riwayat sesi yang sama; sekolah via seam core)."""
    return SqlSesiService(session, SqlRiwayatService(session), SqlSekolahService(session))


def get_bukti_service(session: SessionDep) -> BuktiService:
    """SEAM: `BuktiService` PostgreSQL (riwayat sesi yang sama)."""
    return SqlBuktiService(session, SqlRiwayatService(session))


def get_narasi_sumber_service(session: SessionDep) -> NarasiSumberService:
    """SEAM: `NarasiSumberService` PostgreSQL (teks sumber narasi yang tak dapat diubah)."""
    return SqlNarasiSumberService(session)


def get_riset_protokol_service(session: SessionDep) -> RisetProtokolService:
    """SEAM: `RisetProtokolService` PostgreSQL (protokol riset berversi yang dapat dikunci)."""
    return SqlRisetProtokolService(session)


def get_riset_signoff_service(session: SessionDep) -> RisetSignoffService:
    """SEAM: `RisetSignoffService` PostgreSQL (bukti sign-off PI/etik protokol riset)."""
    return SqlRisetSignoffService(session)


def get_riset_statistik_service(session: SessionDep) -> RisetStatistikService:
    """SEAM: `RisetStatistikService` PostgreSQL (statistik riset dengan verifikasi independen)."""
    return SqlRisetStatistikService(session)


def get_riset_kasus_negatif_service(session: SessionDep) -> RisetKasusNegatifService:
    """SEAM: `RisetKasusNegatifService` PostgreSQL (kasus negatif riset, append-only)."""
    return SqlRisetKasusNegatifService(session)


def get_klarifikasi_service(session: SessionDep) -> KlarifikasiService:
    """SEAM: `KlarifikasiService` PostgreSQL (register klarifikasi narasi, riwayat append-only)."""
    return SqlKlarifikasiService(session)


def get_narasi_metrik_service(session: SessionDep) -> NarasiMetrikService:
    """SEAM: `NarasiMetrikService` PostgreSQL (menit aktif tinjauan dan metrik alur narasi)."""
    return SqlNarasiMetrikService(session)


def get_narasi_service(session: SessionDep) -> NarasiService:
    """SEAM: `NarasiService` PostgreSQL (satu-satunya jalur tulis kasus, versi, dan event)."""
    return SqlNarasiService(session)


def get_permintaan_ai_service(session: SessionDep) -> PermintaanAiService:
    """SEAM: `PermintaanAiService` PostgreSQL (tautan kasus narasi, job, dan `ai_run`)."""
    return SqlPermintaanAiService(session)


def get_ai_gateway(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> AiGateway:
    """SEAM: `AiGateway` di atas sesi request; registri fungsi dari `FUNGSI_TERDAFTAR`."""
    return AiGateway(session, settings)


def get_ai_usulan_service(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> AiUsulanService:
    """SEAM: `AiUsulanService` PostgreSQL (pengajuan umum fungsi AI non-narasi)."""
    return SqlAiUsulanService(session, settings, AiGateway(session, settings))


def get_penilaian_service(session: SessionDep) -> PenilaianService:
    """SEAM: `PenilaianService` PostgreSQL (riwayat sesi yang sama)."""
    return SqlPenilaianService(session, SqlRiwayatService(session))


def get_ringkasan_yayasan_service(session: SessionDep) -> RingkasanYayasanService:
    """SEAM: `RingkasanYayasanService` PostgreSQL (read-model masalah + penilaian)."""
    return SqlRingkasanYayasanService(session)


def get_proses_service(session: SessionDep) -> ProsesService:
    """SEAM: `ProsesService` PostgreSQL (proses & langkah); rujukan sekolah lewat seam core."""
    return SqlProsesService(session, SqlRiwayatService(session), SqlSekolahService(session))


def get_konfirmasi_service(session: SessionDep) -> KonfirmasiService:
    """SEAM: `KonfirmasiService` PostgreSQL (riwayat sesi yang sama)."""
    return SqlKonfirmasiService(session, SqlRiwayatService(session), get_masalah_service(session))


def get_async_job_service(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> AsyncJobService:
    """SEAM: `AsyncJobService` PostgreSQL (job asinkron; flag fitur dibaca dari settings)."""
    return SqlAsyncJobService(session, settings)


def get_ai_run_service(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> AiRunService:
    """SEAM: `AiRunService` PostgreSQL (register run AI; kebijakan simpan masukan dari settings)."""
    return SqlAiRunService(session, settings)


def get_saklar_ai_service(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> SaklarAiService:
    """SEAM: `SaklarAiService` PostgreSQL (kill switch layanan AI; flag env dari settings)."""
    return SqlSaklarAiService(session, settings)


def get_ai_penyedia_service(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> SqlAiPenyediaService:
    """SEAM: pengaturan penyedia AI di PostgreSQL. Rute dilarang memanggil `baca_kunci_api`."""
    return SqlAiPenyediaService(session, settings)


def get_skema_db_service(session: SessionDep) -> SkemaDbService:
    """SEAM: `SkemaDbService` PostgreSQL (pembanding revisi skema, hanya baca)."""
    return SqlSkemaDbService(session)


def get_koreksi_service(session: SessionDep) -> KoreksiService:
    """SEAM: `KoreksiService` PostgreSQL (koreksi langkah append-only; riwayat sesi yang sama)."""
    return SqlKoreksiService(session, SqlRiwayatService(session))


def get_kode_orang_service(session: SessionDep) -> KodeOrangService:
    """SEAM: implementasi `KodeOrangService` berbasis PostgreSQL (riwayat sesi yang sama)."""
    return SqlKodeOrangService(session, SqlRiwayatService(session))


# --- Backup & restore (backlog 025) ---


def get_backup_service() -> BackupService:
    """SEAM: layanan backup/restore basis data (subprocess `pg_dump`/`pg_restore`).

    Bukan seam bertingkat (Protocol + placeholder) seperti provider data lain —
    operasi ini inheren terikat PostgreSQL nyata, sama seperti `db.py` sendiri.
    """
    return BackupService(get_db_settings())


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


def require_tim_kajian(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """Guard otorisasi: hanya anggota grup `tim-kajian` (data register redesain).

    Grup `admin` TIDAK otomatis lolos — data keterangan sekolah bersifat sensitif.
    """
    if GRUP_TIM_KAJIAN not in principal.groups:
        raise ForbiddenError("Akses ditolak: hanya Tim Kajian yang dapat mengakses data redesain.")
    return principal


def require_sekolah_pengisi(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """Guard otorisasi: hanya anggota grup `sekolah-pengisi` (pengisi konfirmasi sekolah).

    `tim-kajian` maupun `admin` TIDAK otomatis lolos — isian konfirmasi adalah suara
    sekolah sendiri, bukan diisikan Tim.
    """
    if GRUP_SEKOLAH_PENGISI not in principal.groups:
        raise ForbiddenError("Akses ditolak: hanya sekolah pengisi yang dapat mengisi konfirmasi.")
    return principal


def require_tim_kajian_atau_pengisi(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """Guard otorisasi: anggota grup `tim-kajian` ATAU `sekolah-pengisi`."""
    if GRUP_TIM_KAJIAN not in principal.groups and GRUP_SEKOLAH_PENGISI not in principal.groups:
        raise ForbiddenError("Akses ditolak: hanya Tim Kajian atau sekolah pengisi.")
    return principal


def get_kode_orang_pemanggil(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> str:
    """Tentukan kode orang pemanggil (get-or-create) untuk pencatatan pelaku riwayat.

    Args:
        principal: Identitas token pemanggil.
        par_service: Seam partisipan untuk resolusi `subject` -> partisipan.
        ko_service: Seam kode orang.

    Returns:
        Kode pseudonim pemanggil (mis. `O-0001`).

    Raises:
        ForbiddenError: Pemanggil tidak punya record partisipan.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        raise ForbiddenError("Akses ditolak: pemanggil tidak terdaftar sebagai partisipan.")
    return ko_service.untuk_partisipan(par.id).kode


def authorize_sekolah_scope(
    principal: Principal,
    sekolah_id: str,
    par_service: PartisipanService,
) -> None:
    """Guard object-level lingkup sekolah: `tim-kajian` selalu lolos; `sekolah-pengisi`
    hanya untuk sekolah partisipannya sendiri.

    Raises:
        ForbiddenError: Grup lain, partisipan tak ditemukan, atau `sekolah_id` partisipan
            kosong/berbeda dari `sekolah_id` yang diakses.
    """
    if GRUP_TIM_KAJIAN in principal.groups:
        return
    if GRUP_SEKOLAH_PENGISI in principal.groups:
        par = par_service.get_by_subject(principal.subject)
        if par is not None and par.sekolah_id is not None and par.sekolah_id == sekolah_id:
            return
    raise ForbiddenError("Akses ditolak: di luar lingkup sekolah Anda.")


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
    if "admin" not in principal.groups:
        par = par_service.get_by_subject(principal.subject)
        if par is None or partisipan_id is None or par.id != partisipan_id:
            raise ForbiddenError("Akses ditolak: Anda bukan pemilik data responden ini.")
    catat_baca_terlindung(principal)


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
    if "admin" not in principal.groups:
        par = par_service.get_by_subject(principal.subject)
        if par is None:
            raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi ini.")
        if par.id != sesi.koordinator_id and not any(
            r.sesi_id == sesi.id for r in rsp_service.list_by_partisipan(par.id)
        ):
            raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi ini.")
    catat_baca_terlindung(principal)


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
    if "admin" not in principal.groups:
        par = par_service.get_by_subject(principal.subject)
        if par is None or not any(
            r.sesi_id == sesi_id for r in rsp_service.list_by_partisipan(par.id)
        ):
            raise ForbiddenError("Akses ditolak: Anda bukan peserta sesi OPM ini.")
    catat_baca_terlindung(principal)


# --- Audit baca data terlindung ---

_audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)

TUJUAN_TIDAK_DINYATAKAN = "TIDAK_DINYATAKAN"
"""Nilai `tujuan` bila klien tidak mengirim header `X-Tujuan-Akses`."""

TUJUAN_MAKS_PANJANG = 200
"""Batas panjang `tujuan` yang dicatat (sisanya dipotong)."""


@dataclass(frozen=True)
class _KonteksAudit:
    """Konteks permintaan GET yang dipakai guard object-level untuk mencatat audit."""

    metode: str
    resource: str
    resource_id: str | None
    tujuan: str


_konteks_audit: ContextVar[_KonteksAudit | None] = ContextVar("konteks_audit", default=None)


def normalisasi_tujuan(nilai: str | None) -> str:
    """Rapikan header tujuan akses untuk log audit.

    Args:
        nilai: Isi header `X-Tujuan-Akses` (boleh `None`).

    Returns:
        Teks yang di-trim dan dipotong `TUJUAN_MAKS_PANJANG` karakter;
        `TIDAK_DINYATAKAN` bila absen atau kosong.
    """
    teks = (nilai or "").strip()[:TUJUAN_MAKS_PANJANG].strip()
    return teks or TUJUAN_TIDAK_DINYATAKAN


def _bangun_konteks(request: Request, tujuan: str | None) -> _KonteksAudit:
    """Turunkan konteks audit dari permintaan (template rute, path param utama, tujuan)."""
    params = request.path_params
    nama_per_nilai = {str(v): k for k, v in params.items()}
    # `route.path` bersifat relatif terhadap router bersarang, jadi template dirakit dari
    # jalur nyata: segmen yang sama dengan nilai path param diganti `{nama}`.
    resource = "/".join(
        "{" + nama_per_nilai[seg] + "}" if seg in nama_per_nilai else seg
        for seg in request.url.path.split("/")
    )
    resource_id = str(next(iter(params.values()))) if params else None
    return _KonteksAudit(request.method, resource, resource_id, normalisasi_tujuan(tujuan))


def _tulis_audit(principal: Principal, konteks: _KonteksAudit) -> None:
    """Tulis satu record `protected_read` (tanpa nama/isi data apa pun)."""
    # `logging.config.fileConfig` (dipanggil Alembic saat migrasi/initdb) menonaktifkan
    # logger yang sudah ada -> record audit hilang senyap. Nyalakan ulang tiap tulis.
    _audit_logger.disabled = False
    _audit_logger.info(
        "protected_read",
        extra={
            "actor": principal.subject,
            "resource": konteks.resource,
            "resource_id": konteks.resource_id,
            "tujuan": konteks.tujuan,
        },
    )


async def siapkan_konteks_audit(
    request: Request,
    tujuan: Annotated[
        str | None,
        Header(
            alias="X-Tujuan-Akses",
            description=(
                "Tujuan akses yang dinyatakan klien (opsional, maks. 200 karakter). "
                "Dicatat di log audit pembacaan data terlindung; absen -> TIDAK_DINYATAKAN."
            ),
        ),
    ] = None,
) -> None:
    """Dependency: simpan konteks permintaan agar guard object-level dapat mencatat audit.

    Dipasang di `READ_GUARDS`. Sengaja `async` agar contextvar yang di-set terlihat oleh
    endpoint sync (threadpool menyalin konteks pemanggil).
    """
    _konteks_audit.set(_bangun_konteks(request, tujuan))


def catat_baca_terlindung(principal: Principal) -> None:
    """Catat audit `protected_read` bila permintaan berjalan adalah GET.

    Dipanggil di dalam guard object-level SETELAH otorisasi lolos. Permintaan non-GET
    (tulis) atau tanpa konteks audit tidak menghasilkan record.
    """
    konteks = _konteks_audit.get()
    if konteks is None or konteks.metode != "GET":
        return
    _tulis_audit(principal, konteks)


def audit_baca_terlindung(
    principal: Annotated[Principal, Depends(get_current_principal)],
    _konteks: Annotated[None, Depends(siapkan_konteks_audit)],
) -> None:
    """Dependency audit untuk rute baca terlindung tanpa guard object-level (redesain).

    Wajib dipasang SETELAH dependency otorisasi di daftar `dependencies` agar penolakan
    403 tidak menghasilkan record. Konteks (termasuk header `X-Tujuan-Akses`) diambil dari
    `siapkan_konteks_audit` (di-cache per permintaan). Hanya mencatat untuk metode GET.
    """
    catat_baca_terlindung(principal)


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

READ_GUARDS = [
    Depends(get_current_principal),
    Depends(rate_limit),
    Depends(siapkan_konteks_audit),
]
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
