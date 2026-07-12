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
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


class DcsSesiModel(Base):
    __tablename__ = "dcs_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    periode: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    max_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class DcsRespondenModel(Base):
    __tablename__ = "dcs_responden"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("dcs_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jabatan_label: Mapped[str] = mapped_column(String(200), nullable=False)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sudah_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


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


class WcpSesiModel(Base):
    __tablename__ = "wcp_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    periode: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    max_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class WcpRespondenModel(Base):
    __tablename__ = "wcp_responden"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sesi_id: Mapped[str] = mapped_column(
        ForeignKey("wcp_sesi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nama: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jabatan_label: Mapped[str] = mapped_column(String(200), nullable=False)
    partisipan_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sudah_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


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
    __tablename__ = "ti_uraian_tugas"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    uraian: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
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
    std_ai_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    std_va_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    std_dcs_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class TiSesiModel(Base):
    __tablename__ = "ti_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    periode: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    koordinator_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    min_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_responden: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
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
    __tablename__ = "ti_responden"

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
    sumber_bukti: Mapped[str] = mapped_column(String(20), nullable=False)
    kondisi: Mapped[str] = mapped_column(String(20), nullable=False)
    frekuensi_teks: Mapped[str] = mapped_column(String(100), nullable=False)
    durasi_per_kali: Mapped[int] = mapped_column(Integer, nullable=False)
    jam_per_minggu: Mapped[float] = mapped_column(Float, nullable=False)
    peak4w_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ai_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    va_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dcs_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True = partisipan menerima nilai standar master apa adanya.
    # False = ia mengubah minimal satu komponen. Task yang masternya tidak punya
    # nilai standar tetap True (tidak ada standar untuk dibantah).
    setuju_standar: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    __tablename__ = "opm_sesi"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    jabatan_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    ti_sesi_id: Mapped[str] = mapped_column(String(40), nullable=False)
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

    sesi: Mapped[OpmSesiModel] = relationship(back_populates="task_links")


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
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    criticality: Mapped[int] = mapped_column(Integer, nullable=False)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
