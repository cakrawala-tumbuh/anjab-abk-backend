"""Implementasi `TiRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiRespondenService` TANPA mengubah kontrak Protocol.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.services.partisipan import PartisipanService
from ...core.services.sekolah import SekolahService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import PartisipanModel, TiRespondenModel, TiSesiModel
from ...schemas.common import BulkAssignResult, BulkSkipped
from ..schemas.responden import TiRespondenCreate, TiRespondenRead


def _to_read(rec: TiRespondenModel) -> TiRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    t1 = rec.tahap1_submitted_at
    if t1 is not None and t1.tzinfo is None:
        t1 = t1.replace(tzinfo=UTC)
    t3 = rec.tahap3_submitted_at
    if t3 is not None and t3.tzinfo is None:
        t3 = t3.replace(tzinfo=UTC)
    return TiRespondenRead(
        id=rec.id,
        sesi_id=rec.sesi_id,
        nama=rec.nama,
        partisipan_id=rec.partisipan_id,
        tahap1_submit=rec.tahap1_submit,
        tahap1_submitted_at=t1,
        tahap3_submit=rec.tahap3_submit,
        tahap3_submitted_at=t3,
        created_at=created,
    )


def _resolve_cabang_partisipan(
    partisipan_service: PartisipanService,
    sekolah_service: SekolahService,
    partisipan_id: str,
) -> str | None:
    """Cabang seorang partisipan, ditentukan lewat sekolahnya (`schemas/common.py::Cabang`).

    Sumber tunggal cabang partisipan (backlog `anjab-abk-backend#41`) — dibaca lewat
    seam `core` (`PartisipanService` → `sekolah_id` → `SekolahService` → `cabang`),
    **bukan** query ORM lintas domain langsung (konvensi `CLAUDE.md` repo ini).

    Mengembalikan `None` ("tidak tahu") bila partisipan atau sekolahnya tidak
    ditemukan (data inkonsisten lintas domain), **atau** bila `sekolah.cabang`
    memang `NULL` — kedua kasus diperlakukan sama, sejalan aturan "tidak tahu ≠
    salah" yang menjaga seluruh gerbang cabang di modul ini tetap longgar untuk
    data yang belum lengkap. Tidak pernah melempar exception.

    Args:
        partisipan_service: seam `core` untuk resolusi `sekolah_id` partisipan.
        sekolah_service: seam `core` untuk resolusi `cabang` sekolah.
        partisipan_id: ID partisipan yang cabangnya hendak ditentukan.

    Returns:
        Nilai `Cabang` (`"Bandung"`/`"Semarang"`) bila diketahui, selain itu `None`.
    """
    try:
        partisipan = partisipan_service.get(partisipan_id)
    except NotFoundError:
        return None
    try:
        sekolah = sekolah_service.get(partisipan.sekolah_id)
    except NotFoundError:
        return None
    return sekolah.cabang


def assign_ti_responden_banyak(
    session: Session,
    sesi_id: str,
    partisipan_ids: list[str],
    *,
    cabang: str | None = None,
    sekolah_service: SekolahService | None = None,
) -> BulkAssignResult[TiRespondenRead]:
    """Assign banyak partisipan sekaligus sebagai responden Task Inventory.

    Dipakai baik oleh auto-populate saat sesi dibuat (`SqlTiSesiService.create()`)
    maupun endpoint bulk manual — **tidak** memvalidasi keanggotaan SME panel;
    pemanggil wajib menyaring `partisipan_ids` sebelum memanggil fungsi ini.

    Penyaringan cabang (backlog `anjab-abk-backend#41`) hanya aktif bila **kedua**
    `cabang` dan `sekolah_service` diberikan (non-`None`) — dipakai oleh
    `SqlTiSesiService.create()` untuk auto-populate; endpoint bulk manual
    (`SqlTiRespondenService.assign_banyak()`) sengaja memanggil fungsi ini TANPA
    kedua argumen ini, sehingga perilakunya tidak berubah. Saat aktif, partisipan
    yang cabang sekolahnya **diketahui dan berbeda** dari `cabang` dilewati dengan
    alasan `beda_cabang` (`sekolah.cabang` `NULL` → "tidak tahu", tetap
    diloloskan). `sekolah.cabang` dicache per `sekolah_id` dalam satu pemanggilan
    agar partisipan satu sekolah tidak memicu lookup berulang.

    Args:
        session: sesi SQLAlchemy aktif (satu per request).
        sesi_id: ID sesi Task Inventory tujuan.
        partisipan_ids: daftar ID partisipan yang hendak di-assign.
        cabang: cabang sesi tujuan; `None` menonaktifkan penyaringan cabang.
        sekolah_service: seam resolusi cabang sekolah; wajib diisi bersama
            `cabang` agar penyaringan berjalan.

    Returns:
        `BulkAssignResult` — baris yang berhasil dibuat + yang dilewati beserta
        alasannya (`duplikat_input` | `sudah_terdaftar` | `beda_cabang`).
    """
    skipped: list[BulkSkipped] = []
    seen: set[str] = set()
    candidates: list[str] = []
    for partisipan_id in partisipan_ids:
        if partisipan_id in seen:
            skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="duplikat_input"))
            continue
        seen.add(partisipan_id)
        candidates.append(partisipan_id)

    existing_ids: set[str] = set()
    if candidates:
        existing_ids = set(
            session.scalars(
                select(TiRespondenModel.partisipan_id).where(
                    TiRespondenModel.sesi_id == sesi_id,
                    TiRespondenModel.partisipan_id.in_(candidates),
                )
            ).all()
        )

    to_create = [pid for pid in candidates if pid not in existing_ids]
    par_map: dict[str, PartisipanModel] = {}
    if to_create:
        par_rows = session.scalars(
            select(PartisipanModel).where(PartisipanModel.id.in_(to_create))
        ).all()
        par_map = {p.id: p for p in par_rows}

    cabang_filtering = cabang is not None and sekolah_service is not None
    sekolah_cabang_cache: dict[str, str | None] = {}

    def _cabang_sekolah(sekolah_id: str) -> str | None:
        if sekolah_id not in sekolah_cabang_cache:
            try:
                sekolah_cabang_cache[sekolah_id] = sekolah_service.get(sekolah_id).cabang  # type: ignore[union-attr]
            except NotFoundError:
                sekolah_cabang_cache[sekolah_id] = None
        return sekolah_cabang_cache[sekolah_id]

    created: list[TiRespondenRead] = []
    for partisipan_id in candidates:
        if partisipan_id in existing_ids:
            skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="sudah_terdaftar"))
            continue
        par = par_map.get(partisipan_id)
        if cabang_filtering and par is not None:
            par_cabang = _cabang_sekolah(par.sekolah_id)
            if par_cabang is not None and par_cabang != cabang:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="beda_cabang"))
                continue
        rec = TiRespondenModel(
            id=f"trsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=par.nama if par else None,
            partisipan_id=partisipan_id,
            tahap1_submit=False,
            tahap3_submit=False,
        )
        session.add(rec)
        session.flush()
        created.append(_to_read(rec))

    return BulkAssignResult(created=created, skipped=skipped)


class SqlTiRespondenService:
    """`TiRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(
        self,
        session: Session,
        partisipan_service: PartisipanService,
        sekolah_service: SekolahService,
    ) -> None:
        self._s = session
        self._par = partisipan_service
        self._sek = sekolah_service

    def _get_model(self, responden_id: str) -> TiRespondenModel:
        rec = self._s.get(TiRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
        return rec

    def list_by_sesi(
        self, sesi_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[TiRespondenRead], int]:
        total = (
            self._s.scalar(
                select(func.count())
                .select_from(TiRespondenModel)
                .where(TiRespondenModel.sesi_id == sesi_id)
            )
            or 0
        )
        stmt = (
            select(TiRespondenModel)
            .where(TiRespondenModel.sesi_id == sesi_id)
            .order_by(TiRespondenModel.created_at.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        rows = self._s.scalars(stmt).all()
        return [_to_read(r) for r in rows], total

    def list_by_partisipan(self, partisipan_id: str) -> list[TiRespondenRead]:
        rows = self._s.scalars(
            select(TiRespondenModel)
            .where(TiRespondenModel.partisipan_id == partisipan_id)
            .order_by(TiRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def count_by_sesi(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(TiRespondenModel)
                .where(TiRespondenModel.sesi_id == sesi_id)
            )
            or 0
        )

    def count_tahap1_submitted(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(TiRespondenModel)
                .where(
                    TiRespondenModel.sesi_id == sesi_id,
                    TiRespondenModel.tahap1_submit.is_(True),
                )
            )
            or 0
        )

    def get(self, responden_id: str) -> TiRespondenRead:
        return _to_read(self._get_model(responden_id))

    def create(self, sesi_id: str, data: TiRespondenCreate) -> TiRespondenRead:
        """Daftarkan satu responden pada sesi Task Inventory `sesi_id`.

        Menolak (`ConflictError`, 409) bila `data.partisipan_id` **non-null** dan
        partisipan itu sudah punya baris responden di sesi yang sama
        (backlog `anjab-abk-backend#29`) — dicek eksplisit di sini, SEBELUM
        `INSERT`, agar pesannya spesifik alih-alih pesan generik
        `IntegrityError`. `UniqueConstraint("sesi_id", "partisipan_id")`
        (`uq_ti_responden_sesi_partisipan`) di `TiRespondenModel` tetap ada
        sebagai jaring pengaman lapisan DB untuk race dua request bersamaan.
        `partisipan_id = NULL` (responden manual tanpa partisipan) TIDAK
        dicek — boleh berulang.

        **Gerbang cabang** (backlog `anjab-abk-backend#41`), diletakkan
        **setelah** gerbang duplikat di atas agar `409` tetap menang untuk
        kasus yang sama: menolak (`ValidationAppError`, 422) bila
        `data.partisipan_id` non-null, sesi ini punya `cabang` yang diketahui,
        dan cabang sekolah partisipan (`_resolve_cabang_partisipan`) juga
        diketahui tapi **berbeda** dari cabang sesi. Sesi tanpa `cabang`, atau
        partisipan yang cabangnya tidak diketahui (sekolah belum diisi
        `cabang`, atau partisipan/sekolah tidak ditemukan), **diloloskan** —
        aturan "tidak tahu ≠ salah".

        Args:
            sesi_id: ID sesi Task Inventory tujuan.
            data: payload pembuatan responden (`nama`, `partisipan_id` opsional).

        Returns:
            Responden yang baru dibuat.

        Raises:
            ConflictError: `data.partisipan_id` non-null sudah terdaftar sebagai
                responden pada `sesi_id` ini.
            ValidationAppError: cabang sekolah partisipan diketahui dan berbeda
                dari cabang sesi (keduanya diketahui).
        """
        if data.partisipan_id is not None:
            sudah_ada = self._s.scalar(
                select(TiRespondenModel.id).where(
                    TiRespondenModel.sesi_id == sesi_id,
                    TiRespondenModel.partisipan_id == data.partisipan_id,
                )
            )
            if sudah_ada is not None:
                raise ConflictError(
                    "Partisipan ini sudah terdaftar sebagai responden pada sesi ini."
                )
            sesi_rec = self._s.get(TiSesiModel, sesi_id)
            sesi_cabang = sesi_rec.cabang if sesi_rec is not None else None
            if sesi_cabang is not None:
                par_cabang = _resolve_cabang_partisipan(self._par, self._sek, data.partisipan_id)
                if par_cabang is not None and par_cabang != sesi_cabang:
                    raise ValidationAppError(
                        f"Partisipan bercabang '{par_cabang}' tidak dapat ditambahkan"
                        f" ke sesi bercabang '{sesi_cabang}'."
                    )
        rec = TiRespondenModel(
            id=f"trsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=data.nama,
            partisipan_id=data.partisipan_id,
            tahap1_submit=False,
            tahap3_submit=False,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def assign_banyak(
        self, sesi_id: str, partisipan_ids: list[str]
    ) -> BulkAssignResult[TiRespondenRead]:
        return assign_ti_responden_banyak(self._s, sesi_id, partisipan_ids)

    def mark_tahap1(self, responden_id: str) -> TiRespondenRead:
        rec = self._get_model(responden_id)
        if rec.tahap1_submit:
            raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 1.")
        rec.tahap1_submit = True
        rec.tahap1_submitted_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def mark_tahap3(self, responden_id: str) -> TiRespondenRead:
        rec = self._get_model(responden_id)
        if rec.tahap3_submit:
            raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 3.")
        rec.tahap3_submit = True
        rec.tahap3_submitted_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def delete(self, responden_id: str) -> None:
        rec = self._get_model(responden_id)
        if rec.tahap1_submit or rec.tahap3_submit:
            raise ValidationAppError("Responden yang sudah submit (Tahap 1/3) tidak dapat dihapus.")
        self._s.delete(rec)
        self._s.flush()
