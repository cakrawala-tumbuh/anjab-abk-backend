"""Implementasi `SesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.services.sekolah import SekolahService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    RedesainKodeOrangModel,
    RedesainMasalahModel,
    RedesainSesiMasalahModel,
    RedesainSesiModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import RekapOrangRead, SesiCreate, SesiRead, SesiUpdate
from .riwayat import RiwayatService
from .sesi import SEARCHABLE_FIELDS

ENTITAS = "sesi"

_KOLOM_EDIT = (
    "kode_sesi",
    "kode_orang",
    "sekolah_id",
    "peran",
    "jenis_kegiatan",
    "menit_rencana",
    "menit_disepakati",
    "waktu_kalender",
    "catatan",
    "status_izin",
    "versi_izin",
    "pic_kode_orang",
    "tindak_lanjut",
)
_WAJIB = frozenset({"kode_sesi", "kode_orang", "peran", "jenis_kegiatan", "status_izin"})


def _field_map() -> FieldMap:
    m = RedesainSesiModel
    return {nama: FieldSpec(column=getattr(m, nama)) for nama in sorted(SEARCHABLE_FIELDS)}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def snapshot(r: SesiRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah baris sesi untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Sesi hasil baca.

    Returns:
        Dict kolom bisnis + `masalah_ids` (tanpa id dan cap waktu).
    """
    return {**{k: getattr(r, k) for k in _KOLOM_EDIT}, "masalah_ids": list(r.masalah_ids)}


class SqlSesiService:
    """`SesiService` berbasis PostgreSQL; terikat satu `Session` per request.

    `status_izin` hanya disimpan sebagai informasi — tidak ada jalur yang menolak atau
    menahan sesi karenanya. Sekolah divalidasi lewat seam `SekolahService` (domain core);
    kode orang & masalah (domain redesain sendiri) dibaca langsung dari tabelnya.
    """

    def __init__(self, session: Session, riwayat: RiwayatService, sekolah: SekolahService) -> None:
        self._s = session
        self._riwayat = riwayat
        self._sekolah = sekolah

    # ── validasi rujukan ────────────────────────────────────────────────────

    def _validasi_kode_orang(self, kode: str | None, nama_field: str) -> None:
        if kode is None:
            return
        m = RedesainKodeOrangModel
        if self._s.scalar(select(func.count()).select_from(m).where(m.kode == kode)) == 0:
            raise ValidationAppError(f"Kode orang '{kode}' ({nama_field}) tidak dikenal.")

    def _validasi_sekolah(self, sekolah_id: str | None) -> None:
        if sekolah_id is None:
            return
        try:
            self._sekolah.get(sekolah_id)
        except NotFoundError as exc:
            raise ValidationAppError(f"Sekolah '{sekolah_id}' tidak ditemukan.") from exc

    def _validasi_masalah(self, ids: list[str]) -> list[str]:
        unik = sorted(set(ids))
        if not unik:
            return unik
        m = RedesainMasalahModel
        ada = set(self._s.scalars(select(m.id).where(m.id.in_(unik))).all())
        hilang = [i for i in unik if i not in ada]
        if hilang:
            raise ValidationAppError(f"Masalah tidak ditemukan: {', '.join(hilang)}.")
        return unik

    def _cek_pasangan(self, kode_sesi: str, kode_orang: str, kecuali_id: str | None) -> None:
        m = RedesainSesiModel
        q = (
            select(func.count())
            .select_from(m)
            .where(m.kode_sesi == kode_sesi, m.kode_orang == kode_orang)
        )
        if kecuali_id is not None:
            q = q.where(m.id != kecuali_id)
        if self._s.scalar(q):
            raise ConflictError(f"Orang '{kode_orang}' sudah tercatat pada sesi '{kode_sesi}'.")

    # ── helper baca/tulis ───────────────────────────────────────────────────

    def _masalah_ids(self, sesi_id: str) -> list[str]:
        t = RedesainSesiMasalahModel
        return list(
            self._s.scalars(
                select(t.masalah_id).where(t.sesi_id == sesi_id).order_by(t.masalah_id)
            ).all()
        )

    def _ganti_masalah(self, sesi_id: str, ids: list[str]) -> None:
        t = RedesainSesiMasalahModel
        self._s.execute(
            delete(t).where(t.sesi_id == sesi_id).execution_options(synchronize_session="fetch")
        )
        for mid in ids:
            self._s.add(t(sesi_id=sesi_id, masalah_id=mid))

    def _to_read(self, rec: RedesainSesiModel) -> SesiRead:
        return SesiRead(
            id=rec.id,
            masalah_ids=self._masalah_ids(rec.id),
            created_at=_aware(rec.created_at),
            updated_at=_aware(rec.updated_at),
            **{k: getattr(rec, k) for k in _KOLOM_EDIT},  # type: ignore[arg-type]
        )

    def _flush(self, kode_sesi: str, kode_orang: str) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            # Backstop balapan dua request: pre-check lolos di keduanya.
            raise ConflictError(
                f"Orang '{kode_orang}' sudah tercatat pada sesi '{kode_sesi}'."
            ) from exc

    def _get_model(self, sesi_id: str) -> RedesainSesiModel:
        rec = self._s.get(RedesainSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi '{sesi_id}' tidak ditemukan.")
        return rec

    # ── operasi publik ──────────────────────────────────────────────────────

    def create(self, data: SesiCreate, *, pelaku_kode_orang: str | None) -> SesiRead:
        """Catat keterlibatan orang × sesi beserta tautan masalah, lalu catat riwayat.

        Rujukan divalidasi sebelum tulis. Parent di-flush SENDIRI sebelum baris tautan
        ditambahkan (FK telanjang tanpa `relationship()`, lihat Gotcha CLAUDE.md).

        Raises:
            ValidationAppError: kode orang/PIC, sekolah, atau masalah tak dikenal.
            ConflictError: pasangan `kode_sesi`+`kode_orang` sudah ada.
        """
        self._validasi_kode_orang(data.kode_orang, "peserta")
        self._validasi_kode_orang(data.pic_kode_orang, "PIC")
        self._validasi_sekolah(data.sekolah_id)
        masalah_ids = self._validasi_masalah(data.masalah_ids)
        self._cek_pasangan(data.kode_sesi, data.kode_orang, None)
        rec = RedesainSesiModel(id=str(uuid.uuid4()), **data.model_dump(exclude={"masalah_ids"}))
        self._s.add(rec)
        self._flush(data.kode_sesi, data.kode_orang)
        self._ganti_masalah(rec.id, masalah_ids)
        self._s.flush()
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def get(self, sesi_id: str) -> SesiRead:
        """Ambil satu baris sesi; `NotFoundError` (404) bila tak ada."""
        return self._to_read(self._get_model(sesi_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[SesiRead], int]:
        """Daftar berurutan menurut `kode_sesi`, lalu `kode_orang`."""
        m = RedesainSesiModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.kode_sesi, m.kode_orang).limit(limit).offset(offset)
        ).all()
        return [self._to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SesiRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainSesiModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode_sesi, m.kode_orang]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [self._to_read(r) for r in rows], total

    def update(self, sesi_id: str, data: SesiUpdate, *, pelaku_kode_orang: str | None) -> SesiRead:
        """Ubah parsial baris sesi (hanya field yang dikirim) dan catat riwayat.

        Field nullable boleh dikosongkan dengan `null`; field wajib bernilai `null`
        diabaikan. `masalah_ids` yang dikirim (bukan `null`) mengganti seluruh tautan.
        Keunikan pasangan diperiksa pada nilai EFEKTIF (tersimpan digabung payload).

        Raises:
            NotFoundError: sesi tidak ada.
            ValidationAppError: kode orang/PIC, sekolah, atau masalah baru tak dikenal.
            ConflictError: pasangan efektif bentrok dengan baris lain.
        """
        rec = self._get_model(sesi_id)
        sebelum = snapshot(self._to_read(rec))
        terkirim = data.model_fields_set
        berlaku = {
            nama
            for nama in terkirim - {"masalah_ids"}
            if not (getattr(data, nama) is None and nama in _WAJIB)
        }
        if "kode_orang" in berlaku:
            self._validasi_kode_orang(data.kode_orang, "peserta")
        if "pic_kode_orang" in berlaku:
            self._validasi_kode_orang(data.pic_kode_orang, "PIC")
        if "sekolah_id" in berlaku:
            self._validasi_sekolah(data.sekolah_id)
        masalah_ids: list[str] | None = None
        if "masalah_ids" in terkirim and data.masalah_ids is not None:
            masalah_ids = self._validasi_masalah(data.masalah_ids)
        kode_sesi = data.kode_sesi if "kode_sesi" in berlaku else rec.kode_sesi
        kode_orang = data.kode_orang if "kode_orang" in berlaku else rec.kode_orang
        self._cek_pasangan(kode_sesi, kode_orang, rec.id)  # type: ignore[arg-type]
        for nama in berlaku:
            setattr(rec, nama, getattr(data, nama))
        if masalah_ids is not None:
            self._ganti_masalah(rec.id, masalah_ids)
        self._flush(kode_sesi, kode_orang)  # type: ignore[arg-type]
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def rekap_orang(self, *, limit: int, offset: int) -> tuple[list[RekapOrangRead], int]:
        """Rekap per `kode_orang`, berurutan menurut `kode_orang`.

        `jumlah_sesi` = banyaknya `kode_sesi` berbeda. Total menit memakai `SUM` SQL:
        NULL diabaikan (bukan dianggap 0) dan bila semua NULL hasilnya NULL. Karena satu
        baris = satu orang × satu sesi (unik), menit tiap sesi terhitung tepat sekali.

        Returns:
            Tuple (halaman rekap, jumlah orang unik).
        """
        m = RedesainSesiModel
        total = self._s.scalar(select(func.count(func.distinct(m.kode_orang)))) or 0
        rows = self._s.execute(
            select(
                m.kode_orang,
                func.count(func.distinct(m.kode_sesi)),
                func.sum(m.menit_rencana),
                func.sum(m.menit_disepakati),
            )
            .group_by(m.kode_orang)
            .order_by(m.kode_orang)
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            RekapOrangRead(
                kode_orang=kode,
                jumlah_sesi=jumlah,
                total_menit_rencana=None if rencana is None else int(rencana),
                total_menit_disepakati=None if disepakati is None else int(disepakati),
            )
            for kode, jumlah, rencana, disepakati in rows
        ], total
