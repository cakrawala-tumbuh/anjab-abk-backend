"""Implementasi `ProsesService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.services.sekolah import SekolahService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import RedesainLangkahModel, RedesainMasalahModel, RedesainProsesModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.proses import (
    LangkahCreate,
    LangkahRead,
    LangkahUpdate,
    ProsesCreate,
    ProsesRead,
    ProsesUpdate,
)
from .proses import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS_PROSES = "proses"
ENTITAS_LANGKAH = "langkah"
PREFIX_PROSES = "P-"

_KOLOM_PROSES = ("masalah_id", "sekolah_id", "periode", "nama_proses")
_KOLOM_LANGKAH = (
    "urutan",
    "tahap",
    "pemicu_input",
    "pelaksana",
    "pekerjaan_sistem",
    "keluaran_penerima",
    "pemeriksa_pemutus",
    "hambatan",
    "status_langkah",
)
_LANGKAH_NULLABLE = frozenset({"pemeriksa_pemutus", "hambatan"})
"""Kolom langkah yang boleh dikosongkan lewat PATCH dengan `null`."""


def _field_map() -> FieldMap:
    m = RedesainProsesModel
    return {
        "kode": FieldSpec(column=m.kode),
        "masalah_id": FieldSpec(column=m.masalah_id),
        "sekolah_id": FieldSpec(column=m.sekolah_id),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _nomor_berikutnya(kode_ada: list[str], prefix: str) -> int:
    """Nomor urut maksimum + 1 di antara kode berawalan `prefix` (akhiran non-angka diabaikan).

    Args:
        kode_ada: Kode yang sudah ada (boleh memuat kode berawalan lain).
        prefix: Awalan kode, mis. `P-` atau `P-001-S`.

    Returns:
        Nomor berikutnya (1 bila belum ada satu pun).
    """
    nomor = 0
    for kode in kode_ada:
        akhiran = kode[len(prefix) :]
        if kode.startswith(prefix) and akhiran.isdigit():
            nomor = max(nomor, int(akhiran))
    return nomor + 1


def snapshot_proses(r: ProsesRead) -> dict[str, object]:
    """Snapshot JSON-aman proses untuk riwayat (kode + kolom bisnis, tanpa langkah)."""
    return {"kode": r.kode, **{k: getattr(r, k) for k in _KOLOM_PROSES}}


def snapshot_langkah(r: LangkahRead) -> dict[str, object]:
    """Snapshot JSON-aman langkah untuk riwayat (kode, proses_id, kolom bisnis)."""
    return {
        "kode": r.kode,
        "proses_id": r.proses_id,
        **{k: getattr(r, k) for k in _KOLOM_LANGKAH},
    }


class SqlProsesService:
    """`ProsesService` berbasis PostgreSQL; terikat satu `Session` per request.

    Keberadaan sekolah divalidasi lewat seam `SekolahService` (tabel `sekolah` tidak
    di-query langsung); masalah (domain redesain sendiri) dibaca langsung dari tabelnya.
    Kode dibangkitkan sebagai nomor maksimum + 1 — bentrok akibat balapan dua create
    berakhir 409 lewat unique constraint `kode`.
    """

    def __init__(self, session: Session, riwayat: RiwayatService, sekolah: SekolahService) -> None:
        self._s = session
        self._riwayat = riwayat
        self._sekolah = sekolah

    # ── validasi rujukan ────────────────────────────────────────────────────

    def _validasi_rujukan(self, masalah_id: str, sekolah_id: str) -> None:
        """Pastikan masalah & sekolah ada dan sekolah konsisten dengan masalah.

        Raises:
            ValidationAppError: masalah/sekolah tak dikenal, atau `masalah.sekolah_id`
                terisi dan berbeda dari `sekolah_id`.
        """
        masalah = self._s.get(RedesainMasalahModel, masalah_id)
        if masalah is None:
            raise ValidationAppError(f"Masalah '{masalah_id}' tidak ditemukan.")
        try:
            self._sekolah.get(sekolah_id)
        except NotFoundError as exc:
            raise ValidationAppError(f"Sekolah '{sekolah_id}' tidak ditemukan.") from exc
        if masalah.sekolah_id is not None and masalah.sekolah_id != sekolah_id:
            raise ValidationAppError(
                f"Sekolah proses ('{sekolah_id}') berbeda dari sekolah masalah "
                f"{masalah.kode} ('{masalah.sekolah_id}')."
            )

    # ── helper baca/tulis ───────────────────────────────────────────────────

    def _flush(self, pesan: str) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(pesan) from exc

    def _langkah_to_read(self, rec: RedesainLangkahModel) -> LangkahRead:
        return LangkahRead(
            id=rec.id,
            proses_id=rec.proses_id,
            kode=rec.kode,
            urutan=rec.urutan,
            tahap=rec.tahap,
            pemicu_input=rec.pemicu_input,
            pelaksana=rec.pelaksana,
            pekerjaan_sistem=rec.pekerjaan_sistem,
            keluaran_penerima=rec.keluaran_penerima,
            pemeriksa_pemutus=rec.pemeriksa_pemutus,
            hambatan=rec.hambatan,
            status_langkah=rec.status_langkah,  # type: ignore[arg-type]
            created_at=_aware(rec.created_at),
            updated_at=_aware(rec.updated_at),
        )

    def _to_read(self, rec: RedesainProsesModel) -> ProsesRead:
        lk = RedesainLangkahModel
        langkah = self._s.scalars(
            select(lk).where(lk.proses_id == rec.id).order_by(lk.urutan, lk.kode)
        ).all()
        return ProsesRead(
            id=rec.id,
            kode=rec.kode,
            masalah_id=rec.masalah_id,
            sekolah_id=rec.sekolah_id,
            periode=rec.periode,
            nama_proses=rec.nama_proses,
            langkah=[self._langkah_to_read(x) for x in langkah],
            created_at=_aware(rec.created_at),
            updated_at=_aware(rec.updated_at),
        )

    def _get_model(self, proses_id: str) -> RedesainProsesModel:
        rec = self._s.get(RedesainProsesModel, proses_id)
        if rec is None:
            raise NotFoundError(f"Proses '{proses_id}' tidak ditemukan.")
        return rec

    # ── kontrak proses ──────────────────────────────────────────────────────

    def create(self, data: ProsesCreate, *, pelaku_kode_orang: str | None) -> ProsesRead:
        """Buat proses baru berkode `P-NNN` (global, tiga digit) dan catat riwayat.

        Rujukan divalidasi SEBELUM baris ditulis.

        Raises:
            ValidationAppError: masalah/sekolah tak dikenal atau sekolah tak konsisten.
            ConflictError: kode hasil bangkitan bentrok (balapan dua create).
        """
        self._validasi_rujukan(data.masalah_id, data.sekolah_id)
        m = RedesainProsesModel
        kode_ada = list(self._s.scalars(select(m.kode).where(m.kode.like(f"{PREFIX_PROSES}%"))))
        kode = f"{PREFIX_PROSES}{_nomor_berikutnya(kode_ada, PREFIX_PROSES):03d}"
        rec = m(id=str(uuid.uuid4()), kode=kode, **data.model_dump())
        self._s.add(rec)
        self._flush("Kode proses bentrok; ulangi permintaan.")
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(
            ENTITAS_PROSES, read.id, "create", None, snapshot_proses(read), pelaku_kode_orang
        )
        return read

    def get(self, proses_id: str) -> ProsesRead:
        """Ambil satu proses beserta langkah terurut; `NotFoundError` (404) bila tak ada."""
        return self._to_read(self._get_model(proses_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[ProsesRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainProsesModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [self._to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[ProsesRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainProsesModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [self._to_read(r) for r in rows], total

    def update(
        self, proses_id: str, data: ProsesUpdate, *, pelaku_kode_orang: str | None
    ) -> ProsesRead:
        """Ubah parsial proses dan catat riwayat.

        Field yang dikirim `null` diabaikan (seluruh kolom proses wajib). Bila
        `masalah_id`/`sekolah_id` berubah, aturan sekolah↔masalah divalidasi ulang
        terhadap nilai gabungan (lama + baru). `kode` tidak pernah berubah.

        Raises:
            NotFoundError: proses tidak ada.
            ValidationAppError: masalah/sekolah tak dikenal atau sekolah tak konsisten.
        """
        rec = self._get_model(proses_id)
        ubah = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if "masalah_id" in ubah or "sekolah_id" in ubah:
            self._validasi_rujukan(
                ubah.get("masalah_id", rec.masalah_id), ubah.get("sekolah_id", rec.sekolah_id)
            )
        sebelum = snapshot_proses(self._to_read(rec))
        for nama, nilai in ubah.items():
            setattr(rec, nama, nilai)
        rec.updated_at = datetime.now(UTC)
        self._flush("Perubahan proses bentrok; ulangi permintaan.")
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(
            ENTITAS_PROSES, read.id, "update", sebelum, snapshot_proses(read), pelaku_kode_orang
        )
        return read

    # ── kontrak langkah ─────────────────────────────────────────────────────

    def tambah_langkah(
        self, proses_id: str, data: LangkahCreate, *, pelaku_kode_orang: str | None
    ) -> LangkahRead:
        """Tambah langkah berkode `<kode proses>-SNN` (per proses, dua digit) dan catat riwayat.

        `urutan` `null` → urutan terbesar langkah proses itu + 1.

        Raises:
            NotFoundError: proses tidak ada.
            ConflictError: kode langkah hasil bangkitan bentrok (balapan dua create).
        """
        proses = self._get_model(proses_id)
        lk = RedesainLangkahModel
        prefix = f"{proses.kode}-S"
        kode_ada = list(self._s.scalars(select(lk.kode).where(lk.proses_id == proses.id)))
        kode = f"{prefix}{_nomor_berikutnya(kode_ada, prefix):02d}"
        nilai = data.model_dump()
        if nilai["urutan"] is None:
            maks = self._s.scalar(select(func.max(lk.urutan)).where(lk.proses_id == proses.id))
            nilai["urutan"] = (maks or 0) + 1
        rec = lk(id=str(uuid.uuid4()), proses_id=proses.id, kode=kode, **nilai)
        self._s.add(rec)
        self._flush("Kode langkah bentrok; ulangi permintaan.")
        self._s.refresh(rec)
        read = self._langkah_to_read(rec)
        self._riwayat.catat(
            ENTITAS_LANGKAH, read.id, "create", None, snapshot_langkah(read), pelaku_kode_orang
        )
        return read

    def update_langkah(
        self, langkah_id: str, data: LangkahUpdate, *, pelaku_kode_orang: str | None
    ) -> LangkahRead:
        """Ubah parsial langkah dan catat riwayat.

        Field nullable (`pemeriksa_pemutus`, `hambatan`) yang dikirim `null` dikosongkan;
        field wajib yang dikirim `null` diabaikan. `kode`/`proses_id` tidak berubah.

        Raises:
            NotFoundError: langkah tidak ada.
        """
        rec = self._s.get(RedesainLangkahModel, langkah_id)
        if rec is None:
            raise NotFoundError(f"Langkah '{langkah_id}' tidak ditemukan.")
        sebelum = snapshot_langkah(self._langkah_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is not None or nama in _LANGKAH_NULLABLE:
                setattr(rec, nama, nilai)
        rec.updated_at = datetime.now(UTC)
        self._flush("Perubahan langkah bentrok; ulangi permintaan.")
        self._s.refresh(rec)
        read = self._langkah_to_read(rec)
        self._riwayat.catat(
            ENTITAS_LANGKAH,
            read.id,
            "update",
            sebelum,
            snapshot_langkah(read),
            pelaku_kode_orang,
        )
        return read
