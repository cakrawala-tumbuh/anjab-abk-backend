"""Implementasi `KoreksiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ForbiddenError, NotFoundError
from ...models import (
    RedesainKonfirmasiModel,
    RedesainKoreksiLangkahModel,
    RedesainLangkahModel,
    RedesainProsesModel,
)
from ..schemas.koreksi import AlurRead, KoreksiRead, LangkahAlurRead, ProsesAlurRead
from .konfirmasi_sql import KODE_DUGAAN_BELUM_DITAMPILKAN, KonfirmasiConflictError
from .riwayat import RiwayatService

ENTITAS_KOREKSI = "koreksi_langkah"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SqlKoreksiService:
    """`KoreksiService` berbasis PostgreSQL; terikat satu `Session` per request.

    Proses/langkah/konfirmasi (domain redesain sendiri) dibaca langsung dari tabelnya.
    Hanya `INSERT` — tidak ada jalur ubah/hapus koreksi.
    """

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def _to_read(self, rec: RedesainKoreksiLangkahModel) -> KoreksiRead:
        return KoreksiRead(
            id=rec.id,
            langkah_id=rec.langkah_id,
            konfirmasi_id=rec.konfirmasi_id,
            kode_orang=rec.kode_orang,
            isi=rec.isi,
            waktu=_aware(rec.waktu),
        )

    def _langkah_proses(self, langkah_id: str) -> tuple[RedesainLangkahModel, RedesainProsesModel]:
        langkah = self._s.get(RedesainLangkahModel, langkah_id)
        if langkah is None:
            raise NotFoundError(f"Langkah '{langkah_id}' tidak ditemukan.")
        proses = self._s.get(RedesainProsesModel, langkah.proses_id)
        assert proses is not None  # FK menjamin keberadaan
        return langkah, proses

    def _konfirmasi_milik(self, konfirmasi_id: str, kode_orang: str) -> RedesainKonfirmasiModel:
        """Ambil konfirmasi milik `kode_orang` yang dugaannya sudah tampil.

        Raises:
            NotFoundError: konfirmasi tak ada.
            ForbiddenError: milik orang lain.
            KonfirmasiConflictError: dugaan belum ditampilkan.
        """
        konf = self._s.get(RedesainKonfirmasiModel, konfirmasi_id)
        if konf is None:
            raise NotFoundError(f"Konfirmasi '{konfirmasi_id}' tidak ditemukan.")
        if konf.kode_orang != kode_orang:
            raise ForbiddenError("Akses ditolak: konfirmasi ini bukan milik Anda.")
        if konf.dugaan_ditampilkan_pada is None:
            raise KonfirmasiConflictError(
                KODE_DUGAAN_BELUM_DITAMPILKAN,
                "Dugaan belum ditampilkan; alur belum dapat dilihat atau dikoreksi.",
            )
        return konf

    def _simpan(
        self, langkah_id: str, konfirmasi_id: str | None, isi: str, kode_orang: str
    ) -> KoreksiRead:
        rec = RedesainKoreksiLangkahModel(
            id=str(uuid.uuid4()),
            langkah_id=langkah_id,
            konfirmasi_id=konfirmasi_id,
            kode_orang=kode_orang,
            isi=isi,
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        read = self._to_read(rec)
        self._riwayat.catat(
            ENTITAS_KOREKSI,
            read.id,
            "create",
            None,
            {"langkah_id": langkah_id, "konfirmasi_id": konfirmasi_id, "isi": isi},
            kode_orang,
        )
        return read

    def alur_untuk_konfirmasi(self, konfirmasi_id: str, *, kode_orang: str) -> AlurRead:
        """Proses masalah × sekolah konfirmasi beserta langkahnya (terurut `urutan`, `kode`).

        Proses sekolah lain tidak pernah ikut karena disaring `masalah_id` DAN `sekolah_id`.
        """
        konf = self._konfirmasi_milik(konfirmasi_id, kode_orang)
        p, lk = RedesainProsesModel, RedesainLangkahModel
        proses_list = self._s.scalars(
            select(p)
            .where(p.masalah_id == konf.masalah_id, p.sekolah_id == konf.sekolah_id)
            .order_by(p.kode)
        ).all()
        hasil: list[ProsesAlurRead] = []
        for pr in proses_list:
            langkah = self._s.scalars(
                select(lk).where(lk.proses_id == pr.id).order_by(lk.urutan, lk.kode)
            ).all()
            hasil.append(
                ProsesAlurRead(
                    id=pr.id,
                    kode=pr.kode,
                    periode=pr.periode,
                    nama_proses=pr.nama_proses,
                    langkah=[
                        LangkahAlurRead(
                            id=x.id,
                            kode=x.kode,
                            urutan=x.urutan,
                            tahap=x.tahap,
                            pemicu_input=x.pemicu_input,
                            pelaksana=x.pelaksana,
                            pekerjaan_sistem=x.pekerjaan_sistem,
                            keluaran_penerima=x.keluaran_penerima,
                            pemeriksa_pemutus=x.pemeriksa_pemutus,
                            hambatan=x.hambatan,
                            status_langkah=x.status_langkah,  # type: ignore[arg-type]
                        )
                        for x in langkah
                    ],
                )
            )
        return AlurRead(
            konfirmasi_id=konf.id,
            masalah_id=konf.masalah_id,
            sekolah_id=konf.sekolah_id,
            proses=hasil,
        )

    def tambah_oleh_tim(self, langkah_id: str, isi: str, *, kode_orang: str) -> KoreksiRead:
        """Tulis koreksi Tim (`konfirmasi_id` NULL)."""
        self._langkah_proses(langkah_id)
        return self._simpan(langkah_id, None, isi, kode_orang)

    def tambah_oleh_pengisi(
        self, langkah_id: str, isi: str, konfirmasi_id: str | None, *, kode_orang: str
    ) -> KoreksiRead:
        """Tulis koreksi pengisi: konfirmasi wajib milik pemanggil, dugaan tampil, dan
        masalah + sekolahnya sama dengan proses langkah."""
        _, proses = self._langkah_proses(langkah_id)
        if konfirmasi_id is None:
            raise ForbiddenError("Akses ditolak: `konfirmasi_id` wajib bagi sekolah pengisi.")
        konf = self._konfirmasi_milik(konfirmasi_id, kode_orang)
        if konf.masalah_id != proses.masalah_id or konf.sekolah_id != proses.sekolah_id:
            raise ForbiddenError("Akses ditolak: langkah ini di luar konfirmasi Anda.")
        return self._simpan(langkah_id, konf.id, isi, kode_orang)

    def list_by_langkah(
        self, langkah_id: str, *, limit: int, offset: int
    ) -> tuple[list[KoreksiRead], int]:
        """Koreksi sebuah langkah terurut `waktu` lalu `id`."""
        self._langkah_proses(langkah_id)
        k = RedesainKoreksiLangkahModel
        total = self._s.scalar(
            select(func.count()).select_from(k).where(k.langkah_id == langkah_id)
        )
        rows = self._s.scalars(
            select(k)
            .where(k.langkah_id == langkah_id)
            .order_by(k.waktu, k.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [self._to_read(r) for r in rows], int(total or 0)
