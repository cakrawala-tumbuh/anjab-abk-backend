"""Implementasi `MasalahService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.services.sekolah import SekolahService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import RedesainKonteksModel, RedesainMasalahModel, RedesainMasalahUraianTugasModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ...taskinv.services.uraian_tugas import UraianTugasService
from ..schemas.masalah import MasalahCreate, MasalahRead, MasalahUpdate
from .masalah import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "masalah"

_KOLOM_BISNIS = (
    "konteks_id",
    "sekolah_id",
    "keterangan_sekolah",
    "periode_acuan",
    "periode_pasti",
    "rumusan_hipotesis",
    "sumber_awal_keterbatasan",
    "status_awal",
    "gelombang",
    "penjelasan_alternatif",
    "pic_kode_orang",
    "dibuka_untuk_konfirmasi",
)

_KOLOM_NULLABLE = frozenset(
    {"sekolah_id", "keterangan_sekolah", "penjelasan_alternatif", "pic_kode_orang"}
)
"""Kolom yang boleh dikosongkan lewat PATCH dengan `null`."""


def _field_map() -> FieldMap:
    m = RedesainMasalahModel
    return {
        "kode": FieldSpec(column=m.kode),
        "konteks_id": FieldSpec(column=m.konteks_id),
        "sekolah_id": FieldSpec(column=m.sekolah_id),
        "status_awal": FieldSpec(column=m.status_awal),
        "gelombang": FieldSpec(column=m.gelombang),
        "dibuka_untuk_konfirmasi": FieldSpec(column=m.dibuka_untuk_konfirmasi),
    }


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def kode_prefix(kode_konteks: str) -> str:
    """Awalan kode masalah untuk sebuah konteks.

    Args:
        kode_konteks: Kode konteks, mis. `K-01`.

    Returns:
        Awalan tanpa nomor urut, mis. `M-K01-`.
    """
    return f"M-{kode_konteks.replace('-', '')}-"


def snapshot(r: MasalahRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah masalah untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Masalah hasil baca.

    Returns:
        Dict kolom bisnis + `kode` + `uraian_tugas_ids` (tanpa id dan cap waktu).
    """
    return {
        "kode": r.kode,
        **{k: getattr(r, k) for k in _KOLOM_BISNIS},
        "uraian_tugas_ids": list(r.uraian_tugas_ids),
    }


class SqlMasalahService:
    """`MasalahService` berbasis PostgreSQL; terikat satu `Session` per request.

    Keberadaan uraian tugas dan sekolah divalidasi lewat seam domainnya masing-masing
    (`UraianTugasService`, `SekolahService`) — tabel `ti_*`/`sekolah` tidak di-query
    langsung. Konteks (domain redesain sendiri) dibaca langsung dari tabelnya.
    """

    def __init__(
        self,
        session: Session,
        riwayat: RiwayatService,
        uraian_tugas: UraianTugasService,
        sekolah: SekolahService,
    ) -> None:
        self._s = session
        self._riwayat = riwayat
        self._ut = uraian_tugas
        self._sekolah = sekolah

    # ── validasi rujukan ────────────────────────────────────────────────────

    def _konteks(self, konteks_id: str) -> RedesainKonteksModel:
        rec = self._s.get(RedesainKonteksModel, konteks_id)
        if rec is None:
            raise ValidationAppError(f"Konteks '{konteks_id}' tidak ditemukan.")
        return rec

    def _validasi_sekolah(self, sekolah_id: str | None) -> None:
        if sekolah_id is None:
            return
        try:
            self._sekolah.get(sekolah_id)
        except NotFoundError as exc:
            raise ValidationAppError(f"Sekolah '{sekolah_id}' tidak ditemukan.") from exc

    def _validasi_uraian(self, ids: list[str]) -> list[str]:
        unik = sorted(set(ids))
        hilang: list[str] = []
        for ut_id in unik:
            try:
                self._ut.get(ut_id)
            except NotFoundError:
                hilang.append(ut_id)
        if hilang:
            raise ValidationAppError(f"Uraian tugas tidak ditemukan: {', '.join(hilang)}.")
        return unik

    # ── helper baca/tulis ───────────────────────────────────────────────────

    def _uraian_ids(self, masalah_id: str) -> list[str]:
        t = RedesainMasalahUraianTugasModel
        return list(
            self._s.scalars(
                select(t.uraian_tugas_id)
                .where(t.masalah_id == masalah_id)
                .order_by(t.uraian_tugas_id)
            ).all()
        )

    def _ganti_uraian(self, masalah_id: str, ids: list[str]) -> None:
        t = RedesainMasalahUraianTugasModel
        self._s.execute(
            delete(t)
            .where(t.masalah_id == masalah_id)
            .execution_options(synchronize_session="fetch")
        )
        for ut_id in ids:
            self._s.add(t(masalah_id=masalah_id, uraian_tugas_id=ut_id))

    def _to_read(self, rec: RedesainMasalahModel) -> MasalahRead:
        return MasalahRead(
            id=rec.id,
            kode=rec.kode,
            konteks_id=rec.konteks_id,
            sekolah_id=rec.sekolah_id,
            keterangan_sekolah=rec.keterangan_sekolah,
            periode_acuan=rec.periode_acuan,
            periode_pasti=rec.periode_pasti,
            rumusan_hipotesis=rec.rumusan_hipotesis,
            sumber_awal_keterbatasan=rec.sumber_awal_keterbatasan,
            status_awal=rec.status_awal,  # type: ignore[arg-type]
            gelombang=rec.gelombang,  # type: ignore[arg-type]
            penjelasan_alternatif=rec.penjelasan_alternatif,
            pic_kode_orang=rec.pic_kode_orang,
            dibuka_untuk_konfirmasi=rec.dibuka_untuk_konfirmasi,
            status_awal_dibekukan_pada=_aware(rec.status_awal_dibekukan_pada),
            uraian_tugas_ids=self._uraian_ids(rec.id),
            created_at=_aware(rec.created_at),  # type: ignore[arg-type]
            updated_at=_aware(rec.updated_at),  # type: ignore[arg-type]
        )

    def _flush(self) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError("Kode masalah bentrok; ulangi permintaan.") from exc

    def _kode_berikutnya(self, kode_konteks: str) -> str:
        """Bangkitkan kode berikutnya per konteks: nomor urut maksimum + 1, dua digit."""
        prefix = kode_prefix(kode_konteks)
        m = RedesainMasalahModel
        nomor = 0
        for kode in self._s.scalars(select(m.kode).where(m.kode.like(f"{prefix}%"))).all():
            akhiran = kode[len(prefix) :]
            if akhiran.isdigit():
                nomor = max(nomor, int(akhiran))
        return f"{prefix}{nomor + 1:02d}"

    def _get_model(self, masalah_id: str) -> RedesainMasalahModel:
        rec = self._s.get(RedesainMasalahModel, masalah_id)
        if rec is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        return rec

    # ── kontrak ─────────────────────────────────────────────────────────────

    def create(self, data: MasalahCreate, *, pelaku_kode_orang: str | None) -> MasalahRead:
        """Buat masalah baru, tautkan uraian tugasnya, dan catat riwayat.

        Seluruh rujukan divalidasi SEBELUM ada baris ditulis, sehingga ID tak dikenal
        tidak meninggalkan baris masalah maupun relasi.

        Raises:
            ValidationAppError: konteks, sekolah, atau uraian tugas tidak dikenal.
            ConflictError: kode hasil bangkitan sudah dipakai (balapan dua create).
        """
        konteks = self._konteks(data.konteks_id)
        self._validasi_sekolah(data.sekolah_id)
        ut_ids = self._validasi_uraian(data.uraian_tugas_ids)
        kode = self._kode_berikutnya(konteks.kode)
        m = RedesainMasalahModel
        if self._s.scalars(select(m.id).where(m.kode == kode)).first() is not None:
            raise ConflictError(f"Masalah '{kode}' sudah ada.")
        rec = m(
            id=str(uuid.uuid4()),
            kode=kode,
            **data.model_dump(exclude={"uraian_tugas_ids"}),
        )
        self._s.add(rec)
        self._flush()
        self._ganti_uraian(rec.id, ut_ids)
        self._flush()
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def get(self, masalah_id: str) -> MasalahRead:
        """Ambil satu masalah; `NotFoundError` (404) bila tak ada."""
        return self._to_read(self._get_model(masalah_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[MasalahRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainMasalahModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [self._to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[MasalahRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainMasalahModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [self._to_read(r) for r in rows], total

    def update(
        self, masalah_id: str, data: MasalahUpdate, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Ubah parsial masalah dan catat riwayat.

        Field yang tidak dikirim tidak disentuh; field nullable yang dikirim `null`
        dikosongkan; field wajib yang dikirim `null` diabaikan. `uraian_tugas_ids`
        bila dikirim mengganti penuh tautan. `kode` tidak berubah walau `konteks_id`
        diganti.

        Raises:
            NotFoundError: masalah tidak ada.
            ConflictError: `status_awal` dikirim padahal `status_awal_dibekukan_pada` terisi.
            ValidationAppError: konteks, sekolah, atau uraian tugas tidak dikenal.
        """
        rec = self._get_model(masalah_id)
        fields = data.model_fields_set
        if (
            "status_awal" in fields
            and data.status_awal is not None
            and rec.status_awal_dibekukan_pada is not None
        ):
            raise ConflictError("Status awal sudah dibekukan.")
        if "konteks_id" in fields and data.konteks_id is not None:
            self._konteks(data.konteks_id)
        if "sekolah_id" in fields:
            self._validasi_sekolah(data.sekolah_id)
        ut_ids: list[str] | None = None
        if "uraian_tugas_ids" in fields and data.uraian_tugas_ids is not None:
            ut_ids = self._validasi_uraian(data.uraian_tugas_ids)
        sebelum = snapshot(self._to_read(rec))
        for nama in fields - {"uraian_tugas_ids"}:
            nilai = getattr(data, nama)
            if nilai is not None or nama in _KOLOM_NULLABLE:
                setattr(rec, nama, nilai)
        if ut_ids is not None:
            self._ganti_uraian(rec.id, ut_ids)
        rec.updated_at = datetime.now(UTC)
        self._flush()
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def set_status_konfirmasi(
        self, masalah_id: str, dibuka: bool, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Set `dibuka_untuk_konfirmasi` dan catat riwayat aksi `status-konfirmasi`.

        Raises:
            NotFoundError: masalah tidak ada.
        """
        rec = self._get_model(masalah_id)
        sebelum = snapshot(self._to_read(rec))
        rec.dibuka_untuk_konfirmasi = dibuka
        rec.updated_at = datetime.now(UTC)
        self._flush()
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(
            ENTITAS, read.id, "status-konfirmasi", sebelum, snapshot(read), pelaku_kode_orang
        )
        return read
