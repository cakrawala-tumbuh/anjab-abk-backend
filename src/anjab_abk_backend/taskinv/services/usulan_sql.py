"""Implementasi `TiUsulanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiUsulanService` TANPA mengubah kontrak Protocol.

`tugas_pokok_id`/`detil_tugas_id` di `TiUsulanTaskModel` sengaja BUKAN `ForeignKey`
(lihat docstring model) — nama induknya diresolusi live lewat `TugasPokokService`/
`DetilTugasService` yang di-inject ke konstruktor, dengan fallback ke id mentah bila
induknya sudah terhapus dari master data (pola sama dengan resolusi `jabatan_label`
di `SqlDcsRespondenService`/`SqlWcpRespondenService`, lihat entri `[2026-07-14]` di
`CLAUDE.md`).

`materialize_approved` (backlog `anjab-abk-backend#27`) menulis langsung ke
`TiUraianTugasModel`/`TiUraianTugasJabatanModel` (bukan lewat `UraianTugasService`)
— keduanya sama-sama tabel domain `taskinv`, dan validasi jabatan↔detil_tugas yang
dilakukan `SqlUraianTugasService.create()` sudah ditegakkan saat usulan itu SENDIRI
dibuat (`api/v1/taskinv_usulan.py::_validasi_induk_usulan`, backlog #26) — mengulang
validasi itu di sini hanya menambah query tanpa manfaat baru.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import TiUraianTugasJabatanModel, TiUraianTugasModel, TiUsulanTaskModel
from ..schemas.usulan import TiUsulanCreate, TiUsulanRead
from .detil_tugas import DetilTugasService
from .tugas_pokok import TugasPokokService

logger = logging.getLogger(__name__)

# Percobaan maksimum menghasilkan kode acak unik sebelum menyerah (lihat
# `_generate_kode_katalog`) — tabrakan berulang pada ruang 16**8 kemungkinan
# nyaris nol; batas ini murni jaring pengaman terhadap infinite loop.
_MAX_KODE_RETRY = 8


class SqlTiUsulanService:
    """`TiUsulanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(
        self, session: Session, tp_svc: TugasPokokService, dt_svc: DetilTugasService
    ) -> None:
        self._s = session
        self._tp = tp_svc
        self._dt = dt_svc

    def _resolve_nama_tugas_pokok(self, tugas_pokok_id: str) -> str:
        try:
            return self._tp.get(tugas_pokok_id).nama
        except NotFoundError:
            logger.warning(
                "usulan_tugas_pokok_tidak_ditemukan", extra={"tugas_pokok_id": tugas_pokok_id}
            )
            return tugas_pokok_id

    def _resolve_nama_detil_tugas(self, detil_tugas_id: str | None) -> str | None:
        if detil_tugas_id is None:
            return None
        try:
            return self._dt.get(detil_tugas_id).nama
        except NotFoundError:
            logger.warning(
                "usulan_detil_tugas_tidak_ditemukan", extra={"detil_tugas_id": detil_tugas_id}
            )
            return detil_tugas_id

    def _to_read(self, rec: TiUsulanTaskModel) -> TiUsulanRead:
        created = rec.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return TiUsulanRead(
            id=rec.id,
            sesi_id=rec.sesi_id,
            responden_id=rec.responden_id,
            tugas_pokok_id=rec.tugas_pokok_id,
            tugas_pokok=self._resolve_nama_tugas_pokok(rec.tugas_pokok_id),
            detil_tugas_id=rec.detil_tugas_id,
            detil_tugas=self._resolve_nama_detil_tugas(rec.detil_tugas_id),
            uraian=rec.uraian,
            disetujui=rec.disetujui,
            task_kode=rec.task_kode,
            created_at=created,
        )

    def _get_model(self, usulan_id: str) -> TiUsulanTaskModel:
        rec = self._s.get(TiUsulanTaskModel, usulan_id)
        if rec is None:
            raise NotFoundError(f"Usulan '{usulan_id}' tidak ditemukan.")
        return rec

    def create(self, responden_id: str, sesi_id: str, data: TiUsulanCreate) -> TiUsulanRead:
        rec = TiUsulanTaskModel(
            id=f"tius_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            responden_id=responden_id,
            tugas_pokok_id=data.tugas_pokok_id,
            detil_tugas_id=data.detil_tugas_id,
            uraian=data.uraian,
        )
        self._s.add(rec)
        self._s.flush()
        return self._to_read(rec)

    def get(self, usulan_id: str) -> TiUsulanRead:
        return self._to_read(self._get_model(usulan_id))

    def list_by_responden(self, responden_id: str) -> list[TiUsulanRead]:
        rows = self._s.scalars(
            select(TiUsulanTaskModel)
            .where(TiUsulanTaskModel.responden_id == responden_id)
            .order_by(TiUsulanTaskModel.created_at)
        ).all()
        return [self._to_read(r) for r in rows]

    def list_by_sesi(self, sesi_id: str) -> list[TiUsulanRead]:
        rows = self._s.scalars(
            select(TiUsulanTaskModel)
            .where(TiUsulanTaskModel.sesi_id == sesi_id)
            .order_by(TiUsulanTaskModel.created_at)
        ).all()
        return [self._to_read(r) for r in rows]

    def set_keputusan(self, usulan_id: str, disetujui: bool) -> TiUsulanRead:
        rec = self._get_model(usulan_id)
        rec.disetujui = disetujui
        self._s.flush()
        return self._to_read(rec)

    def _derive_unit(self, jabatan_id: str, tugas_pokok_id: str, usulan_id: str) -> str:
        """Turunkan `unit` baris katalog baru dari baris katalog jabatan yang sudah ada.

        Bila `jabatan_id` punya lebih dari satu `unit` di katalog, dipersempit ke
        baris di bawah `tugas_pokok_id` yang sama. Ambigu (0 atau >1 hasil setelah
        dipersempit) atau `jabatan_id` sama sekali tidak punya baris katalog →
        `ValidationAppError` (422), menyebut `usulan_id` yang gagal.
        """
        units = self._s.scalars(
            select(TiUraianTugasJabatanModel.unit)
            .where(TiUraianTugasJabatanModel.jabatan_id == jabatan_id)
            .distinct()
        ).all()
        if not units:
            raise ValidationAppError(
                f"Tidak dapat menurunkan unit untuk usulan '{usulan_id}':"
                f" jabatan '{jabatan_id}' belum punya satu pun baris katalog."
            )
        if len(units) == 1:
            return units[0]
        narrowed = self._s.scalars(
            select(TiUraianTugasJabatanModel.unit)
            .where(
                TiUraianTugasJabatanModel.jabatan_id == jabatan_id,
                TiUraianTugasJabatanModel.tugas_pokok_id == tugas_pokok_id,
            )
            .distinct()
        ).all()
        if len(narrowed) == 1:
            return narrowed[0]
        raise ValidationAppError(
            f"Tidak dapat menurunkan unit untuk usulan '{usulan_id}': jabatan"
            f" '{jabatan_id}' punya lebih dari satu unit di katalog tanpa kecocokan"
            " tunggal pada tugas pokok induknya."
        )

    def _generate_kode_katalog(self) -> str:
        for _ in range(_MAX_KODE_RETRY):
            kode = f"TIU{uuid.uuid4().hex[:8]}"
            exists = self._s.scalar(
                select(TiUraianTugasJabatanModel.id).where(TiUraianTugasJabatanModel.kode == kode)
            )
            if exists is None:
                return kode
        raise ValidationAppError(
            "Gagal menghasilkan kode task unik untuk materialisasi usulan"
            f" setelah {_MAX_KODE_RETRY} percobaan."
        )

    def materialize_approved(self, sesi_id: str, jabatan_id: str) -> list[str]:
        """Materialisasi usulan disetujui sesi ini menjadi baris katalog `ti_uraian_tugas`.

        Untuk tiap usulan ber-`disetujui=True` dan `task_kode` masih NULL: turunkan
        `unit` (`_derive_unit`), hitung `urutan` = urutan maksimum kombinasi
        `jabatan_id`+`unit` + 1, buat satu baris `TiUraianTugasModel` +
        `TiUraianTugasJabatanModel` (seluruh `std_*` NULL) berkode `TIU<8 hex>`,
        lalu simpan kode itu ke `usulan.task_kode`. Usulan yang `task_kode`-nya
        sudah terisi DILEWATI (sekali jalan — aman dipanggil ulang tanpa
        menggandakan baris katalog). Mengembalikan SELURUH `task_kode` usulan
        disetujui sesi ini (lama + baru) untuk digabung pemanggil ke `final_kodes`.

        Melempar `ValidationAppError` (422) bila `unit` tidak dapat diturunkan
        untuk salah satu usulan — pemanggil (router `mulai_tahap3`) berjalan dalam
        satu sesi DB per-request, jadi exception ini membatalkan SELURUH transisi
        (baris katalog yang sempat ditambahkan di pemanggilan ini ikut rollback).
        """
        rows = self._s.scalars(
            select(TiUsulanTaskModel).where(
                TiUsulanTaskModel.sesi_id == sesi_id,
                TiUsulanTaskModel.disetujui.is_(True),
            )
        ).all()
        urutan_max: dict[str, int] = {}
        for rec in rows:
            if rec.task_kode is not None:
                continue  # sudah termaterialisasi sebelumnya
            unit = self._derive_unit(jabatan_id, rec.tugas_pokok_id, rec.id)
            if unit not in urutan_max:
                current_max = self._s.scalar(
                    select(func.max(TiUraianTugasJabatanModel.urutan)).where(
                        TiUraianTugasJabatanModel.jabatan_id == jabatan_id,
                        TiUraianTugasJabatanModel.unit == unit,
                    )
                )
                urutan_max[unit] = current_max or 0
            urutan_max[unit] += 1
            kode = self._generate_kode_katalog()
            link = TiUraianTugasJabatanModel(
                kode=kode,
                unit=unit,
                jabatan_id=jabatan_id,
                urutan=urutan_max[unit],
                tugas_pokok_id=rec.tugas_pokok_id,
                detil_tugas_id=rec.detil_tugas_id,
            )
            katalog_rec = TiUraianTugasModel(
                id=f"ut_{uuid.uuid4().hex[:8]}", uraian=rec.uraian, jabatan_links=[link]
            )
            self._s.add(katalog_rec)
            self._s.flush()
            rec.task_kode = kode
        self._s.flush()
        return sorted(r.task_kode for r in rows if r.task_kode is not None)

    def delete(self, usulan_id: str) -> None:
        rec = self._get_model(usulan_id)
        self._s.delete(rec)
        self._s.flush()
