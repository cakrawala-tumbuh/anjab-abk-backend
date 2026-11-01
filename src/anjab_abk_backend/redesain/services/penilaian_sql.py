"""Implementasi `PenilaianService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    RedesainKodeOrangModel,
    RedesainKonfirmasiModel,
    RedesainMasalahModel,
    RedesainPenilaianModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.penilaian import (
    PenilaianCreate,
    PenilaianPutuskan,
    PenilaianRead,
    PenilaianStatus,
    PenilaianUpdate,
    Peringatan,
    SebaranK,
)
from ..triase import VERSI_ATURAN_TRIASE, hitung_saran
from .penilaian import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "penilaian"

_KOLOM_EDIT = (
    "status_bukti",
    "gap_material",
    "indikasi_kritis",
    "k1",
    "k2",
    "k3",
    "k4",
    "alasan_rentang_beda",
    "diluruskan_sekolah",
    "pemeriksa_sekolah_konteks",
    "tindak_lanjut",
    "catatan_sumber_versi",
)
_KOLOM_HITUNG = ("saran_otomatis", "versi_aturan_triase")
_KOLOM_KEPUTUSAN = (
    "prioritas_final",
    "alasan_final",
    "pemutus_kode_orang",
    "pemutus_jabatan",
    "tanggal_keputusan",
    "saran_saat_keputusan",
    "status_penilaian",
)
_PRIORITAS_BERBUKTI = frozenset({"P1 - Utama", "P2 - Berikutnya", "P3 - Pantau"})
_NILAI_K = ("Tinggi", "Sedang", "Rendah", "Belum tahu")
_WAJIB = frozenset({"status_bukti", "gap_material", "indikasi_kritis"})


def _field_map() -> FieldMap:
    m = RedesainPenilaianModel
    return {
        "masalah_id": FieldSpec(column=m.masalah_id),
        "status_bukti": FieldSpec(column=m.status_bukti),
        "saran_otomatis": FieldSpec(column=m.saran_otomatis),
        "status_penilaian": FieldSpec(column=m.status_penilaian),
        "prioritas_final": FieldSpec(column=m.prioritas_final),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _peringatan(rec: RedesainPenilaianModel) -> list[Peringatan]:
    """Hitung peringatan (tidak disimpan) atas prioritas final; kosong bila belum diputuskan."""
    hasil: list[Peringatan] = []
    if rec.prioritas_final is None:
        return hasil
    if rec.prioritas_final in _PRIORITAS_BERBUKTI and rec.status_bukti != "Diperkuat untuk klaim":
        hasil.append(
            Peringatan(
                kode="PRIORITAS_TANPA_BUKTI",
                pesan=(
                    f"Prioritas final '{rec.prioritas_final}' diberikan pada masalah berstatus "
                    f"bukti '{rec.status_bukti}' (belum 'Diperkuat untuk klaim')."
                ),
            )
        )
    if rec.prioritas_final != rec.saran_otomatis:
        hasil.append(
            Peringatan(
                kode="BERBEDA_DARI_SARAN",
                pesan=(
                    f"Prioritas final '{rec.prioritas_final}' berbeda dari saran otomatis "
                    f"'{rec.saran_otomatis}'."
                ),
            )
        )
    return hasil


def _to_read(rec: RedesainPenilaianModel) -> PenilaianRead:
    return PenilaianRead(
        peringatan=_peringatan(rec),
        id=rec.id,
        masalah_id=rec.masalah_id,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in (*_KOLOM_EDIT, *_KOLOM_HITUNG, *_KOLOM_KEPUTUSAN)},  # type: ignore[arg-type]
    )


def snapshot(r: PenilaianRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah penilaian untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Penilaian hasil baca.

    Returns:
        Dict `masalah_id` + kolom bisnis + `saran_otomatis`/`versi_aturan_triase`
        termasuk kolom keputusan (tanpa id, cap waktu, dan peringatan hitungan).
    """
    return {
        "masalah_id": r.masalah_id,
        **{k: getattr(r, k) for k in (*_KOLOM_EDIT, *_KOLOM_HITUNG)},
        **{
            k: (v.isoformat() if isinstance(v, date) else v)
            for k in _KOLOM_KEPUTUSAN
            for v in [getattr(r, k)]
        },
    }


def _hitung_ulang(rec: RedesainPenilaianModel) -> None:
    """Isi `saran_otomatis` & `versi_aturan_triase` dari kolom penilaian saat ini (mutasi rec)."""
    rec.saran_otomatis = hitung_saran(
        rec.status_bukti, rec.gap_material, rec.indikasi_kritis, rec.k1, rec.k2, rec.k3, rec.k4
    )
    rec.versi_aturan_triase = VERSI_ATURAN_TRIASE


class SqlPenilaianService:
    """`PenilaianService` berbasis PostgreSQL; terikat satu `Session` per request.

    Satu penilaian per masalah: dicek eksplisit sebelum INSERT (409) dan dijaga unique
    `masalah_id` sebagai backstop balapan. Saran triase dihitung ulang setiap tulis.
    """

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def create(self, data: PenilaianCreate, *, pelaku_kode_orang: str | None) -> PenilaianRead:
        """Buat penilaian, hitung saran triase, dan catat riwayat.

        Raises:
            ValidationAppError: masalah tidak ditemukan (422).
            ConflictError: masalah sudah punya penilaian (409).
        """
        if self._s.get(RedesainMasalahModel, data.masalah_id) is None:
            raise ValidationAppError(f"Masalah '{data.masalah_id}' tidak ditemukan.")
        m = RedesainPenilaianModel
        sudah = self._s.scalar(
            select(func.count()).select_from(m).where(m.masalah_id == data.masalah_id)
        )
        if sudah:
            raise ConflictError(f"Masalah '{data.masalah_id}' sudah punya penilaian.")
        rec = m(id=str(uuid.uuid4()), **data.model_dump())
        _hitung_ulang(rec)
        self._s.add(rec)
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(f"Masalah '{data.masalah_id}' sudah punya penilaian.") from exc
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, penilaian_id: str) -> RedesainPenilaianModel:
        rec = self._s.get(RedesainPenilaianModel, penilaian_id)
        if rec is None:
            raise NotFoundError(f"Penilaian '{penilaian_id}' tidak ditemukan.")
        return rec

    def get(self, penilaian_id: str) -> PenilaianRead:
        """Ambil satu penilaian; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(penilaian_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[PenilaianRead], int]:
        """Daftar berurutan menurut `created_at` lalu `id`."""
        m = RedesainPenilaianModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.created_at, m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PenilaianRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainPenilaianModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.created_at, m.id]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, penilaian_id: str, data: PenilaianUpdate, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Ubah parsial penilaian, hitung ulang saran triase, dan catat riwayat.

        Field nullable boleh dikosongkan dengan `null`; field wajib bernilai `null` diabaikan.

        Raises:
            NotFoundError: penilaian tidak ada (404).
        """
        rec = self._get_model(penilaian_id)
        sebelum = snapshot(_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is None and nama in _WAJIB:
                continue
            setattr(rec, nama, nilai)
        _hitung_ulang(rec)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def putuskan(
        self, penilaian_id: str, data: PenilaianPutuskan, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Catat keputusan prioritas final (boleh diulang), set `Telah diputuskan`, catat riwayat.

        Raises:
            NotFoundError: penilaian tak ada (404).
            ValidationAppError: kode orang pemutus tak dikenal (422).
        """
        rec = self._get_model(penilaian_id)
        ko = RedesainKodeOrangModel
        ada = self._s.scalar(
            select(func.count()).select_from(ko).where(ko.kode == data.pemutus_kode_orang)
        )
        if not ada:
            raise ValidationAppError(f"Kode orang '{data.pemutus_kode_orang}' tidak dikenal.")
        sebelum = snapshot(_to_read(rec))
        rec.prioritas_final = data.prioritas_final
        rec.alasan_final = data.alasan_final
        rec.pemutus_kode_orang = data.pemutus_kode_orang
        rec.pemutus_jabatan = data.pemutus_jabatan
        rec.tanggal_keputusan = data.tanggal_keputusan
        rec.saran_saat_keputusan = rec.saran_otomatis
        rec.status_penilaian = "Telah diputuskan"
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(
            ENTITAS, read.id, "putuskan", sebelum, snapshot(read), pelaku_kode_orang
        )
        return read

    def set_status(
        self, penilaian_id: str, data: PenilaianStatus, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Ubah `status_penilaian` (bukan `Telah diputuskan`) dan catat riwayat `status`.

        Raises:
            NotFoundError: penilaian tak ada (404).
        """
        rec = self._get_model(penilaian_id)
        sebelum = snapshot(_to_read(rec))
        rec.status_penilaian = data.status_penilaian
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "status", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def agenda_yayasan(self, *, limit: int, offset: int) -> tuple[list[PenilaianRead], int]:
        """Penilaian berstatus `Siap untuk telaah yayasan`, berurutan `created_at` lalu `id`."""
        m = RedesainPenilaianModel
        cond = m.status_penilaian == "Siap untuk telaah yayasan"
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(m.created_at, m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def sebaran_k(self, masalah_id: str) -> SebaranK:
        """Hitung sebaran K1–K4 konfirmasi `terkirim` yang belum digantikan ralat.

        Draf dan konfirmasi yang sudah digantikan (ada baris lain dengan `menggantikan_id`
        = id-nya) tidak ikut dihitung. Nilai `NULL` dihitung sebagai `kosong`.

        Raises:
            NotFoundError: masalah tidak ada (404).
        """
        if self._s.get(RedesainMasalahModel, masalah_id) is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        k = RedesainKonfirmasiModel
        pengganti = select(k.menggantikan_id).where(k.menggantikan_id.is_not(None))
        rows = self._s.scalars(
            select(k).where(
                k.masalah_id == masalah_id, k.status == "terkirim", k.id.not_in(pengganti)
            )
        ).all()
        hasil: dict[str, dict[str, int]] = {}
        for nama in ("k1", "k2", "k3", "k4"):
            hitung = dict.fromkeys((*_NILAI_K, "kosong"), 0)
            for r in rows:
                nilai = getattr(r, nama)
                hitung[nilai if nilai in _NILAI_K else "kosong"] += 1
            hasil[nama] = hitung
        return SebaranK(masalah_id=masalah_id, jumlah_konfirmasi=len(rows), **hasil)
