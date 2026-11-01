"""Implementasi `KonfirmasiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from ...models import (
    RedesainKodeOrangModel,
    RedesainKonfirmasiModel,
    RedesainKonteksModel,
    RedesainMasalahModel,
)
from ...schemas.common import ErrorDetail
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.konfirmasi import (
    FIELD_BAGIAN_C_E,
    FIELD_WAJIB_KIRIM,
    AngkatMasalahCreate,
    DugaanRead,
    KonfirmasiDaftarRead,
    KonfirmasiLuringCreate,
    KonfirmasiRead,
    KonfirmasiUpdate,
    MasalahSekolahRead,
)
from ..schemas.masalah import MasalahCreate, MasalahRead
from .konfirmasi import SEARCHABLE_FIELDS
from .masalah import MasalahService
from .riwayat import RiwayatService

ENTITAS_KONFIRMASI = "konfirmasi"
ENTITAS_MASALAH = "masalah"

KODE_CERITA_SUDAH_DIKUNCI = "CERITA_SUDAH_DIKUNCI"
KODE_CERITA_BELUM_DIKUNCI = "CERITA_BELUM_DIKUNCI"
KODE_DUGAAN_BELUM_DITAMPILKAN = "DUGAAN_BELUM_DITAMPILKAN"
KODE_SUDAH_TERKIRIM = "KONFIRMASI_SUDAH_TERKIRIM"
KODE_SUDAH_ADA = "KONFIRMASI_SUDAH_ADA"
KODE_BELUM_TERKIRIM = "KONFIRMASI_BELUM_TERKIRIM"
KODE_SUDAH_DIGANTIKAN = "KONFIRMASI_SUDAH_DIGANTIKAN"
KODE_MASALAH_SUDAH_DIANGKAT = "MASALAH_SUDAH_DIANGKAT"

_KOLOM_SALIN_RALAT = ("peran", "tanggal", "cerita_sebelum", *FIELD_BAGIAN_C_E)
"""Kolom isi yang disalin apa adanya dari versi lama ke draf ralat."""

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

    def __init__(self, session: Session, riwayat: RiwayatService, masalah: MasalahService) -> None:
        self._s = session
        self._riwayat = riwayat
        self._masalah = masalah

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
        self,
        rec: RedesainKonfirmasiModel,
        aksi: str,
        sebelum: dict[str, object] | None,
        *,
        pelaku: str | None = None,
    ) -> KonfirmasiRead:
        self._s.flush()
        self._s.refresh(rec)
        self._riwayat.catat(
            ENTITAS_KONFIRMASI, rec.id, aksi, sebelum, _snapshot(rec), pelaku or rec.kode_orang
        )
        return self._to_read(rec)

    def _efek_terkirim(
        self, rec: RedesainKonfirmasiModel, waktu: datetime, pelaku: str | None
    ) -> None:
        """Bekukan status awal masalah dan tandai eskalasi untuk konfirmasi yang terkirim.

        Dipakai bersama oleh `kirim` dan `luring`. Masing-masing penanda hanya diisi bila
        masih NULL dan dicatat di riwayat entitas `masalah`.
        """
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
                pelaku,
            )
        if rec.indikasi_risiko == "Ada indikasi" and masalah.eskalasi_pada is None:
            masalah.eskalasi_pada = waktu
            self._riwayat.catat(
                ENTITAS_MASALAH,
                masalah.id,
                "eskalasi",
                None,
                {"indikasi_risiko": rec.indikasi_risiko, "konfirmasi_id": rec.id},
                pelaku,
            )

    def _digantikan_ids(self, ids: list[str]) -> set[str]:
        """Himpunan `ids` yang sudah ditunjuk `menggantikan_id` oleh versi lain."""
        if not ids:
            return set()
        k = RedesainKonfirmasiModel
        return set(self._s.scalars(select(k.menggantikan_id).where(k.menggantikan_id.in_(ids))))

    def _daftar(self, rows: list[RedesainKonfirmasiModel]) -> list[KonfirmasiDaftarRead]:
        digantikan = self._digantikan_ids([r.id for r in rows])
        return [
            KonfirmasiDaftarRead(**self._to_read(r).model_dump(), digantikan=r.id in digantikan)
            for r in rows
        ]

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
        self._efek_terkirim(rec, waktu, kode_orang)
        return self._simpan(rec, "kirim", sebelum)

    def ralat(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Buat draf ralat: salinan isi konfirmasi terkirim, `menggantikan_id` = id lama.

        Stempel `cerita_dikunci_pada`/`dugaan_ditampilkan_pada` ikut disalin sehingga ralat
        tidak membuka ulang cerita. Versi lama tidak diubah sama sekali. Riwayat `ralat`.

        Raises:
            ForbiddenError: konfirmasi milik orang lain.
            KonfirmasiConflictError: `KONFIRMASI_BELUM_TERKIRIM` (masih draf),
                `KONFIRMASI_SUDAH_DIGANTIKAN` (bukan versi terbaru), atau
                `KONFIRMASI_SUDAH_ADA` (pasangan itu sudah punya draf).
        """
        lama = self._get_milik(konfirmasi_id, kode_orang)
        if lama.status != "terkirim":
            raise KonfirmasiConflictError(
                KODE_BELUM_TERKIRIM, "Hanya konfirmasi yang sudah terkirim yang dapat diralat."
            )
        if self._digantikan_ids([lama.id]):
            raise KonfirmasiConflictError(
                KODE_SUDAH_DIGANTIKAN, "Konfirmasi ini sudah digantikan versi yang lebih baru."
            )
        k = RedesainKonfirmasiModel
        draf = self._s.scalar(
            select(func.count())
            .select_from(k)
            .where(k.masalah_id == lama.masalah_id, k.kode_orang == kode_orang, k.status == "draf")
        )
        if draf:
            raise KonfirmasiConflictError(
                KODE_SUDAH_ADA, "Anda sudah punya draf konfirmasi untuk masalah ini."
            )
        baru = k(
            id=str(uuid.uuid4()),
            masalah_id=lama.masalah_id,
            kode_orang=kode_orang,
            sekolah_id=lama.sekolah_id,
            sumber="daring",
            status="draf",
            menggantikan_id=lama.id,
            cerita_dikunci_pada=lama.cerita_dikunci_pada,
            dugaan_ditampilkan_pada=lama.dugaan_ditampilkan_pada,
            **{kol: getattr(lama, kol) for kol in _KOLOM_SALIN_RALAT},
        )
        self._s.add(baru)
        self._s.flush()
        self._s.refresh(baru)
        self._riwayat.catat(
            ENTITAS_KONFIRMASI,
            baru.id,
            "ralat",
            None,
            {**_snapshot(baru), "menggantikan_id": lama.id},
            kode_orang,
        )
        return self._to_read(baru)

    def list_saya(
        self, kode_orang: str, *, limit: int, offset: int
    ) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Seluruh versi (draf, terkirim, digantikan) milik `kode_orang`, terlama dulu."""
        k = RedesainKonfirmasiModel
        total = (
            self._s.scalar(select(func.count()).select_from(k).where(k.kode_orang == kode_orang))
            or 0
        )
        rows = self._s.scalars(
            select(k)
            .where(k.kode_orang == kode_orang)
            .order_by(k.created_at, k.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return self._daftar(list(rows)), int(total)

    def list_semua(self, *, limit: int, offset: int) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Seluruh konfirmasi, terlama dulu."""
        k = RedesainKonfirmasiModel
        total = self._s.scalar(select(func.count()).select_from(k)) or 0
        rows = self._s.scalars(
            select(k).order_by(k.created_at, k.id).limit(limit).offset(offset)
        ).all()
        return self._daftar(list(rows)), int(total)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        k = RedesainKonfirmasiModel
        field_map: FieldMap = {f: FieldSpec(column=getattr(k, f)) for f in SEARCHABLE_FIELDS}
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [k.created_at, k.id]
        total = self._s.scalar(select(func.count()).select_from(k).where(cond)) or 0
        rows = self._s.scalars(
            select(k).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return self._daftar(list(rows)), int(total)

    def angkat_masalah(
        self, konfirmasi_id: str, data: AngkatMasalahCreate, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Angkat `masalah_baru` menjadi masalah `Keterangan kasus` di register.

        Masalah dibuat lewat `MasalahService.create` (kode mengikuti konteks yang dipilih),
        sekolah = sekolah konfirmasi, periode acuan disalin dari masalah asal. Teks
        `masalah_baru` di konfirmasi tidak diubah. Riwayat `angkat_masalah` pada konfirmasi.

        Raises:
            NotFoundError: konfirmasi tak ada.
            KonfirmasiConflictError: masih draf, atau sudah pernah diangkat.
            ValidationAppError: `masalah_baru` kosong, atau konteks tak dikenal.
        """
        rec = self._get_model(konfirmasi_id)
        if rec.status != "terkirim":
            raise KonfirmasiConflictError(
                KODE_BELUM_TERKIRIM, "Hanya konfirmasi yang sudah terkirim yang dapat diangkat."
            )
        if not (rec.masalah_baru or "").strip():
            raise ValidationAppError(
                "Konfirmasi ini tidak memuat masalah lain (`masalah_baru` kosong).",
                details=[ErrorDetail(loc=["body"], msg="masalah_baru kosong.", type="missing")],
            )
        m = RedesainMasalahModel
        sudah_diangkat = self._s.scalar(
            select(func.count()).select_from(m).where(m.sumber_konfirmasi_id == rec.id)
        )
        if sudah_diangkat:
            raise KonfirmasiConflictError(
                KODE_MASALAH_SUDAH_DIANGKAT, "Masalah dari konfirmasi ini sudah diangkat."
            )
        asal = self._s.get(RedesainMasalahModel, rec.masalah_id)
        assert asal is not None  # FK menjamin
        baru = self._masalah.create(
            MasalahCreate(
                konteks_id=data.konteks_id,
                sekolah_id=rec.sekolah_id,
                periode_acuan=asal.periode_acuan,
                rumusan_hipotesis=data.rumusan_hipotesis,
                sumber_awal_keterbatasan=f"Disebut dalam konfirmasi {rec.id}",
                status_awal="Keterangan kasus",
                gelombang="Belum dijadwalkan",
            ),
            pelaku_kode_orang=pelaku_kode_orang,
            sumber_konfirmasi_id=rec.id,
        )
        self._riwayat.catat(
            ENTITAS_KONFIRMASI,
            rec.id,
            "angkat_masalah",
            None,
            {"masalah_id": baru.id, "masalah_kode": baru.kode},
            pelaku_kode_orang,
        )
        return baru

    def luring(
        self, data: KonfirmasiLuringCreate, *, pelaku_kode_orang: str | None
    ) -> KonfirmasiRead:
        """Simpan isian kertas atas nama `data.kode_orang` sebagai konfirmasi `terkirim`.

        `sumber="luring"`, cap waktu cerita/dugaan NULL; efek pembekuan status awal dan
        eskalasi sama dengan `kirim`. Pelaku riwayat = Tim pemanggil.

        Raises:
            ValidationAppError: kode orang, masalah tak dikenal, atau masalah bukan milik
                `sekolah_id` yang diberikan.
            KonfirmasiConflictError: `KONFIRMASI_SUDAH_ADA` untuk pasangan (masalah, kode).
        """
        if (
            self._s.scalar(
                select(func.count())
                .select_from(RedesainKodeOrangModel)
                .where(RedesainKodeOrangModel.kode == data.kode_orang)
            )
            == 0
        ):
            raise ValidationAppError(f"Kode orang '{data.kode_orang}' tidak dikenal.")
        masalah = self._s.get(RedesainMasalahModel, data.masalah_id)
        if masalah is None:
            raise ValidationAppError(f"Masalah '{data.masalah_id}' tidak ditemukan.")
        if masalah.sekolah_id != data.sekolah_id:
            raise ValidationAppError("Masalah ini bukan milik sekolah yang diberikan.")
        k = RedesainKonfirmasiModel
        sudah = self._s.scalar(
            select(func.count())
            .select_from(k)
            .where(
                k.masalah_id == data.masalah_id,
                k.kode_orang == data.kode_orang,
                k.status.in_(("draf", "terkirim")),
            )
        )
        if sudah:
            raise KonfirmasiConflictError(
                KODE_SUDAH_ADA, "Kode orang ini sudah punya konfirmasi untuk masalah tersebut."
            )
        waktu = _now()
        isi = data.model_dump(
            exclude={"masalah_id", "kode_orang", "sekolah_id", "tanggal"}, exclude_unset=False
        )
        rec = k(
            id=str(uuid.uuid4()),
            masalah_id=data.masalah_id,
            kode_orang=data.kode_orang,
            sekolah_id=data.sekolah_id,
            sumber="luring",
            tanggal=data.tanggal or waktu.date(),
            status="terkirim",
            dikirim_pada=waktu,
            **isi,
        )
        self._s.add(rec)
        self._s.flush()
        self._efek_terkirim(rec, waktu, pelaku_kode_orang)
        return self._simpan(rec, "create", None, pelaku=pelaku_kode_orang)
