"""Implementasi `AlternatifService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...anjab.services.jabatan import JabatanService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    RedesainAlternatifModel,
    RedesainAlternatifPenerimaModel,
    RedesainKeputusanPerubahanModel,
    RedesainKesiapanModel,
    RedesainKodeOrangModel,
    RedesainMasalahModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.alternatif import (
    AlternatifCreate,
    AlternatifRead,
    AlternatifUpdate,
    KeputusanPerubahan,
    KeputusanPerubahanCreate,
    KeputusanPerubahanRead,
    KesiapanBaris,
    KesiapanCreate,
    KesiapanMatriksRead,
    KesiapanRead,
    PenerimaCreate,
    PenerimaRead,
    StatusKesiapan,
)
from .alternatif import (
    SEARCHABLE_FIELDS,
    KesiapanBelumReadyError,
    KesiapanHoldError,
    PenerimaBukanMilikAlternatifError,
    PenerimaGandaError,
    hitung_status_opsi,
)
from .riwayat import RiwayatService

ENTITAS = "alternatif"
PREFIX = "U-"
OPSI_ALIH = "Alihkan tugas bersyarat"
STATUS_UJI = "Uji disetujui terpisah"

_KOLOM_EDIT = (
    "masalah_id",
    "opsi",
    "alur_kini_vs_usulan",
    "pihak_asal_jabatan_id",
    "pihak_penerima_jabatan_id",
    "komitmen_penerima",
    "jadwal_puncak",
    "keterampilan_akses",
    "tambahan_bersih",
    "risiko_layanan",
    "gap_penerima",
    "status_telaah",
    "pemutus_kode_orang",
    "keputusan",
    "prasyarat_monitoring",
    "catatan_versi_bukti",
)
_WAJIB = frozenset({"opsi", "alur_kini_vs_usulan", "gap_penerima", "status_telaah"})


def _field_map() -> FieldMap:
    m = RedesainAlternatifModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "masalah_id": FieldSpec(column=m.masalah_id),
        "opsi": FieldSpec(column=m.opsi),
        "status_telaah": FieldSpec(column=m.status_telaah),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainAlternatifModel) -> AlternatifRead:
    return AlternatifRead(
        id=rec.id,
        kode=rec.kode,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in _KOLOM_EDIT},  # type: ignore[arg-type]
    )


def snapshot(r: AlternatifRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah alternatif untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Alternatif hasil baca.

    Returns:
        Dict kode + kolom bisnis (tanpa id dan cap waktu).
    """
    return {"kode": r.kode, **{k: getattr(r, k) for k in _KOLOM_EDIT}}


def _penerima_read(rec: RedesainAlternatifPenerimaModel) -> PenerimaRead:
    """Petakan baris penerima ke skema respons."""
    return PenerimaRead(
        id=rec.id,
        alternatif_id=rec.alternatif_id,
        penerima_jabatan_id=rec.penerima_jabatan_id,
        material=rec.material,
        catatan=rec.catatan,
        created_at=_aware(rec.created_at),
    )


_KOLOM_DELTA = (
    "delta_asal_jam",
    "delta_asal_estimasi",
    "delta_penerima_jam",
    "delta_penerima_estimasi",
    "delta_organisasi_jam",
    "delta_organisasi_estimasi",
)


def _kesiapan_read(rec: RedesainKesiapanModel) -> KesiapanRead:
    """Petakan baris kesiapan ke skema respons."""
    return KesiapanRead(
        id=rec.id,
        penerima_id=rec.penerima_id,
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        syarat=rec.syarat,
        alasan_hold=rec.alasan_hold,
        dinilai_oleh=rec.dinilai_oleh,
        created_at=_aware(rec.created_at),
        **{k: getattr(rec, k) for k in _KOLOM_DELTA},
    )


def _keputusan_read(rec: RedesainKeputusanPerubahanModel) -> KeputusanPerubahanRead:
    """Petakan baris keputusan perubahan ke skema respons."""
    return KeputusanPerubahanRead(
        id=rec.id,
        alternatif_id=rec.alternatif_id,
        periode=rec.periode,
        keputusan=rec.keputusan,  # type: ignore[arg-type]
        alasan=rec.alasan,
        stop_rule=rec.stop_rule,
        status_opsi_saat_putus=rec.status_opsi_saat_putus,  # type: ignore[arg-type]
        pemutus_kode_orang=rec.pemutus_kode_orang,
        created_at=_aware(rec.created_at),
    )


def _nomor_berikutnya(kode_ada: list[str]) -> int:
    """Nomor urut maksimum + 1 di antara kode `U-<angka>` (akhiran non-angka diabaikan)."""
    nomor = 0
    for kode in kode_ada:
        akhiran = kode[len(PREFIX) :]
        if kode.startswith(PREFIX) and akhiran.isdigit():
            nomor = max(nomor, int(akhiran))
    return nomor + 1


class SqlAlternatifService:
    """`AlternatifService` berbasis PostgreSQL; terikat satu `Session` per request.

    Keberadaan jabatan divalidasi lewat seam `JabatanService` (domain anjab), bukan query
    langsung. `status_telaah` tak pernah diturunkan dari prioritas penilaian.
    """

    def __init__(self, session: Session, riwayat: RiwayatService, jabatan: JabatanService) -> None:
        self._s = session
        self._riwayat = riwayat
        self._jabatan = jabatan

    def _validasi_jabatan(self, jabatan_id: str | None, nama_field: str) -> None:
        if jabatan_id is None:
            return
        try:
            self._jabatan.get(jabatan_id)
        except NotFoundError as exc:
            raise ValidationAppError(
                f"Jabatan '{jabatan_id}' ({nama_field}) tidak ditemukan."
            ) from exc

    def _validasi_kode_orang(self, kode: str | None) -> None:
        if kode is None:
            return
        m = RedesainKodeOrangModel
        if self._s.scalar(select(func.count()).select_from(m).where(m.kode == kode)) == 0:
            raise ValidationAppError(f"Kode orang '{kode}' (pemutus) tidak dikenal.")

    @staticmethod
    def _validasi_aturan(
        opsi: str,
        penerima: str | None,
        status: str,
        keputusan: str | None,
        pemutus: str | None,
    ) -> None:
        if opsi == OPSI_ALIH and not penerima:
            raise ValidationAppError(
                "Opsi 'Alihkan tugas bersyarat' mewajibkan pihak_penerima_jabatan_id."
            )
        if status == STATUS_UJI and (not keputusan or not pemutus):
            raise ValidationAppError(
                "Status 'Uji disetujui terpisah' mewajibkan keputusan dan pemutus_kode_orang."
            )

    def _flush(self) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError("Kode alternatif bentrok; ulangi permintaan.") from exc

    def create(self, data: AlternatifCreate, *, pelaku_kode_orang: str | None) -> AlternatifRead:
        """Buat alternatif berkode `U-NNN` dan catat riwayat; rujukan divalidasi sebelum tulis.

        Raises:
            ValidationAppError: masalah/jabatan/kode orang tak dikenal, atau aturan
                opsi pengalihan / status uji dilanggar.
            ConflictError: kode hasil bangkitan bentrok (balapan dua create).
        """
        if self._s.get(RedesainMasalahModel, data.masalah_id) is None:
            raise ValidationAppError(f"Masalah '{data.masalah_id}' tidak ditemukan.")
        self._validasi_jabatan(data.pihak_asal_jabatan_id, "pihak asal")
        self._validasi_jabatan(data.pihak_penerima_jabatan_id, "pihak penerima")
        self._validasi_kode_orang(data.pemutus_kode_orang)
        self._validasi_aturan(
            data.opsi,
            data.pihak_penerima_jabatan_id,
            data.status_telaah,
            data.keputusan,
            data.pemutus_kode_orang,
        )
        m = RedesainAlternatifModel
        kode_ada = list(self._s.scalars(select(m.kode).where(m.kode.like(f"{PREFIX}%"))))
        kode = f"{PREFIX}{_nomor_berikutnya(kode_ada):03d}"
        rec = m(id=str(uuid.uuid4()), kode=kode, **data.model_dump())
        self._s.add(rec)
        self._flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, alternatif_id: str) -> RedesainAlternatifModel:
        rec = self._s.get(RedesainAlternatifModel, alternatif_id)
        if rec is None:
            raise NotFoundError(f"Alternatif '{alternatif_id}' tidak ditemukan.")
        return rec

    def get(self, alternatif_id: str) -> AlternatifRead:
        """Ambil satu alternatif; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(alternatif_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[AlternatifRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainAlternatifModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AlternatifRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainAlternatifModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, alternatif_id: str, data: AlternatifUpdate, *, pelaku_kode_orang: str | None
    ) -> AlternatifRead:
        """Ubah parsial alternatif (hanya field yang dikirim) dan catat riwayat.

        Aturan opsi pengalihan / status uji divalidasi pada keadaan AKHIR (nilai tersimpan
        digabung payload). Field nullable boleh dikosongkan dengan `null`; field wajib
        bernilai `null` diabaikan.

        Raises:
            NotFoundError: alternatif tidak ada.
            ValidationAppError: jabatan/kode orang baru tak valid atau aturan dilanggar.
        """
        rec = self._get_model(alternatif_id)
        sebelum = snapshot(_to_read(rec))
        terkirim = data.model_fields_set
        efektif = {
            nama: (
                getattr(data, nama)
                if nama in terkirim and not (getattr(data, nama) is None and nama in _WAJIB)
                else getattr(rec, nama)
            )
            for nama in _KOLOM_EDIT
        }
        if "pihak_asal_jabatan_id" in terkirim:
            self._validasi_jabatan(data.pihak_asal_jabatan_id, "pihak asal")
        if "pihak_penerima_jabatan_id" in terkirim:
            self._validasi_jabatan(data.pihak_penerima_jabatan_id, "pihak penerima")
        if "pemutus_kode_orang" in terkirim:
            self._validasi_kode_orang(data.pemutus_kode_orang)
        self._validasi_aturan(
            efektif["opsi"],
            efektif["pihak_penerima_jabatan_id"],
            efektif["status_telaah"],
            efektif["keputusan"],
            efektif["pemutus_kode_orang"],
        )
        for nama in terkirim:
            nilai = getattr(data, nama)
            if nilai is None and nama in _WAJIB:
                continue
            setattr(rec, nama, nilai)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def tambah_penerima(self, alternatif_id: str, data: PenerimaCreate) -> PenerimaRead:
        """Tambah penerima (jabatan) pada alternatif.

        Raises:
            NotFoundError: alternatif tak ada.
            ValidationAppError: jabatan tak ditemukan.
            PenerimaGandaError: jabatan sudah menjadi penerima alternatif ini (409
                `PENERIMA_GANDA`), termasuk balapan dua permintaan (UNIQUE).
        """
        self._get_model(alternatif_id)
        self._validasi_jabatan(data.penerima_jabatan_id, "penerima")
        m = RedesainAlternatifPenerimaModel
        ada = self._s.scalar(
            select(func.count())
            .select_from(m)
            .where(
                m.alternatif_id == alternatif_id, m.penerima_jabatan_id == data.penerima_jabatan_id
            )
        )
        if ada:
            raise PenerimaGandaError("Jabatan itu sudah menjadi penerima alternatif ini.")
        rec = m(
            id=str(uuid.uuid4()),
            alternatif_id=alternatif_id,
            penerima_jabatan_id=data.penerima_jabatan_id,
            material=data.material,
            catatan=data.catatan,
            created_at=datetime.now(UTC),
        )
        self._s.add(rec)
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise PenerimaGandaError("Jabatan itu sudah menjadi penerima alternatif ini.") from exc
        self._s.refresh(rec)
        return _penerima_read(rec)

    def daftar_penerima(self, alternatif_id: str) -> list[PenerimaRead]:
        """Daftar penerima alternatif, urut `created_at` naik lalu `id`; 404 bila tak ada."""
        self._get_model(alternatif_id)
        m = RedesainAlternatifPenerimaModel
        rows = self._s.scalars(
            select(m).where(m.alternatif_id == alternatif_id).order_by(m.created_at, m.id)
        ).all()
        return [_penerima_read(r) for r in rows]

    def nilai_kesiapan(
        self, alternatif_id: str, data: KesiapanCreate, *, dinilai_oleh: str
    ) -> KesiapanRead:
        """Simpan penilaian kesiapan baru; tidak pernah menimpa penilaian lama.

        Raises:
            NotFoundError: alternatif tak ada.
            PenerimaBukanMilikAlternatifError: `penerima_id` bukan penerima alternatif ini.
        """
        self._get_model(alternatif_id)
        pm = RedesainAlternatifPenerimaModel
        penerima = self._s.get(pm, data.penerima_id)
        if penerima is None or penerima.alternatif_id != alternatif_id:
            raise PenerimaBukanMilikAlternatifError(
                f"Penerima '{data.penerima_id}' bukan milik alternatif '{alternatif_id}'."
            )
        rec = RedesainKesiapanModel(
            id=str(uuid.uuid4()),
            dinilai_oleh=dinilai_oleh,
            created_at=datetime.now(UTC),
            **{k: (v.value if hasattr(v, "value") else v) for k, v in data.model_dump().items()},
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _kesiapan_read(rec)

    def matriks_kesiapan(self, alternatif_id: str, periode: str) -> KesiapanMatriksRead:
        """Susun matriks kesiapan dari penilaian TERAKHIR tiap penerima pada `periode`.

        Penilaian terakhir = `created_at` terbesar, `id` sebagai pemutus seri. Penerima tanpa
        penilaian tampil dengan `status=None`.

        Raises:
            NotFoundError: alternatif tak ada.
        """
        self._get_model(alternatif_id)
        pm = RedesainAlternatifPenerimaModel
        km = RedesainKesiapanModel
        penerima = self._s.scalars(
            select(pm).where(pm.alternatif_id == alternatif_id).order_by(pm.created_at, pm.id)
        ).all()
        terakhir: dict[str, RedesainKesiapanModel] = {}
        if penerima:
            nilai = self._s.scalars(
                select(km)
                .where(km.penerima_id.in_([p.id for p in penerima]), km.periode == periode)
                .order_by(km.created_at, km.id)
            ).all()
            for n in nilai:  # urutan naik: yang terakhir menimpa
                terakhir[n.penerima_id] = n
        baris: list[KesiapanBaris] = []
        for p in penerima:
            n = terakhir.get(p.id)
            baris.append(
                KesiapanBaris(
                    penerima_id=p.id,
                    penerima_jabatan_id=p.penerima_jabatan_id,
                    material=p.material,
                    status=n.status if n else None,  # type: ignore[arg-type]
                    syarat=n.syarat if n else None,
                    alasan_hold=n.alasan_hold if n else None,
                    dinilai_pada=_aware(n.created_at) if n else None,
                    **{k: (getattr(n, k) if n else None) for k in _KOLOM_DELTA},
                )
            )
        status_opsi = hitung_status_opsi(
            (b.material, StatusKesiapan(b.status) if b.status else None) for b in baris
        )
        return KesiapanMatriksRead(
            alternatif_id=alternatif_id, periode=periode, status_opsi=status_opsi, baris=baris
        )

    def putuskan_perubahan(
        self, alternatif_id: str, data: KeputusanPerubahanCreate, *, pemutus: str
    ) -> KeputusanPerubahanRead:
        """Catat keputusan perubahan; status opsi dihitung ulang dari matriks saat itu.

        Raises:
            NotFoundError: alternatif tak ada.
            KesiapanBelumReadyError: APPROVE saat status opsi bukan READY.
            KesiapanHoldError: CONDITIONAL saat status opsi HOLD.
        """
        status_opsi = self.matriks_kesiapan(alternatif_id, data.periode).status_opsi
        if data.keputusan == KeputusanPerubahan.APPROVE and status_opsi != StatusKesiapan.READY:
            raise KesiapanBelumReadyError(
                f"APPROVE ditolak: status opsi periode {data.periode} adalah {status_opsi.value}."
            )
        if data.keputusan == KeputusanPerubahan.CONDITIONAL and status_opsi == StatusKesiapan.HOLD:
            raise KesiapanHoldError(
                f"CONDITIONAL ditolak: status opsi periode {data.periode} adalah HOLD."
            )
        rec = RedesainKeputusanPerubahanModel(
            id=str(uuid.uuid4()),
            alternatif_id=alternatif_id,
            periode=data.periode,
            keputusan=data.keputusan.value,
            alasan=data.alasan,
            stop_rule=data.stop_rule,
            status_opsi_saat_putus=status_opsi.value,
            pemutus_kode_orang=pemutus,
            created_at=datetime.now(UTC),
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _keputusan_read(rec)

    def riwayat_keputusan_perubahan(
        self, alternatif_id: str, periode: str | None
    ) -> list[KeputusanPerubahanRead]:
        """Riwayat keputusan perubahan urut `created_at` naik lalu `id`; 404 bila tak ada."""
        self._get_model(alternatif_id)
        m = RedesainKeputusanPerubahanModel
        stmt = select(m).where(m.alternatif_id == alternatif_id)
        if periode is not None:
            stmt = stmt.where(m.periode == periode)
        rows = self._s.scalars(stmt.order_by(m.created_at, m.id)).all()
        return [_keputusan_read(r) for r in rows]
