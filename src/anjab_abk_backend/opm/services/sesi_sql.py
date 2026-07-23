"""Implementasi `OpmSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

`create()` melakukan validasi lintas-domain (Jabatan, SME panel, Task Inventory)
lalu men-snapshot task terpilih TI ke `opm_sesi_task` dan membuat responden
otomatis dari seluruh anggota SME panel — semuanya dalam SATU transaksi (pola
`taskinv/services/sesi_sql.py::_jabatan_map`, `anjab/services/sme_panel_sql.py`
untuk pre-check `ConflictError` + backstop `IntegrityError`).
"""

from __future__ import annotations

import uuid
from datetime import UTC

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    JabatanModel,
    OpmRespondenModel,
    OpmSesiModel,
    OpmSesiTaskModel,
    PartisipanModel,
    SMEPanelModel,
    TiDetilTugasModel,
    TiSesiModel,
    TiTugasPokokModel,
    TiUraianTugasModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import OpmSesiCreate, OpmSesiRead, OpmSesiTaskRead, OpmSesiUpdate, StatusSesi

# Sumber tunggal whitelist & state machine.
from .sesi import _ERR_NON_DRAFT, _VALID_TRANSITIONS, SEARCHABLE_FIELDS


def _sesi_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=OpmSesiModel.id),
        "jabatan_id": FieldSpec(column=OpmSesiModel.jabatan_id),
        "ti_sesi_id": FieldSpec(column=OpmSesiModel.ti_sesi_id),
        "periode": FieldSpec(column=OpmSesiModel.periode),
        "status": FieldSpec(column=OpmSesiModel.status),
        "created_at": FieldSpec(
            column=OpmSesiModel.created_at, order_column=OpmSesiModel.created_at
        ),
    }


def _task_to_read(rec: OpmSesiTaskModel) -> OpmSesiTaskRead:
    return OpmSesiTaskRead(
        task_kode=rec.task_kode,
        uraian_tugas=rec.uraian_tugas,
        tugas_pokok=rec.tugas_pokok,
        detil_tugas=rec.detil_tugas,
        urutan=rec.urutan,
    )


def _to_read(rec: OpmSesiModel, jabatan_nama: str | None = None) -> OpmSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return OpmSesiRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        jabatan_nama=jabatan_nama,
        ti_sesi_id=rec.ti_sesi_id,
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        min_responden=rec.min_responden,
        max_responden=rec.max_responden,
        jumlah_task=len(rec.task_links),
        catatan=rec.catatan,
        created_at=created,
    )


class SqlOpmSesiService:
    """`OpmSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sesi_id: str) -> OpmSesiModel:
        rec = self._s.get(OpmSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
        return rec

    def _jabatan_map(self, jabatan_ids: list[str]) -> dict[str, str]:
        if not jabatan_ids:
            return {}
        rows = self._s.scalars(select(JabatanModel).where(JabatanModel.id.in_(jabatan_ids))).all()
        return {j.id: j.nama for j in rows}

    def _flush_checked(self, *, on_conflict: str) -> None:
        """Flush dalam SAVEPOINT; petakan **hanya** `UniqueViolation` → 409.

        Pelanggaran integritas lain (`ForeignKeyViolation`, NOT NULL, dst.) sengaja
        dibiarkan naik apa adanya: memetakannya jadi "sudah ada" menyamarkan bug
        nyata sebagai konflik duplikat yang mustahil. Persis itu yang menyembunyikan
        `ForeignKeyViolation` di `create()` selama dua sesi pengujian produksi.
        """
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise ConflictError(on_conflict) from exc
            raise

    def list(self, *, limit: int, offset: int) -> tuple[list[OpmSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(OpmSesiModel)) or 0
        rows = self._s.scalars(
            select(OpmSesiModel)
            .order_by(OpmSesiModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total

    def get(self, sesi_id: str) -> OpmSesiRead:
        rec = self._get_model(sesi_id)
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def create(self, data: OpmSesiCreate) -> OpmSesiRead:
        # 1. Jabatan wajib ada.
        jabatan = self._s.get(JabatanModel, data.jabatan_id)
        if jabatan is None:
            raise ValidationAppError(f"Jabatan '{data.jabatan_id}' tidak ditemukan.")

        # 2. min <= max.
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")

        # 3. Jabatan wajib punya SME panel dengan anggota.
        panel = self._s.scalar(
            select(SMEPanelModel).where(SMEPanelModel.jabatan_id == data.jabatan_id)
        )
        if panel is None or not panel.anggota:
            raise ValidationAppError(
                "Jabatan ini belum memiliki SME panel / panel belum punya anggota."
            )

        # 4. Pre-check satu sesi OPM per jabatan (backstop unique constraint di bawah).
        exists = self._s.scalar(
            select(OpmSesiModel.id).where(OpmSesiModel.jabatan_id == data.jabatan_id)
        )
        if exists is not None:
            raise ConflictError(f"Sesi OPM untuk jabatan '{data.jabatan_id}' sudah ada.")

        # 5. TiSesi sumber wajib ada, milik jabatan yang sama, dan sudah frozen.
        ti = self._s.get(TiSesiModel, data.ti_sesi_id)
        if ti is None:
            raise ValidationAppError(f"Sesi Task Inventory '{data.ti_sesi_id}' tidak ditemukan.")
        if ti.jabatan_id != data.jabatan_id:
            raise ValidationAppError("Sesi Task Inventory yang dipilih bukan untuk jabatan ini.")
        if not ti.task_frozen:
            raise ValidationAppError(
                "Sesi Task Inventory belum dibekukan (belum melewati Tahap 3)."
            )
        terpilih = ti.task_terpilih or []
        if not terpilih:
            raise ValidationAppError(
                "Sesi Task Inventory tidak memiliki task terpilih untuk dijadikan snapshot."
            )

        anggota_ids = panel.partisipan_ids
        if len(anggota_ids) > data.max_responden:
            raise ValidationAppError(
                f"Jumlah anggota SME panel ({len(anggota_ids)}) melebihi"
                f" max_responden ({data.max_responden})."
            )

        konflik = f"Sesi OPM untuk jabatan '{data.jabatan_id}' sudah ada."

        rec = OpmSesiModel(
            id=f"opses_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            ti_sesi_id=data.ti_sesi_id,
            periode=data.periode,
            status="DRAFT",
            min_responden=data.min_responden,
            max_responden=data.max_responden,
            catatan=data.catatan,
        )
        self._s.add(rec)
        # Flush sesi TERLEBIH DAHULU, sebelum insert responden auto-populate di
        # langkah 7. `OpmRespondenModel.sesi_id` adalah FK murni tanpa
        # `relationship()` ORM ke `OpmSesiModel` — tanpa flush eksplisit ini, urutan
        # INSERT saat flush gabungan TIDAK terjamin (unit-of-work SQLAlchemy
        # mengurutkan INSERT berdasar `relationship()` yang dikonfigurasi, bukan
        # sekadar FK kolom mentah), sehingga bisa mencoba INSERT responden sebelum
        # sesi ada → `ForeignKeyViolation`. Pola sama dengan `SqlTiSesiService.create()`.
        # Tetap lewat `_flush_checked` agar unique constraint `jabatan_id` tetap jadi
        # backstop 409 untuk race dua create bersamaan (pre-check langkah 4 lolos di
        # keduanya). `rec.task_links` (langkah 6) TIDAK terpengaruh — itu relationship,
        # urutannya memang dijamin.
        self._flush_checked(on_conflict=konflik)

        # 6. Snapshot task terpilih TI → opm_sesi_task.
        ut_rows = self._s.scalars(
            select(TiUraianTugasModel).where(TiUraianTugasModel.kode.in_(terpilih))
        ).all()
        ut_by_kode = {u.kode: u for u in ut_rows}
        tp_map = self._s.scalars(
            select(TiTugasPokokModel).where(
                TiTugasPokokModel.id.in_({u.tugas_pokok_id for u in ut_rows})
            )
        ).all()
        tp_by_id = {t.id: t.nama for t in tp_map}
        detil_ids = {u.detil_tugas_id for u in ut_rows if u.detil_tugas_id is not None}
        dt_map = (
            self._s.scalars(
                select(TiDetilTugasModel).where(TiDetilTugasModel.id.in_(detil_ids))
            ).all()
            if detil_ids
            else []
        )
        dt_by_id = {d.id: d.nama for d in dt_map}

        for kode in sorted(terpilih):
            ut = ut_by_kode.get(kode)
            if ut is None:
                continue  # tidak seharusnya terjadi; kode berasal dari snapshot TI valid
            rec.task_links.append(
                OpmSesiTaskModel(
                    task_kode=kode,
                    uraian_tugas=ut.uraian,
                    tugas_pokok=tp_by_id.get(ut.tugas_pokok_id, ""),
                    detil_tugas=dt_by_id.get(ut.detil_tugas_id) if ut.detil_tugas_id else None,
                    urutan=ut.urutan,
                )
            )

        # 7. Auto-responden dari anggota SME panel.
        par_map = (
            self._s.scalars(
                select(PartisipanModel).where(PartisipanModel.id.in_(anggota_ids))
            ).all()
            if anggota_ids
            else []
        )
        par_by_id = {p.id: p for p in par_map}
        for pid in anggota_ids:
            par = par_by_id.get(pid)
            self._s.add(
                OpmRespondenModel(
                    id=f"oprs_{uuid.uuid4().hex[:8]}",
                    sesi_id=rec.id,
                    nama=par.nama if par else None,
                    jabatan_label=jabatan.nama,
                    partisipan_id=pid,
                    sudah_submit=False,
                )
            )

        self._flush_checked(on_conflict=konflik)
        return _to_read(rec, jabatan.nama)

    def update(self, sesi_id: str, data: OpmSesiUpdate) -> OpmSesiRead:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT":
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
        changes = data.model_dump(exclude_unset=True)
        new_min = changes.get("min_responden", rec.min_responden)
        new_max = changes.get("max_responden", rec.max_responden)
        if new_min > new_max:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def delete(self, sesi_id: str, *, paksa: bool = False) -> None:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT" and not paksa:
            raise ValidationAppError(_ERR_NON_DRAFT)
        self._s.delete(rec)
        self._s.flush()
        self._s.expire_all()

    def transition(self, sesi_id: str, target: StatusSesi) -> OpmSesiRead:
        rec = self._get_model(sesi_id)
        expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
        if expected != target:
            raise ValidationAppError(
                f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
            )
        rec.status = target
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def list_task(
        self, sesi_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[OpmSesiTaskRead], int]:
        self._get_model(sesi_id)
        total = (
            self._s.scalar(
                select(func.count())
                .select_from(OpmSesiTaskModel)
                .where(OpmSesiTaskModel.sesi_id == sesi_id)
            )
            or 0
        )
        stmt = (
            select(OpmSesiTaskModel)
            .where(OpmSesiTaskModel.sesi_id == sesi_id)
            .order_by(OpmSesiTaskModel.urutan, OpmSesiTaskModel.task_kode)
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        rows = self._s.scalars(stmt).all()
        return [_task_to_read(r) for r in rows], total

    def get_task_kodes(self, sesi_id: str) -> set[str]:
        tasks, _ = self.list_task(sesi_id)
        return {t.task_kode for t in tasks}

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[OpmSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _sesi_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [OpmSesiModel.created_at.desc()]
        total = self._s.scalar(select(func.count()).select_from(OpmSesiModel).where(cond)) or 0
        rows = self._s.scalars(
            select(OpmSesiModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total
