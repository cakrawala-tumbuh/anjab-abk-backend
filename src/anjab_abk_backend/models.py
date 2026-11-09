"""Model ORM SQLAlchemy 2.0 (lapisan PENYIMPANAN, bukan kontrak API).

Prinsip backend-skill "skema ≠ model penyimpanan" tetap berlaku: model di sini
adalah representasi tabel PostgreSQL dan TERPISAH dari skema Pydantic. Pemetaan
model → skema dilakukan lewat helper `_to_read` di tiap `services/*_sql.py`.

`naming_convention` membuat nama constraint/index deterministik sehingga migrasi
Alembic (terutama `--autogenerate`) stabil & dapat di-review.

Keunggulan PostgreSQL yang dipakai:
- **`TIMESTAMPTZ`** (`DateTime(timezone=True)`) → datetime aware (UTC), tanpa gotcha
  naive/aware seperti MySQL.
- **`JSONB`** untuk payload idempotency.

Field bertipe daftar (mis. `partisipan.jabatan_tambahan_ids`, `sme_panel.partisipan_ids`,
`tugas_pokok.jabatan_ids`) dimodelkan sebagai tabel relasi 1:N agar query & agregasi
efisien; properti `*_values`/`*_ids` memetakannya kembali ke `list[str]`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from anjab_abk_backend.narasi.schemas.kasus import (
    BasisRelation,
    EventKind,
    NarrativeKind,
    RevisionOrigin,
    StatusNarasi,
)
from anjab_abk_backend.schemas.ai_usulan import PutusanUsulan, SasaranUsulan, TingkatKoreksi
from anjab_abk_backend.schemas.riset_protokol import StatusProtokol
from anjab_abk_backend.schemas.riset_statistik import StatusStatistik

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base deklaratif; semua model mewarisi `metadata` ini (dipakai Alembic)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _utcnow() -> datetime:
    """Timestamp UTC aware (kolom memakai TIMESTAMPTZ)."""
    return datetime.now(UTC)


def _ts(**kw: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, **kw)


# ======================================================================================
# Idempotency
# ======================================================================================


class IdempotencyRecord(Base):
    """Tabel `idempotency_keys` — realisasi seam `IdempotencyStore` di PostgreSQL."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AsyncJobModel(Base):
    """Tabel `async_job` — job asinkron generik lintas fitur (status dikelola service)."""

    __tablename__ = "async_job"
    __table_args__ = (Index("ix_async_job_fitur_status", "fitur", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fitur: Mapped[str] = mapped_column(String(50), nullable=False)
    jenis: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    percobaan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dibuat_oleh: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class AiRunModel(Base):
    """Tabel `ai_run` — register run AI (ModelRun_ID, hash, Protocol_ID)."""

    __tablename__ = "ai_run"
    __table_args__ = (Index("ix_ai_run_fungsi_status_qa", "fungsi", "status_qa"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fungsi: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_diminta: Mapped[str] = mapped_column(String(100), nullable=False)
    model_dilayani: Mapped[str | None] = mapped_column(String(100), nullable=True)
    penyedia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    protocol_id: Mapped[str] = mapped_column(String(300), nullable=False)
    input_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sumber: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    masukan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    keluaran: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status_qa: Mapped[str] = mapped_column(String(20), nullable=False)
    kode_qa: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dibuat_oleh: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = _ts()
    selesai_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiSaklarEventModel(Base):
    """Tabel `ai_saklar_event` — kill switch layanan AI, append-only (tak pernah diubah)."""

    __tablename__ = "ai_saklar_event"
    __table_args__ = (Index("ix_ai_saklar_event_layanan_created_at", "layanan", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layanan: Mapped[str] = mapped_column(String(50), nullable=False)
    aksi: Mapped[str] = mapped_column(String(10), nullable=False)
    alasan: Mapped[str] = mapped_column(Text, nullable=False)
    aktor: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()


class AiPenyediaPengaturanModel(Base):
    """Tabel `ai_penyedia_pengaturan` — satu baris (`id` = `TUNGGAL`) pilihan penyedia AI.

    `kredensial_terenkripsi` berisi token Fernet kunci API; tidak pernah teks asli.
    """

    __tablename__ = "ai_penyedia_pengaturan"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effort: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kredensial_terenkripsi: Mapped[str | None] = mapped_column(Text, nullable=True)
    kredensial_akhiran: Mapped[str | None] = mapped_column(String(4), nullable=True)
    diperbarui_oleh: Mapped[str | None] = mapped_column(String(254), nullable=True)
    updated_at: Mapped[datetime] = _ts()

    def __repr__(self) -> str:
        """Representasi tanpa kolom kredensial."""
        return f"<AiPenyediaPengaturanModel id={self.id!r} mode={self.mode!r}>"


class AiPenyediaEventModel(Base):
    """Tabel `ai_penyedia_event` — riwayat perubahan pengaturan penyedia, append-only."""

    __tablename__ = "ai_penyedia_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aksi: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effort: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kredensial_akhiran: Mapped[str | None] = mapped_column(String(4), nullable=True)
    alasan: Mapped[str] = mapped_column(Text, nullable=False)
    aktor: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()


# ======================================================================================
# Core
# ======================================================================================


class JenjangPendidikanModel(Base):
    __tablename__ = "jenjang_pendidikan"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MataPelajaranModel(Base):
    __tablename__ = "mata_pelajaran"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(String(200), nullable=False)
    kelompok: Mapped[str] = mapped_column(String(30), nullable=False)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)


class SekolahModel(Base):
    __tablename__ = "sekolah"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str] = mapped_column(String(200), nullable=False)
    jenjang_pendidikan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    npsn: Mapped[str | None] = mapped_column(String(8), nullable=True, unique=True)
    kota: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Cabang (Bandung/Semarang) — enum aplikasi, bukan FK, nullable disengaja:
    # "belum diketahui" tidak boleh tertukar dengan "salah cabang" (backlog
    # `anjab-abk-backend#40`). Sumber tunggal cabang seorang PARTISIPAN, lewat
    # `partisipan.sekolah_id` — lihat `schemas/common.py::Cabang`.
    cabang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts(index=True)


class PartisipanModel(Base):
    __tablename__ = "partisipan"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    sekolah_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    jabatan_utama_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    masa_kerja_tahun: Mapped[int] = mapped_column(Integer, nullable=False)
    masa_kerja_bulan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mata_pelajaran_utama_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Menyimpan klaim `sub` token OIDC (identitas yang dicocokkan saat login). Dengan
    # `sub_mode=user_email` di provider Authentik, nilainya adalah email — sehingga
    # lebarnya disamakan dengan kolom `email` (254) agar tidak terpotong.
    authentik_user_id: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    created_at: Mapped[datetime] = _ts(index=True)

    jabatan_tambahan: Mapped[list[PartisipanJabatanTambahanModel]] = relationship(
        back_populates="partisipan", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def jabatan_tambahan_ids(self) -> list[str]:
        return [j.jabatan_id for j in sorted(self.jabatan_tambahan, key=lambda x: x.id)]


class PartisipanJabatanTambahanModel(Base):
    __tablename__ = "partisipan_jabatan_tambahan"
    __table_args__ = (UniqueConstraint("partisipan_id", "jabatan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partisipan_id: Mapped[str] = mapped_column(
        ForeignKey("partisipan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False)

    partisipan: Mapped[PartisipanModel] = relationship(back_populates="jabatan_tambahan")


# ======================================================================================
# ANJAB
# ======================================================================================


class JabatanModel(Base):
    __tablename__ = "jabatan"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(String(200), nullable=False)
    jenis: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_kerja_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts(index=True)


class SMEPanelModel(Base):
    __tablename__ = "sme_panel"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    koordinator_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts(index=True)

    anggota: Mapped[list[SMEPanelAnggotaModel]] = relationship(
        back_populates="panel", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def partisipan_ids(self) -> list[str]:
        return [a.partisipan_id for a in sorted(self.anggota, key=lambda x: x.id)]


class SMEPanelAnggotaModel(Base):
    __tablename__ = "sme_panel_anggota"
    __table_args__ = (UniqueConstraint("panel_id", "partisipan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[str] = mapped_column(
        ForeignKey("sme_panel.id", ondelete="CASCADE"), nullable=False, index=True
    )
    partisipan_id: Mapped[str] = mapped_column(String(40), nullable=False)

    panel: Mapped[SMEPanelModel] = relationship(back_populates="anggota")


# ======================================================================================
# DCS (Dimension Classification Survey)
# ======================================================================================


class DcsSubSkalaModel(Base):
    __tablename__ = "dcs_subskala"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DcsItemModel(Base):
    __tablename__ = "dcs_item"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    subskala_kode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sub_dimensi: Mapped[str] = mapped_column(String(150), nullable=False)
    pernyataan: Mapped[str] = mapped_column(Text, nullable=False)
    arah: Mapped[str] = mapped_column(String(4), nullable=False)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DcsInstrumenModel(Base):
    """Instrumen DCS singleton — satu baris tetap (`id='dcs'`), tanpa sesi."""

    __tablename__ = "dcs_instrumen"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class DcsRespondenModel(Base):
    __tablename__ = "dcs_responden"
    __table_args__ = (UniqueConstraint("partisipan_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jabatan_label: Mapped[str] = mapped_column(String(200), nullable=False)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sudah_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)
    item_bank_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DcsJawabanModel(Base):
    __tablename__ = "dcs_jawaban"
    __table_args__ = (UniqueConstraint("responden_id", "item_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("dcs_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(20), nullable=False)
    skor_raw: Mapped[int] = mapped_column(Integer, nullable=False)


# ======================================================================================
# WCP (Work Characteristics Profile)
# ======================================================================================


class WcpDimensiModel(Base):
    __tablename__ = "wcp_dimensi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WcpItemModel(Base):
    __tablename__ = "wcp_item"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    dimensi_kode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    indikator_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    indikator_label: Mapped[str] = mapped_column(String(200), nullable=False)
    pernyataan: Mapped[str] = mapped_column(Text, nullable=False)
    reverse_type: Mapped[str] = mapped_column(String(10), nullable=False)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WcpInstrumenModel(Base):
    """Instrumen WCP singleton — satu baris tetap (`id='wcp'`), tanpa sesi."""

    __tablename__ = "wcp_instrumen"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class WcpRespondenModel(Base):
    __tablename__ = "wcp_responden"
    __table_args__ = (UniqueConstraint("partisipan_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jabatan_label: Mapped[str] = mapped_column(String(200), nullable=False)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sudah_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)
    item_bank_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WcpJawabanModel(Base):
    __tablename__ = "wcp_jawaban"
    __table_args__ = (UniqueConstraint("responden_id", "item_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("wcp_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(20), nullable=False)
    skor_raw: Mapped[int] = mapped_column(Integer, nullable=False)


# ======================================================================================
# Task Inventory
# ======================================================================================


class TiTugasPokokModel(Base):
    __tablename__ = "ti_tugas_pokok"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    created_at: Mapped[datetime] = _ts(index=True)

    jabatan_links: Mapped[list[TiTugasPokokJabatanModel]] = relationship(
        back_populates="tugas_pokok", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def jabatan_ids(self) -> list[str]:
        return [j.jabatan_id for j in sorted(self.jabatan_links, key=lambda x: x.id)]


class TiTugasPokokJabatanModel(Base):
    __tablename__ = "ti_tugas_pokok_jabatan"
    __table_args__ = (UniqueConstraint("tugas_pokok_id", "jabatan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tugas_pokok_id: Mapped[str] = mapped_column(
        ForeignKey("ti_tugas_pokok.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    tugas_pokok: Mapped[TiTugasPokokModel] = relationship(back_populates="jabatan_links")


class TiDetilTugasModel(Base):
    __tablename__ = "ti_detil_tugas"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nama: Mapped[str] = mapped_column(String(300), nullable=False)
    tugas_pokok_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_at: Mapped[datetime] = _ts(index=True)

    jabatan_links: Mapped[list[TiDetilTugasJabatanModel]] = relationship(
        back_populates="detil_tugas", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def jabatan_ids(self) -> list[str]:
        return [j.jabatan_id for j in sorted(self.jabatan_links, key=lambda x: x.id)]


class TiDetilTugasJabatanModel(Base):
    __tablename__ = "ti_detil_tugas_jabatan"
    __table_args__ = (UniqueConstraint("detil_tugas_id", "jabatan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detil_tugas_id: Mapped[str] = mapped_column(
        ForeignKey("ti_detil_tugas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    detil_tugas: Mapped[TiDetilTugasModel] = relationship(back_populates="jabatan_links")


class TiUraianTugasModel(Base):
    """Entitas kanonik uraian tugas (task statement) — 1 baris = 1 pernyataan tugas.

    Sejak refactor m2m via association object (backlog `anjab-abk-backend#23`), kolom
    per-jabatan (`kode`, `unit`, `jabatan_id`, `urutan`, `tugas_pokok_id`,
    `detil_tugas_id`, `std_*`) dipindah ke `TiUraianTugasJabatanModel` lewat
    `jabatan_links`. Migrasi awal (revisi Alembic pendampingnya) bersifat 1:1
    non-lossy — setiap baris lama menjadi tepat satu kanonik + satu link; dedup/
    kanonikalisasi baris `uraian` yang identik teksnya adalah pekerjaan terpisah
    yang menyusul.
    """

    __tablename__ = "ti_uraian_tugas"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    uraian: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts(index=True)

    jabatan_links: Mapped[list[TiUraianTugasJabatanModel]] = relationship(
        back_populates="uraian_tugas", cascade="all, delete-orphan", lazy="selectin"
    )


class TiUraianTugasJabatanModel(Base):
    """Association object uraian tugas ↔ jabatan — memikul seluruh atribut per-jabatan.

    Sebelum refactor `anjab-abk-backend#23`, kolom-kolom ini hidup langsung di
    `TiUraianTugasModel` (relasi 1:N tunggal ke jabatan). Dipindah ke tabel terpisah
    agar satu uraian tugas kanonik bisa suatu saat dipakai banyak jabatan tanpa
    duplikasi fisik teksnya — meniru pola `TiTugasPokokJabatanModel`/
    `TiDetilTugasJabatanModel` yang sudah m2m sejak awal.
    """

    __tablename__ = "ti_uraian_tugas_jabatan"
    __table_args__ = (UniqueConstraint("uraian_tugas_id", "jabatan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uraian_tugas_id: Mapped[str] = mapped_column(
        ForeignKey("ti_uraian_tugas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tugas_pokok_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detil_tugas_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # Nilai standar CalHR — prefill isian Tahap 3. Semua nullable: master lama
    # tanpa nilai standar tetap valid, dan partisipan mengisi dari nol seperti sebelumnya.
    std_sumber_bukti: Mapped[str | None] = mapped_column(String(20), nullable=True)
    std_kondisi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    std_frekuensi_teks: Mapped[str | None] = mapped_column(String(100), nullable=True)
    std_durasi_per_kali: Mapped[str | None] = mapped_column(String(100), nullable=True)
    std_jam_per_minggu: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_peak4w_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_va_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Nilai standar OPM (backlog `anjab-abk-backend#33`) — skala 1-5, sumber sheet
    # `05_Raw_Task_Migration` (kolom Importance/Frequency/Criticality). Prefiks
    # `std_opm_` sengaja dipakai agar tidak tertukar dengan `std_frekuensi_teks`
    # (frekuensi teks bebas untuk ABK) — makna & format keduanya berbeda. Semua
    # nullable: master lama tanpa nilai standar OPM tetap valid.
    std_opm_importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    std_opm_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    std_opm_criticality: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uraian_tugas: Mapped[TiUraianTugasModel] = relationship(back_populates="jabatan_links")


class TiSesiModel(Base):
    __tablename__ = "ti_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    cabang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    koordinator_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # task_terpilih: None sampai di-freeze (TAHAP2→TAHAP3). `task_frozen` membedakan
    # "belum di-freeze" (None) vs "di-freeze tapi kosong" ([]).
    task_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _ts(index=True)

    task_terpilih_links: Mapped[list[TiSesiTaskTerpilihModel]] = relationship(
        back_populates="sesi", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def task_terpilih(self) -> list[str] | None:
        if not self.task_frozen:
            return None
        return sorted(t.task_kode for t in self.task_terpilih_links)


class TiSesiTaskTerpilihModel(Base):
    __tablename__ = "ti_sesi_task_terpilih"
    __table_args__ = (UniqueConstraint("sesi_id", "task_kode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)

    sesi: Mapped[TiSesiModel] = relationship(back_populates="task_terpilih_links")


class TiRespondenModel(Base):
    """Satu baris responden Task Inventory dalam satu sesi.

    `UniqueConstraint("sesi_id", "partisipan_id")` (`uq_ti_responden_sesi_partisipan`)
    menegakkan **satu partisipan hanya satu responden per sesi** di lapisan basis data
    (backlog `anjab-abk-backend#29`) — jaring pengaman terakhir setelah pengecekan
    eksplisit di `SqlTiRespondenService.create()`. `partisipan_id = NULL` (responden
    manual tanpa partisipan) TIDAK dibatasi constraint ini: PostgreSQL memperlakukan
    NULL sebagai distinct pada unique constraint, sehingga boleh berulang.
    """

    __tablename__ = "ti_responden"
    __table_args__ = (
        UniqueConstraint("sesi_id", "partisipan_id", name="uq_ti_responden_sesi_partisipan"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    tahap1_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tahap1_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tahap3_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tahap3_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _ts(index=True)


class TiSeleksiModel(Base):
    __tablename__ = "ti_seleksi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("ti_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _ts()


class TiTahap2Model(Base):
    __tablename__ = "ti_tahap2"
    __table_args__ = (UniqueConstraint("sesi_id", "task_kode"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    disetujui: Mapped[bool] = mapped_column(Boolean, nullable=False)
    submitted_at: Mapped[datetime] = _ts()


class TiDetailModel(Base):
    __tablename__ = "ti_detail"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("ti_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    # Lima kolom CalHR inti berikut nullable sejak backlog #38: draft parsial (PUT
    # .../detail) menyimpan baris sebelum seluruh field terisi; kelengkapan digerbang di
    # submit() (services/detail.py + detail_sql.py), bukan di sini.
    sumber_bukti: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kondisi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    frekuensi_teks: Mapped[str | None] = mapped_column(String(100), nullable=True)
    durasi_per_kali: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jam_per_minggu: Mapped[float] = mapped_column(Float, nullable=False)
    peak4w_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    va_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # True = partisipan menerima nilai standar master apa adanya.
    # False = ia mengubah minimal satu komponen. Task yang masternya tidak punya
    # nilai standar tetap True (tidak ada standar untuk dibantah).
    setuju_standar: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class TiUsulanTaskModel(Base):
    """Usulan uraian tugas baru dari responden Tahap 1 (backlog `anjab-abk-backend#26`).

    Dicatat per orang di bawah tugas pokok (dan opsional detil tugas) pilihannya saat
    tugas yang ia kerjakan tidak ada di katalog Tahap 1 (`ti_uraian_tugas*`). Usulan
    TIDAK menyentuh katalog master — `tugas_pokok_id`/`detil_tugas_id` sengaja BUKAN
    `ForeignKey` (nama induknya diresolusi live saat baca via
    `TugasPokokService`/`DetilTugasService`, lihat `taskinv/services/usulan_sql.py`).
    Tanpa `UniqueConstraint`: dua orang boleh mengusulkan tugas yang mirip, koordinator
    Tahap 2 yang memutuskan (`disetujui`) — pekerjaan review & materialisasi
    `task_kode` menyusul di `anjab-abk-backend#27`.
    """

    __tablename__ = "ti_usulan_task"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("ti_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("ti_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tugas_pokok_id: Mapped[str] = mapped_column(String(40), nullable=False)
    detil_tugas_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    uraian: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL = belum diputuskan koordinator Tahap 2.
    disetujui: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Diisi item lanjutan (anjab-abk-backend#27) saat materialisasi ke katalog.
    task_kode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


# ======================================================================================
# Time Study
# ======================================================================================


class TsPenugasanModel(Base):
    """Penugasan Time Study — gerbang akses per partisipan (tanpa sesi)."""

    __tablename__ = "ts_penugasan"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    partisipan_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class TsLogModel(Base):
    __tablename__ = "ts_log"
    __table_args__ = (UniqueConstraint("partisipan_id", "tanggal"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    partisipan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    waktu_masuk: Mapped[str] = mapped_column(String(5), nullable=False)
    waktu_keluar: Mapped[str] = mapped_column(String(5), nullable=False)
    day_color: Mapped[str] = mapped_column(String(10), nullable=False)
    menit_core: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    menit_character: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    menit_improve: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    menit_strategic: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    menit_admin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    menit_recovery: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


# ======================================================================================
# OPM (Rating Tugas — Importance/Frequency/Criticality)
# ======================================================================================


class OpmSesiModel(Base):
    """Satu sesi rating OPM, terikat pada satu `TiSesiModel` sumber snapshot task.

    `cabang` DITURUNKAN dari `ti_sesi.cabang` oleh `SqlOpmSesiService.create()` —
    bukan input pengguna (`OpmSesiCreate` tidak punya field ini). `jabatan_id`
    kehilangan `unique=True` sejak backlog `anjab-abk-backend#37`: satu jabatan
    kini boleh punya sesi OPM Bandung DAN Semarang berdampingan. Uniqueness
    `(jabatan_id, cabang)` ditegakkan di APLIKASI (bukan constraint DB) karena
    `cabang` nullable dan PostgreSQL memperlakukan `NULL` sebagai distinct pada
    unique constraint — lihat `SqlOpmSesiService.create()` langkah pre-check.
    """

    __tablename__ = "opm_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    ti_sesi_id: Mapped[str] = mapped_column(String(40), nullable=False)
    cabang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    periode: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)

    task_links: Mapped[list[OpmSesiTaskModel]] = relationship(
        back_populates="sesi", cascade="all, delete-orphan", lazy="selectin"
    )


class OpmSesiTaskModel(Base):
    """Snapshot beku satu task terpilih Task Inventory di dalam sesi OPM.

    Dibekukan sekali oleh `SqlOpmSesiService.create()` dari `ti_uraian_tugas_jabatan`
    (via `task_kode`) — termasuk tiga kolom `std_*` di bawah, yang disalin dari
    `TiUraianTugasJabatanModel.std_opm_importance`/`std_opm_frequency`/
    `std_opm_criticality` (backlog `anjab-abk-backend#33`). Nilai beku, TIDAK pernah
    disegarkan ulang setelah sesi OPM dibuat — perubahan katalog TI berikutnya tidak
    memengaruhi sesi OPM yang sudah ada.
    """

    __tablename__ = "opm_sesi_task"
    __table_args__ = (UniqueConstraint("sesi_id", "task_kode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("opm_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    uraian_tugas: Mapped[str] = mapped_column(Text, nullable=False)
    tugas_pokok: Mapped[str] = mapped_column(String(300), nullable=False)
    detil_tugas: Mapped[str | None] = mapped_column(String(300), nullable=True)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Nilai standar OPM (backlog `anjab-abk-backend#33`/`#34`) — skala 1-5, DISALIN
    # (bukan direferensikan) dari `ti_uraian_tugas_jabatan.std_opm_*` saat sesi OPM
    # dibuat. Semua nullable: task yang kodenya tidak punya nilai standar di katalog
    # (mis. hasil materialisasi usulan Tahap 1) tetap menghasilkan baris snapshot,
    # hanya dengan ketiganya `NULL` — bukan error. Tanpa prefiks `opm_` karena tabel
    # ini sudah milik OPM (beda dari katalog TI yang perlu `std_opm_` untuk
    # membedakannya dari `std_frekuensi_teks`).
    std_importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    std_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    std_criticality: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sesi: Mapped[OpmSesiModel] = relationship(back_populates="task_links")


class OpmSesiPengecualianModel(Base):
    """Register pengecualian satu sesi OPM (backlog `anjab-abk-backend#69`, A9).

    Mencatat ketidakcocokan TI-OPM berkode alasan alih-alih membuangnya diam-diam:
    `TI_DETAIL_UNMATCHED` (kode terpilih TI tak ada di katalog saat snapshot),
    `OPM_STD_MISSING` (task snapshot tanpa ketiga nilai standar) dan
    `OPM_RATING_MISSING` (task tanpa satu pun rating saat analisis). Register hanya
    MENCATAT — tidak pernah mengisi nilai standar/rating secara otomatis. Unik per
    `(sesi_id, task_kode, alasan)` sehingga pencatatan ulang bersifat idempoten.
    `status` selalu `OPEN` pada item ini (keputusan reviewer di luar lingkup).
    """

    __tablename__ = "opm_sesi_pengecualian"
    __table_args__ = (
        UniqueConstraint(
            "sesi_id", "task_kode", "alasan", name="uq_opm_sesi_pengecualian_sesi_task_alasan"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("opm_sesi.id", ondelete="CASCADE", name="fk_opm_sesi_pengecualian_sesi"),
        nullable=False,
        index=True,
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    alasan: Mapped[str] = mapped_column(String(40), nullable=False)
    keterangan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN", server_default="OPEN"
    )
    created_at: Mapped[datetime] = _ts()


class OpmRespondenModel(Base):
    __tablename__ = "opm_responden"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("opm_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jabatan_label: Mapped[str] = mapped_column(String(200), nullable=False)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sudah_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class OpmJawabanModel(Base):
    __tablename__ = "opm_jawaban"
    __table_args__ = (UniqueConstraint("responden_id", "task_kode"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    responden_id: Mapped[str] = mapped_column(
        ForeignKey("opm_responden.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_kode: Mapped[str] = mapped_column(String(20), nullable=False)
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criticality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)


# ======================================================================================
# Redesain Pekerjaan
# ======================================================================================


class RedesainRiwayatModel(Base):
    """Riwayat perubahan append-only seluruh entitas redesain.

    Tidak ada jalur update/delete di service maupun API. `pelaku_kode_orang` NULL
    hanya untuk seed/sistem (diisi mulai item pemilik kode orang).
    """

    __tablename__ = "redesain_riwayat"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entitas: Mapped[str] = mapped_column(String(40), nullable=False)
    entitas_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    aksi: Mapped[str] = mapped_column(String(40), nullable=False)
    nilai_sebelum: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    nilai_sesudah: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pelaku_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    waktu: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )


KODE_ORANG_SEQ = Sequence("redesain_kode_orang_seq")
"""Sequence PostgreSQL sumber nomor `kode` kode orang (dibuat di revisi Alembic)."""


class RedesainKodeOrangModel(Base):
    """Peta kode pseudonim (`O-0001`) ke partisipan; baris tanpa partisipan = narasumber.

    Tidak pernah dihapus/didaur ulang. Hanya terbaca `tim-kajian`.
    """

    __tablename__ = "redesain_kode_orang"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    partisipan_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("partisipan.id"), nullable=True, unique=True
    )
    keterangan_peran: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class RedesainKonteksModel(Base):
    """Katalog konteks usulan redesain (K-01...K-14 paket v1.3).

    Tidak pernah dihapus; konteks dinonaktifkan lewat `aktif=False`. `gelombang`
    bertipe `String(40)` tanpa CHECK (divalidasi skema `Gelombang`).
    """

    __tablename__ = "redesain_konteks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    tema: Mapped[str] = mapped_column(String(200), nullable=False)
    gelombang: Mapped[str] = mapped_column(String(40), nullable=False)
    ruang_dugaan: Mapped[str] = mapped_column(Text, nullable=False)
    sumber_draft: Mapped[str] = mapped_column(Text, nullable=False)
    batas_pemeriksaan: Mapped[str] = mapped_column(Text, nullable=False)
    aktif: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainMasalahModel(Base):
    """Hipotesis masalah lokal per sekolah/periode (sheet MASALAH paket v1.3).

    `kode` dibangkitkan sistem (`M-K01-01`). `sekolah_id` NULL = "Belum ditetapkan"
    (teks bebasnya di `keterangan_sekolah`). `status_awal` membeku begitu
    `status_awal_dibekukan_pada` terisi (diisi alur konfirmasi sekolah, BE-6a).
    `status_awal`/`gelombang` bertipe `String(40)` tanpa CHECK (divalidasi skema).
    `eskalasi_pada` diisi saat konfirmasi pertama ber-`indikasi_risiko="Ada indikasi"`
    terkirim (penanda untuk Tim; tidak ada notifikasi keluar sistem).
    `sumber_konfirmasi_id` terisi bila masalah diangkat Tim dari `masalah_baru` sebuah
    konfirmasi (BE-6b). Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_masalah"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    konteks_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_konteks.id"), nullable=False, index=True
    )
    sekolah_id: Mapped[str | None] = mapped_column(
        ForeignKey("sekolah.id", ondelete="SET NULL"), nullable=True, index=True
    )
    keterangan_sekolah: Mapped[str | None] = mapped_column(String(200), nullable=True)
    periode_acuan: Mapped[str] = mapped_column(String(100), nullable=False)
    periode_pasti: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    rumusan_hipotesis: Mapped[str] = mapped_column(Text, nullable=False)
    sumber_awal_keterbatasan: Mapped[str] = mapped_column(Text, nullable=False)
    status_awal: Mapped[str] = mapped_column(String(40), nullable=False)
    gelombang: Mapped[str] = mapped_column(String(40), nullable=False)
    penjelasan_alternatif: Mapped[str | None] = mapped_column(Text, nullable=True)
    pic_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dibuka_untuk_konfirmasi: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status_awal_dibekukan_pada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    eskalasi_pada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sumber_konfirmasi_id: Mapped[str | None] = mapped_column(
        ForeignKey("redesain_konfirmasi.id", name="fk_redesain_masalah_sumber_konfirmasi"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainMasalahUraianTugasModel(Base):
    """Tautan masalah redesain ↔ uraian tugas katalog Task Inventory (PK gabungan).

    Kedua FK `ON DELETE CASCADE`: masalah atau uraian tugas yang terhapus ikut
    melepaskan tautannya.
    """

    __tablename__ = "redesain_masalah_uraian_tugas"

    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id", ondelete="CASCADE"), primary_key=True
    )
    uraian_tugas_id: Mapped[str] = mapped_column(
        # Nama eksplisit: hasil naming_convention (64 karakter) melewati batas 63 PostgreSQL.
        ForeignKey(
            "ti_uraian_tugas.id",
            ondelete="CASCADE",
            name="fk_redesain_masalah_ut_uraian_tugas_id_ti_uraian_tugas",
        ),
        primary_key=True,
        index=True,
    )


class RedesainProsesModel(Base):
    """Proses kerja (Process_ID, sheet ALUR) untuk satu masalah di SATU sekolah.

    `kode` dibangkitkan sistem secara global (`P-001`). `sekolah_id` wajib: proses
    sekolah B tidak boleh dicatat sebagai fakta dari catatan sekolah A (`ALUR!A3`).
    Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_proses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id"), nullable=False, index=True
    )
    sekolah_id: Mapped[str] = mapped_column(ForeignKey("sekolah.id"), nullable=False, index=True)
    periode: Mapped[str] = mapped_column(String(100), nullable=False)
    nama_proses: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainLangkahModel(Base):
    """Langkah (Step_ID) sebuah proses redesain; kode `<kode proses>-S01`, `-S02`, ...

    `pelaksana`/`pemeriksa_pemutus` berisi jabatan/peran, bukan nama orang (validasi
    manusia). `status_langkah` bertipe `String(40)` tanpa CHECK (divalidasi skema
    `StatusLangkah`). Langkah yang tak berlaku diberi status `Tidak berlaku`, tidak dihapus.
    """

    __tablename__ = "redesain_langkah"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proses_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_proses.id"), nullable=False, index=True
    )
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False)
    tahap: Mapped[str] = mapped_column(String(200), nullable=False)
    pemicu_input: Mapped[str] = mapped_column(Text, nullable=False)
    pelaksana: Mapped[str] = mapped_column(String(200), nullable=False)
    pekerjaan_sistem: Mapped[str] = mapped_column(Text, nullable=False)
    keluaran_penerima: Mapped[str] = mapped_column(Text, nullable=False)
    pemeriksa_pemutus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hambatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_langkah: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainBuktiModel(Base):
    """Bukti per klaim untuk satu masalah redesain (sheet BUKTI), opsional menunjuk satu langkah.

    Bukti berupa rujukan teks (lokasi/nama dokumen), bukan berkas unggahan. `kode`
    dibangkitkan sistem (`B-0001`, global). `jenis`/`independen`/`status_pemeriksaan` bertipe
    `String(40)` tanpa CHECK (divalidasi skema). `*_kode_orang` adalah pseudonim (bukan FK).
    Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_bukti"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id", name="fk_redesain_bukti_masalah"),
        nullable=False,
        index=True,
    )
    langkah_id: Mapped[str | None] = mapped_column(
        ForeignKey("redesain_langkah.id", name="fk_redesain_bukti_langkah"),
        nullable=True,
        index=True,
    )
    unit_periode: Mapped[str] = mapped_column(String(200), nullable=False)
    jenis: Mapped[str] = mapped_column(String(40), nullable=False)
    pembuat_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pembuat_peran: Mapped[str | None] = mapped_column(String(200), nullable=True)
    independen: Mapped[str] = mapped_column(String(40), nullable=False)
    klaim_didukung: Mapped[str] = mapped_column(Text, nullable=False)
    klaim_tidak_didukung: Mapped[str | None] = mapped_column(Text, nullable=True)
    tanggal_versi_lokasi: Mapped[str] = mapped_column(Text, nullable=False)
    status_pemeriksaan: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum diperiksa", server_default="Belum diperiksa"
    )
    pemeriksa_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alasan: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan_privasi_gap: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainAlternatifModel(Base):
    """Alternatif redesain untuk satu masalah (sheet ALTERNATIF; BUKAN bagian skor K1-K4).

    `kode` dibangkitkan sistem (`U-001`, global). Pihak asal/penerima berupa jabatan (FK
    `jabatan.id`), bukan orang. `status_telaah` hanya berubah lewat payload eksplisit Tim.
    `opsi`/`gap_penerima`/`status_telaah` bertipe `String(40)` tanpa CHECK (divalidasi skema).
    `pemutus_kode_orang` adalah pseudonim (bukan FK). Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_alternatif"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id", name="fk_redesain_alternatif_masalah"),
        nullable=False,
        index=True,
    )
    opsi: Mapped[str] = mapped_column(String(40), nullable=False)
    alur_kini_vs_usulan: Mapped[str] = mapped_column(Text, nullable=False)
    pihak_asal_jabatan_id: Mapped[str | None] = mapped_column(
        ForeignKey("jabatan.id", name="fk_redesain_alternatif_pihak_asal"), nullable=True
    )
    pihak_penerima_jabatan_id: Mapped[str | None] = mapped_column(
        ForeignKey("jabatan.id", name="fk_redesain_alternatif_pihak_penerima"), nullable=True
    )
    komitmen_penerima: Mapped[str | None] = mapped_column(Text, nullable=True)
    jadwal_puncak: Mapped[str | None] = mapped_column(Text, nullable=True)
    keterampilan_akses: Mapped[str | None] = mapped_column(Text, nullable=True)
    tambahan_bersih: Mapped[str | None] = mapped_column(Text, nullable=True)
    risiko_layanan: Mapped[str | None] = mapped_column(Text, nullable=True)
    gap_penerima: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum tahu", server_default="Belum tahu"
    )
    status_telaah: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum ditelaah", server_default="Belum ditelaah"
    )
    pemutus_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    keputusan: Mapped[str | None] = mapped_column(Text, nullable=True)
    prasyarat_monitoring: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan_versi_bukti: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainSesiModel(Base):
    """Keterlibatan satu orang pada satu sesi kegiatan redesain (sheet SESI; BUKAN Time Study).

    Satu baris = satu orang (`kode_orang`, pseudonim) × satu sesi (`kode_sesi`, dibagi
    semua peserta satu kegiatan, diisi Tim). Pasangan keduanya unik. Menit dicatat sekali
    per baris. `status_izin` hanya informasi — tidak memblokir apa pun, termasuk
    `Tidak diotorisasi`. `jenis_kegiatan`/`status_izin` bertipe `String(40)` tanpa CHECK
    (divalidasi skema). `kode_orang`/`pic_kode_orang` bukan FK. Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_sesi"
    __table_args__ = (
        UniqueConstraint("kode_sesi", "kode_orang", name="uq_redesain_sesi_kode_sesi_kode_orang"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode_sesi: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    kode_orang: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sekolah_id: Mapped[str | None] = mapped_column(
        ForeignKey("sekolah.id", ondelete="SET NULL", name="fk_redesain_sesi_sekolah"),
        nullable=True,
        index=True,
    )
    peran: Mapped[str] = mapped_column(String(200), nullable=False)
    jenis_kegiatan: Mapped[str] = mapped_column(String(40), nullable=False)
    menit_rencana: Mapped[int | None] = mapped_column(Integer, nullable=True)
    menit_disepakati: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waktu_kalender: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_izin: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum ditetapkan", server_default="Belum ditetapkan"
    )
    versi_izin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pic_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tindak_lanjut: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainSesiMasalahModel(Base):
    """Tautan sesi partisipasi ↔ masalah redesain (PK gabungan; kedua FK `ON DELETE CASCADE`)."""

    __tablename__ = "redesain_sesi_masalah"

    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_sesi.id", ondelete="CASCADE", name="fk_redesain_sesi_masalah_sesi"),
        primary_key=True,
    )
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey(
            "redesain_masalah.id", ondelete="CASCADE", name="fk_redesain_sesi_masalah_masalah"
        ),
        primary_key=True,
        index=True,
    )


class RedesainKoreksiLangkahModel(Base):
    """Koreksi pihak pemeriksa atas satu langkah ALUR (append-only; sheet ALUR!N).

    Disimpan terpisah dari langkah sehingga keterangan tiap pihak tidak saling menimpa.
    `konfirmasi_id` NULL bila ditulis Tim Kajian. `kode_orang` adalah pseudonim penulis
    (bukan FK). Tidak ada operasi ubah/hapus.
    """

    __tablename__ = "redesain_koreksi_langkah"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    langkah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_langkah.id", name="fk_redesain_koreksi_langkah_langkah"),
        nullable=False,
        index=True,
    )
    konfirmasi_id: Mapped[str | None] = mapped_column(
        ForeignKey("redesain_konfirmasi.id", name="fk_redesain_koreksi_langkah_konfirmasi"),
        nullable=True,
    )
    kode_orang: Mapped[str] = mapped_column(String(20), nullable=False)
    isi: Mapped[str] = mapped_column(Text, nullable=False)
    waktu: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class RedesainKonfirmasiModel(Base):
    """Konfirmasi sekolah satu orang atas satu masalah (sheet KONFIRMASI, Lembar Konfirmasi).

    Urutan anti-persetujuan-semu ditegakkan lewat tiga stempel waktu: `cerita_dikunci_pada`
    (cerita bebas dikunci) → `dugaan_ditampilkan_pada` (rumusan hipotesis diperlihatkan)
    → `dikirim_pada` (status `terkirim`, tidak dapat diubah lagi). `kode_orang` adalah
    pseudonim pengisi (bukan FK — sama seperti `pelaku_kode_orang` riwayat). Kolom pilihan
    (`sumber`, `kesesuaian`, `k1`…`k4`, `indikasi_risiko`, `status`) bertipe `String(40)`
    tanpa CHECK (divalidasi skema). `menggantikan_id` disiapkan untuk ralat (BE-6b).
    """

    __tablename__ = "redesain_konfirmasi"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id"), nullable=False, index=True
    )
    kode_orang: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sekolah_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    sumber: Mapped[str] = mapped_column(
        String(40), nullable=False, default="daring", server_default=text("'daring'")
    )
    peran: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    cerita_sebelum: Mapped[str | None] = mapped_column(Text, nullable=True)
    cerita_dikunci_pada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dugaan_ditampilkan_pada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dikirim_pada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kesesuaian: Mapped[str | None] = mapped_column(String(40), nullable=True)
    koreksi: Mapped[str | None] = mapped_column(Text, nullable=True)
    masalah_baru: Mapped[str | None] = mapped_column(Text, nullable=True)
    alasan_k: Mapped[str | None] = mapped_column(Text, nullable=True)
    bukti_dapat_diperiksa: Mapped[str | None] = mapped_column(Text, nullable=True)
    hal_belum_jelas: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan_independensi: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan_akses: Mapped[str | None] = mapped_column(Text, nullable=True)
    k1: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k2: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k3: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k4: Mapped[str | None] = mapped_column(String(40), nullable=True)
    indikasi_risiko: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="draf", server_default=text("'draf'")
    )
    menggantikan_id: Mapped[str | None] = mapped_column(
        ForeignKey("redesain_konfirmasi.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainPenilaianModel(Base):
    """Penilaian Tim Kajian atas satu masalah redesain (sheet PENILAIAN), satu per masalah.

    `status_bukti`/`gap_material`/`indikasi_kritis`/`k1`…`k4` bertipe `String(40)` tanpa
    CHECK (divalidasi skema). `saran_otomatis` & `versi_aturan_triase` read-only: dihitung
    ulang service lewat `redesain.triase.hitung_saran` pada setiap create/update. K1–K4 diisi
    Tim (tidak diagregasi dari konfirmasi). Kolom keputusan (`prioritas_final`, `alasan_final`,
    `pemutus_*`, `tanggal_keputusan`, `saran_saat_keputusan`) diisi hanya lewat aksi putuskan;
    `status_penilaian` dikelola aksi putuskan/status. Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_penilaian"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    masalah_id: Mapped[str] = mapped_column(
        ForeignKey("redesain_masalah.id", name="fk_redesain_penilaian_masalah"),
        nullable=False,
        unique=True,
    )
    status_bukti: Mapped[str] = mapped_column(String(40), nullable=False)
    gap_material: Mapped[str] = mapped_column(String(40), nullable=False)
    indikasi_kritis: Mapped[str] = mapped_column(String(40), nullable=False)
    k1: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k2: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k3: Mapped[str | None] = mapped_column(String(40), nullable=True)
    k4: Mapped[str | None] = mapped_column(String(40), nullable=True)
    alasan_rentang_beda: Mapped[str | None] = mapped_column(Text, nullable=True)
    diluruskan_sekolah: Mapped[str | None] = mapped_column(Text, nullable=True)
    pemeriksa_sekolah_konteks: Mapped[str | None] = mapped_column(Text, nullable=True)
    tindak_lanjut: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan_sumber_versi: Mapped[str | None] = mapped_column(Text, nullable=True)
    saran_otomatis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    versi_aturan_triase: Mapped[str] = mapped_column(String(10), nullable=False)
    prioritas_final: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alasan_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    pemutus_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pemutus_jabatan: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tanggal_keputusan: Mapped[date | None] = mapped_column(Date, nullable=True)
    saran_saat_keputusan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_penilaian: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Belum ditelaah",
        server_default=text("'Belum ditelaah'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainCakupanJabatanModel(Base):
    """Cakupan jabatan awal paket v1.3 (sheet CAKUPAN_19), satu baris = entri x cabang.

    `role_kode` berpola `J-NN` dan `cabang` (`Bandung`/`Semarang`) membentuk pasangan unik.
    `nama_jabatan` adalah teks paket; `jabatan_id` (FK `jabatan.id`) dipetakan manual oleh Tim
    dan NULL pada seed. Kolom status bertipe `String(40)` tanpa CHECK (divalidasi skema).
    `pic_kode_orang` adalah pseudonim (bukan FK). Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_cakupan_jabatan"
    __table_args__ = (
        UniqueConstraint("role_kode", "cabang", name="uq_redesain_cakupan_jabatan_role_cabang"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_kode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    nama_jabatan: Mapped[str] = mapped_column(String(200), nullable=False)
    jabatan_id: Mapped[str | None] = mapped_column(
        ForeignKey("jabatan.id", name="fk_redesain_cakupan_jabatan_jabatan"),
        nullable=True,
        index=True,
    )
    cabang: Mapped[str] = mapped_column(String(20), nullable=False)
    status_unit: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum diperiksa", server_default="Belum diperiksa"
    )
    pemegang_diperiksa: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum diperiksa", server_default="Belum diperiksa"
    )
    inventori_ditinjau: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum diperiksa", server_default="Belum diperiksa"
    )
    peta_diperkuat: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Belum diperiksa", server_default="Belum diperiksa"
    )
    gap_variasi: Mapped[str | None] = mapped_column(Text, nullable=True)
    pic_kode_orang: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RedesainVersiMetodeModel(Base):
    """Catatan versi metode redesain (sheet PERUBAHAN paket v1.3), satu baris = versi x bagian.

    Pasangan (`versi`, `bagian`) unik. `pemeriksa_pemutus` berisi peran/jabatan, bukan nama
    orang. Tidak ada operasi hapus.
    """

    __tablename__ = "redesain_versi_metode"
    __table_args__ = (
        UniqueConstraint("versi", "bagian", name="uq_redesain_versi_metode_versi_bagian"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    versi: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    bagian: Mapped[str] = mapped_column(String(200), nullable=False)
    apa_diperbarui: Mapped[str] = mapped_column(Text, nullable=False)
    alasan_risiko: Mapped[str] = mapped_column(Text, nullable=False)
    status_hasil_uji: Mapped[str] = mapped_column(Text, nullable=False)
    pemeriksa_pemutus: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class NarasiSumberModel(Base):
    """Teks sumber narasi yang ditempel Tim (Source_ID = `id`); baris TIDAK PERNAH diubah.

    `teks_hash` = SHA-256 hex atas UTF-8 `teks`. Revisi teks atau perubahan izin = baris baru
    dengan `menggantikan_id` menunjuk baris lama. `izin_ai` hanya catatan, tidak menyalakan AI.
    Tidak ada operasi ubah/hapus.
    """

    __tablename__ = "narasi_sumber"
    __table_args__ = (Index("ix_narasi_sumber_jenis_periode", "jenis", "periode"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    judul: Mapped[str] = mapped_column(String(200), nullable=False)
    jenis: Mapped[str] = mapped_column(String(40), nullable=False)
    versi: Mapped[str] = mapped_column(String(50), nullable=False)
    periode: Mapped[str] = mapped_column(String(20), nullable=False)
    teks: Mapped[str] = mapped_column(Text, nullable=False)
    teks_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    izin_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    izin_catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    menggantikan_id: Mapped[str | None] = mapped_column(
        ForeignKey("narasi_sumber.id", name="fk_narasi_sumber_menggantikan"), nullable=True
    )
    dibuat_oleh: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


def _in_check(kolom: str, enum_cls: type) -> str:
    """Ekspresi SQL `kolom IN (...)` dari nilai sebuah StrEnum (untuk CHECK constraint)."""
    nilai = ", ".join(f"'{m.value}'" for m in enum_cls)  # type: ignore[attr-defined]
    return f"{kolom} IN ({nilai})"


class NarasiKasusModel(Base):
    """Kasus narasi: satu lingkup unik (instrumen, field, peran, periode, ...) yang bersejarah.

    UNIQUE delapan kolom lingkup memakai NULLS NOT DISTINCT (PostgreSQL 15+), sehingga kolom
    null ikut dibandingkan. `status` adalah proyeksi yang boleh berubah; riwayat ada di
    `narasi_versi`. Tidak ada `context_id`.
    """

    __tablename__ = "narasi_kasus"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "field_key",
            "peran_ref",
            "periode",
            "sekolah_id",
            "assignment_ref",
            "target_subject_ref",
            "konteks_kode",
            name="uq_narasi_kasus_lingkup",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(_in_check("narrative_kind", NarrativeKind), name="narrative_kind"),
        CheckConstraint(_in_check("status", StatusNarasi), name="status"),
        Index("ix_narasi_kasus_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(50), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    peran_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    periode: Mapped[str] = mapped_column(String(20), nullable=False)
    sekolah_id: Mapped[str | None] = mapped_column(
        ForeignKey("sekolah.id", name="fk_narasi_kasus_sekolah_id_sekolah"), nullable=True
    )
    assignment_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_subject_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    konteks_kode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    narrative_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    intended_use: Mapped[str] = mapped_column(String(200), nullable=False)
    permission_scope: Mapped[str] = mapped_column(String(200), nullable=False)
    sensitivity_class: Mapped[str] = mapped_column(String(40), nullable=False)
    dibuat_oleh: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class NarasiVersiModel(Base):
    """Satu versi teks sebuah kasus narasi; append-only (trigger `narasi_tolak_ubah`).

    `ai_run_id` UNIQUE: satu run AI menghasilkan paling banyak satu versi. `metadata_ai`
    hanya memuat kunci `METADATA_AI_KUNCI`; model/prompt/snapshot dibaca lewat `ai_run`.
    `status_hasil` mencatat hasil pembuatan versi (nilai bebas hingga item mesin status).
    """

    __tablename__ = "narasi_versi"
    __table_args__ = (
        UniqueConstraint("narasi_id", "revision_no", name="uq_narasi_versi_narasi_revisi"),
        CheckConstraint("revision_no > 0", name="revision_no_positif"),
        CheckConstraint(_in_check("revision_origin", RevisionOrigin), name="revision_origin"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    narasi_id: Mapped[str] = mapped_column(
        ForeignKey("narasi_kasus.id", name="fk_narasi_versi_narasi_id_narasi_kasus"),
        nullable=False,
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    status_hasil: Mapped[str] = mapped_column(String(30), nullable=False)
    teks: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("narasi_versi.id", name="fk_narasi_versi_supersedes_id_narasi_versi"),
        nullable=True,
    )
    ai_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_run.id", name="fk_narasi_versi_ai_run_id_ai_run"),
        nullable=True,
        unique=True,
    )
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_ai: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    dibuat_oleh: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()


class NarasiAiPermintaanModel(Base):
    """Permintaan draf AI atas satu kasus narasi: satu-satunya tautan kasus dan `ai_run`.

    `ai_run_id` UNIQUE (satu run, satu permintaan) diisi dari `async_job.ref_id`. Kolom
    `diserap_at`, `hasil_serap`, `kode_serap` null sampai penyerap hasil run menulisnya.
    """

    __tablename__ = "narasi_ai_permintaan"
    __table_args__ = (
        Index("ix_narasi_ai_permintaan_narasi_id_created_at", "narasi_id", "created_at"),
        Index(
            "ix_narasi_ai_permintaan_belum_diserap",
            "narasi_id",
            postgresql_where=text("diserap_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    narasi_id: Mapped[str] = mapped_column(
        ForeignKey("narasi_kasus.id", name="fk_narasi_ai_permintaan_narasi_id_narasi_kasus"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ai_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_run.id", name="fk_narasi_ai_permintaan_ai_run_id_ai_run"),
        nullable=False,
        unique=True,
    )
    sumber_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    diminta_oleh: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()
    diserap_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hasil_serap: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kode_serap: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class AiUsulanModel(Base):
    """Usulan hasil fungsi AI non-narasi atas satu sasaran; tidak pernah menjadi versi narasi.

    `ai_run_id` UNIQUE (satu run, satu usulan). `sasaran_id` polimorfik, sengaja tanpa FK, selebar
    40 karakter agar muat id `jabatan` (`String(40)`) selain UUID.
    `diserap_at`, `hasil_serap`, `kode_serap`, `isi`, `amplop`, `output_hash` null sampai
    penyerap menulisnya; `isi` dan `amplop` adalah keluaran model dan tidak boleh dicatat ke log.
    """

    __tablename__ = "ai_usulan"
    __table_args__ = (
        CheckConstraint(_in_check("sasaran_jenis", SasaranUsulan), name="sasaran_jenis"),
        Index("ix_ai_usulan_fungsi_sasaran_id_created_at", "fungsi", "sasaran_id", "created_at"),
        Index(
            "ix_ai_usulan_belum_diserap",
            "created_at",
            postgresql_where=text("diserap_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fungsi: Mapped[str] = mapped_column(String(10), nullable=False)
    sasaran_jenis: Mapped[str] = mapped_column(String(30), nullable=False)
    sasaran_id: Mapped[str] = mapped_column(String(40), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ai_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_run.id", name="fk_ai_usulan_ai_run_id_ai_run"),
        nullable=False,
        unique=True,
    )
    sumber_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    diminta_oleh: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()
    diserap_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hasil_serap: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kode_serap: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    isi: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    amplop: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AiUsulanPutusanModel(Base):
    """Putusan reviewer manusia atas satu usulan AI; append-only, hanya catatan audit.

    Tidak ada jalur ubah/hapus di service maupun rute (pola `ai_saklar_event`; tanpa trigger).
    Putusan tidak menulis `narasi_*`. `catatan` dan `teks_koreksi` adalah teks bebas reviewer
    dan tidak boleh masuk log maupun daftar.
    """

    __tablename__ = "ai_usulan_putusan"
    __table_args__ = (
        CheckConstraint(_in_check("putusan", PutusanUsulan), name="putusan"),
        CheckConstraint(
            "tingkat_koreksi IS NULL OR " + _in_check("tingkat_koreksi", TingkatKoreksi),
            name="tingkat_koreksi",
        ),
        Index("ix_ai_usulan_putusan_usulan_id_created_at", "usulan_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usulan_id: Mapped[str] = mapped_column(
        ForeignKey("ai_usulan.id", name="fk_ai_usulan_putusan_usulan_id_ai_usulan"),
        nullable=False,
    )
    putusan: Mapped[str] = mapped_column(String(10), nullable=False)
    tingkat_koreksi: Mapped[str | None] = mapped_column(String(10), nullable=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    teks_koreksi: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_key: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _ts()


class NarasiVersiSumberModel(Base):
    """Tautan versi narasi ke kutipan teks sumber; append-only (trigger `narasi_tolak_ubah`).

    PK sendiri karena satu sumber boleh dikutip berkali-kali dalam satu versi.
    """

    __tablename__ = "narasi_versi_sumber"
    __table_args__ = (
        CheckConstraint(_in_check("basis_relation", BasisRelation), name="basis_relation"),
        Index("ix_narasi_versi_sumber_narasi_versi_id", "narasi_versi_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    narasi_versi_id: Mapped[str] = mapped_column(
        ForeignKey("narasi_versi.id", name="fk_narasi_versi_sumber_narasi_versi_id_narasi_versi"),
        nullable=False,
    )
    sumber_id: Mapped[str] = mapped_column(
        ForeignKey("narasi_sumber.id", name="fk_narasi_versi_sumber_sumber_id_narasi_sumber"),
        nullable=False,
    )
    source_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    basis_relation: Mapped[str] = mapped_column(String(20), nullable=False)


class NarasiEventModel(Base):
    """Tindakan manusia atas sebuah kasus narasi; append-only (trigger `narasi_tolak_ubah`).

    Hanya service `NarasiService` yang menulis; aktor `system:ai-worker` tidak pernah
    tercatat di sini (transisi sistem dibuktikan baris `narasi_versi`).
    """

    __tablename__ = "narasi_event"
    __table_args__ = (
        CheckConstraint(_in_check("event_kind", EventKind), name="event_kind"),
        CheckConstraint(_in_check("dari_status", StatusNarasi), name="dari_status"),
        CheckConstraint(_in_check("ke_status", StatusNarasi), name="ke_status"),
        Index("ix_narasi_event_narasi_id_event_at", "narasi_id", "event_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    narasi_id: Mapped[str] = mapped_column(
        ForeignKey("narasi_kasus.id", name="fk_narasi_event_narasi_id_narasi_kasus"),
        nullable=False,
    )
    narasi_versi_id: Mapped[str | None] = mapped_column(
        ForeignKey("narasi_versi.id", name="fk_narasi_event_narasi_versi_id_narasi_versi"),
        nullable=True,
    )
    actor_key: Mapped[str] = mapped_column(String(254), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    dari_status: Mapped[str] = mapped_column(String(30), nullable=False)
    ke_status: Mapped[str] = mapped_column(String(30), nullable=False)
    event_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[datetime] = _ts()


# ======================================================================================
# Riset — protokol berversi yang dapat dikunci
# ======================================================================================


class RisetProtokolModel(Base):
    """Protokol riset berversi (`riset_protokol`); sesudah `TERKUNCI` tak ada jalur API pengubah.

    `versi` dihitung per `kode` (versi terbesar + 1, mulai 1) dan dijaga UNIQUE (`kode`, `versi`).
    Perbaikan draf maupun revisi = baris `DRAF` baru dengan `kode` sama; tidak ada sunting atau
    hapus. `isi_hash` (SHA-256 heksadesimal atas UTF-8 `isi`), `dikunci_oleh`, dan
    `dikunci_pada` null sampai protokol dikunci.
    """

    __tablename__ = "riset_protokol"
    __table_args__ = (
        CheckConstraint(_in_check("status", StatusProtokol), name="status"),
        UniqueConstraint("kode", "versi", name="uq_riset_protokol_kode_versi"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kode: Mapped[str] = mapped_column(String(40), nullable=False)
    versi: Mapped[int] = mapped_column(Integer, nullable=False)
    judul: Mapped[str] = mapped_column(String(200), nullable=False)
    isi: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatusProtokol.DRAF.value,
        server_default=text("'DRAF'"),
    )
    isi_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dibuat_oleh: Mapped[str] = mapped_column(String(200), nullable=False)
    dikunci_oleh: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dikunci_pada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class RisetStatistikModel(Base):
    """Keluaran analisis statistik per protokol riset `TERKUNCI` (`riset_statistik`).

    Tidak ada sunting atau hapus; koreksi = baris baru. Satu-satunya perubahan baris adalah
    verifikasi sekali jalan (`DRAF` -> `TERVERIFIKASI`) oleh subjek yang bukan `dibuat_oleh`.
    FK ke `riset_protokol` memakai `ON DELETE RESTRICT` agar protokol yang sudah menjadi dasar
    statistik tidak bisa hilang diam-diam.
    """

    __tablename__ = "riset_statistik"
    __table_args__ = (CheckConstraint(_in_check("status", StatusStatistik), name="status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    protokol_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("riset_protokol.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nama_analisis: Mapped[str] = mapped_column(String(200), nullable=False)
    keluaran: Mapped[str] = mapped_column(Text, nullable=False)
    kode_sumber_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=StatusStatistik.DRAF.value,
        server_default=text("'DRAF'"),
    )
    dibuat_oleh: Mapped[str] = mapped_column(String(200), nullable=False)
    diverifikasi_oleh: Mapped[str | None] = mapped_column(String(200), nullable=True)
    diverifikasi_pada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _ts()
