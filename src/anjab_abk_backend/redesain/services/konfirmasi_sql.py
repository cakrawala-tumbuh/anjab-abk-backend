"""Implementasi `KonfirmasiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from ...models import RedesainKonfirmasiModel, RedesainKonteksModel, RedesainMasalahModel
from ...schemas.common import ErrorDetail
from ..schemas.konfirmasi import (
    FIELD_BAGIAN_C_E,
    FIELD_WAJIB_KIRIM,
    DugaanRead,
    KonfirmasiRead,
    KonfirmasiUpdate,
    MasalahSekolahRead,
)
from .riwayat import RiwayatService

ENTITAS_KONFIRMASI = "konfirmasi"
ENTITAS_MASALAH = "masalah"

KODE_CERITA_SUDAH_DIKUNCI = "CERITA_SUDAH_DIKUNCI"
KODE_CERITA_BELUM_DIKUNCI = "CERITA_BELUM_DIKUNCI"
KODE_DUGAAN_BELUM_DITAMPILKAN = "DUGAAN_BELUM_DITAMPILKAN"
KODE_SUDAH_TERKIRIM = "KONFIRMASI_SUDAH_TERKIRIM"
KODE_SUDAH_ADA = "KONFIRMASI_SUDAH_ADA"

_KOLOM_SNAPSHOT = ("peran", "cerita_sebelum", *FIELD_BAGIAN_C_E, "status")


class KonfirmasiConflictError(ConflictError):
    """409 dengan kode stabil khusus alur konfirmasi (mis. `CERITA_SUDAH_DIKUNCI`).

    Kode muncul di field `error` envelope sekaligus di `details[0].code`, sehingga klien
    dapat membedakan pelanggaran urutan tanpa mengurai pesan.
    """

    def __init__(self, kode: str, message: str, *, field: str | None = None) -> None:
        super().__init__(
            message,
            details=[
                ErrorDetail(
                    loc=["body", field] if field else None,
                    msg=message,
                    type="conflict",
                    code=kode,
                )
            ],
        )
        self.error_code = kode


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _snapshot(rec: RedesainKonfirmasiModel) -> dict[str, object]:
    """Snapshot JSON-aman konfirmasi untuk riwayat (kolom isian + status)."""
    return {"masalah_id": rec.masalah_id, **{k: getattr(rec, k) for k in _KOLOM_SNAPSHOT}}


class SqlKonfirmasiService:
    """`KonfirmasiService` berbasis PostgreSQL; terikat satu `Session` per request.

    Masalah & konteks (domain redesain sendiri) dibaca langsung dari tabelnya. Kepemilikan
    ditentukan oleh `kode_orang` pengisi: aksi tulis atas konfirmasi orang lain → 403.
    """

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    # ── helper ──────────────────────────────────────────────────────────────

    def _to_read(self, rec: RedesainKonfirmasiModel) -> KonfirmasiRead:
        return KonfirmasiRead(
            id=rec.id,
            masalah_id=rec.masalah_id,
            kode_orang=rec.kode_orang,
            sekolah_id=rec.sekolah_id,
            sumber=rec.sumber,  # type: ignore[arg-type]
            peran=rec.peran,
            tanggal=rec.tanggal,
            cerita_sebelum=rec.cerita_sebelum,
            cerita_dikunci_pada=_aware(rec.cerita_dikunci_pada),
            dugaan_ditampilkan_pada=_aware(rec.dugaan_ditampilkan_pada),
            dugaan_diperlihatkan="Ya" if rec.dugaan_ditampilkan_pada is not None else "Belum",
            dikirim_pada=_aware(rec.dikirim_pada),
            kesesuaian=rec.kesesuaian,  # type: ignore[arg-type]
            koreksi=rec.koreksi,
            masalah_baru=rec.masalah_baru,
            alasan_k=rec.alasan_k,
            bukti_dapat_diperiksa=rec.bukti_dapat_diperiksa,
            hal_belum_jelas=rec.hal_belum_jelas,
            catatan_independensi=rec.catatan_independensi,
            catatan_akses=rec.catatan_akses,
            k1=rec.k1,  # type: ignore[arg-type]
            k2=rec.k2,  # type: ignore[arg-type]
            k3=rec.k3,  # type: ignore[arg-type]
            k4=rec.k4,  # type: ignore[arg-type]
            indikasi_risiko=rec.indikasi_risiko,  # type: ignore[arg-type]
            status=rec.status,  # type: ignore[arg-type]
            menggantikan_id=rec.menggantikan_id,
            created_at=_aware(rec.created_at),  # type: ignore[arg-type]
            updated_at=_aware(rec.updated_at),  # type: ignore[arg-type]
        )

    def _get_model(self, konfirmasi_id: str) -> RedesainKonfirmasiModel:
        rec = self._s.get(RedesainKonfirmasiModel, konfirmasi_id)
        if rec is None:
            raise NotFoundError(f"Konfirmasi '{konfirmasi_id}' tidak ditemukan.")
        return rec

    def _get_milik(self, konfirmasi_id: str, kode_orang: str) -> RedesainKonfirmasiModel:
        """Ambil konfirmasi milik `kode_orang`.

        Raises:
            NotFoundError: konfirmasi tak ada.
            ForbiddenError: konfirmasi milik orang lain.
        """
        rec = self._get_model(konfirmasi_id)
        if rec.kode_orang != kode_orang:
            raise ForbiddenError("Akses ditolak: konfirmasi ini bukan milik Anda.")
        return rec

    def _get_draf_milik(self, konfirmasi_id: str, kode_orang: str) -> RedesainKonfirmasiModel:
        """Seperti `_get_milik`, ditambah 409 `KONFIRMASI_SUDAH_TERKIRIM` bila bukan draf."""
        rec = self._get_milik(konfirmasi_id, kode_orang)
        if rec.status != "draf":
            raise KonfirmasiConflictError(
                KODE_SUDAH_TERKIRIM, "Konfirmasi sudah terkirim dan tidak dapat diubah."
            )
        return rec

    def _simpan(
        self, rec: RedesainKonfirmasiModel, aksi: str, sebelum: dict[str, object] | None
    ) -> KonfirmasiRead:
        self._s.flush()
        self._s.refresh(rec)
        self._riwayat.catat(
            ENTITAS_KONFIRMASI, rec.id, aksi, sebelum, _snapshot(rec), rec.kode_orang
        )
        return self._to_read(rec)

    # ── kontrak ─────────────────────────────────────────────────────────────

    def list_masalah_sekolah(
        self, sekolah_id: str, *, limit: int, offset: int
    ) -> tuple[list[MasalahSekolahRead], int]:
        """Daftar masalah terbuka untuk konfirmasi di `sekolah_id`, terurut `kode`.

        Hanya kolom bagian A yang diproyeksikan; `rumusan_hipotesis` tidak pernah dibaca.
        """
        m, k = RedesainMasalahModel, RedesainKonteksModel
        syarat = (m.sekolah_id == sekolah_id, m.dibuka_untuk_konfirmasi.is_(True))
        total = self._s.scalar(select(func.count()).select_from(m).where(*syarat)) or 0
        rows = self._s.execute(
            select(
                m.id,
                m.kode,
                k.kode,
                k.tema,
                m.periode_acuan,
                m.sumber_awal_keterbatasan,
                m.status_awal,
            )
            .join(k, k.id == m.konteks_id)
            .where(*syarat)
            .order_by(m.kode)
            .limit(limit)
            .offset(offset)
        ).all()
        items = [
            MasalahSekolahRead(
                id=r[0],
                kode=r[1],
                konteks_kode=r[2],
                konteks_tema=r[3],
                periode_acuan=r[4],
                sumber_awal_keterbatasan=r[5],
                status_awal=r[6],
            )
            for r in rows
        ]
        return items, int(total)

    def create(self, masalah_id: str, *, kode_orang: str, sekolah_id: str) -> KonfirmasiRead:
        """Buat draf `daring` bertanggal hari ini (UTC) untuk (masalah, kode_orang).

        Raises:
            NotFoundError: masalah tak ada.
            ForbiddenError: masalah bukan sekolah pengisi atau belum dibuka untuk konfirmasi.
            KonfirmasiConflictError: `KONFIRMASI_SUDAH_ADA` bila pasangan sudah punya
                draf atau konfirmasi terkirim.
        """
        masalah = self._s.get(RedesainMasalahModel, masalah_id)
        if masalah is None:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        if masalah.sekolah_id != sekolah_id or not masalah.dibuka_untuk_konfirmasi:
            raise ForbiddenError(
                "Akses ditolak: masalah ini bukan milik sekolah Anda atau belum dibuka "
                "untuk konfirmasi."
            )
        k = RedesainKonfirmasiModel
        sudah = self._s.scalar(
            select(func.count())
            .select_from(k)
            .where(
                k.masalah_id == masalah_id,
                k.kode_orang == kode_orang,
                k.status.in_(("draf", "terkirim")),
            )
        )
        if sudah:
            raise KonfirmasiConflictError(
                KODE_SUDAH_ADA, "Anda sudah punya konfirmasi untuk masalah ini."
            )
        rec = k(
            id=str(uuid.uuid4()),
            masalah_id=masalah_id,
            kode_orang=kode_orang,
            sekolah_id=sekolah_id,
            sumber="daring",
            tanggal=_now().date(),
            status="draf",
        )
        self._s.add(rec)
        return self._simpan(rec, "create", None)

    def get(self, konfirmasi_id: str) -> KonfirmasiRead:
        """Ambil satu konfirmasi (pemeriksaan pemilik dilakukan pemanggil)."""
        return self._to_read(self._get_model(konfirmasi_id))

    def update(
        self, konfirmasi_id: str, data: KonfirmasiUpdate, *, kode_orang: str
    ) -> KonfirmasiRead:
        """Ubah parsial draf milik sendiri; hanya field yang DIKIRIM yang diproses.

        Raises:
            KonfirmasiConflictError: `KONFIRMASI_SUDAH_TERKIRIM`; `CERITA_SUDAH_DIKUNCI` bila
                `cerita_sebelum` dikirim setelah dikunci; `DUGAAN_BELUM_DITAMPILKAN` bila
                field bagian C–E dikirim sebelum dugaan ditampilkan.
        """
        rec = self._get_draf_milik(konfirmasi_id, kode_orang)
        perubahan = data.model_dump(exclude_unset=True)
        if "cerita_sebelum" in perubahan and rec.cerita_dikunci_pada is not None:
            raise KonfirmasiConflictError(
                KODE_CERITA_SUDAH_DIKUNCI,
                "Cerita sudah dikunci dan tidak dapat diubah.",
                field="cerita_sebelum",
            )
        c_e = [f for f in FIELD_BAGIAN_C_E if f in perubahan]
        if c_e and rec.dugaan_ditampilkan_pada is None:
            raise KonfirmasiConflictError(
                KODE_DUGAAN_BELUM_DITAMPILKAN,
                "Penilaian baru dapat diisi setelah dugaan Tim ditampilkan: " + ", ".join(c_e),
                field=c_e[0],
            )
        if "tanggal" in perubahan and perubahan["tanggal"] is None:
            del perubahan["tanggal"]
        sebelum = _snapshot(rec)
        for kolom, nilai in perubahan.items():
            setattr(rec, kolom, nilai)
        return self._simpan(rec, "update", sebelum)

    def kunci_cerita(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Kunci cerita bebas; panggilan ulang tidak mengubah waktu kunci.

        Raises:
            ValidationAppError: `cerita_sebelum` kosong atau hanya spasi.
            KonfirmasiConflictError: `KONFIRMASI_SUDAH_TERKIRIM`.
        """
        rec = self._get_draf_milik(konfirmasi_id, kode_orang)
        if rec.cerita_dikunci_pada is not None:
            return self._to_read(rec)
        if not (rec.cerita_sebelum or "").strip():
            raise ValidationAppError(
                "Cerita belum diisi; tulis cerita lebih dulu sebelum dikunci.",
                details=[
                    ErrorDetail(loc=["body", "cerita_sebelum"], msg="Wajib diisi.", type="missing")
                ],
            )
        sebelum = _snapshot(rec)
        rec.cerita_dikunci_pada = _now()
        return self._simpan(rec, "kunci_cerita", sebelum)

    def tampilkan_dugaan(self, konfirmasi_id: str, *, kode_orang: str) -> DugaanRead:
        """Kembalikan rumusan hipotesis; panggilan pertama mencatat `dugaan_ditampilkan_pada`.

        Raises:
            KonfirmasiConflictError: `CERITA_BELUM_DIKUNCI`.
        """
        rec = self._get_milik(konfirmasi_id, kode_orang)
        if rec.cerita_dikunci_pada is None:
            raise KonfirmasiConflictError(
                KODE_CERITA_BELUM_DIKUNCI, "Kunci cerita lebih dulu sebelum melihat dugaan Tim."
            )
        if rec.dugaan_ditampilkan_pada is None:
            sebelum = _snapshot(rec)
            rec.dugaan_ditampilkan_pada = _now()
            self._simpan(rec, "tampilkan_dugaan", sebelum)
        masalah = self._s.get(RedesainMasalahModel, rec.masalah_id)
        assert masalah is not None  # FK menjamin
        return DugaanRead(
            rumusan_hipotesis=masalah.rumusan_hipotesis,
            dugaan_ditampilkan_pada=_aware(rec.dugaan_ditampilkan_pada),  # type: ignore[arg-type]
        )

    def kirim(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Kirim draf: status `terkirim`, bekukan status awal masalah, tandai eskalasi.

        `masalah.status_awal_dibekukan_pada` dan (bila `indikasi_risiko="Ada indikasi"`)
        `masalah.eskalasi_pada` hanya diisi bila masih NULL; masing-masing dicatat di
        riwayat entitas `masalah`.

        Raises:
            ValidationAppError: field `FIELD_WAJIB_KIRIM` ada yang kosong (disebut per field).
            KonfirmasiConflictError: `KONFIRMASI_SUDAH_TERKIRIM`.
        """
        rec = self._get_draf_milik(konfirmasi_id, kode_orang)
        kurang = [f for f in FIELD_WAJIB_KIRIM if not (getattr(rec, f) or "").strip()]
        if kurang:
            raise ValidationAppError(
                "Field wajib belum diisi: " + ", ".join(kurang),
                details=[
                    ErrorDetail(loc=["body", f], msg="Wajib diisi.", type="missing") for f in kurang
                ],
            )
        sebelum = _snapshot(rec)
        waktu = _now()
        rec.status = "terkirim"
        rec.dikirim_pada = waktu
        masalah = self._s.get(RedesainMasalahModel, rec.masalah_id)
        assert masalah is not None  # FK menjamin
        if masalah.status_awal_dibekukan_pada is None:
            masalah.status_awal_dibekukan_pada = waktu
            self._riwayat.catat(
                ENTITAS_MASALAH,
                masalah.id,
                "bekukan_status_awal",
                None,
                {"status_awal": masalah.status_awal, "konfirmasi_id": rec.id},
                kode_orang,
            )
        if rec.indikasi_risiko == "Ada indikasi" and masalah.eskalasi_pada is None:
            masalah.eskalasi_pada = waktu
            self._riwayat.catat(
                ENTITAS_MASALAH,
                masalah.id,
                "eskalasi",
                None,
                {"indikasi_risiko": rec.indikasi_risiko, "konfirmasi_id": rec.id},
                kode_orang,
            )
        return self._simpan(rec, "kirim", sebelum)
