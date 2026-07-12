"""Implementasi `TiSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiSesiService` TANPA mengubah kontrak Protocol.

Uniqueness sesi diperiksa di aplikasi (sama dengan InMemory): (unit, jabatan_id,
periode) bila `unit` diisi, atau (jabatan_id, periode) bila `unit` None. State
machine `_VALID_TRANSITIONS` & whitelist search dipakai ULANG dari modul InMemory.

`task_terpilih` model bernilai None sampai di-freeze (`task_frozen=True`);
`freeze_task_terpilih` mengisi tabel anak `ti_sesi_task_terpilih`. `get_task_terpilih`
mengembalikan [] bila belum di-freeze.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import JabatanModel, SMEPanelModel, TiSesiModel, TiSesiTaskTerpilihModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import StatusSesi, TiSesiCreate, TiSesiRead, TiSesiUpdate
from .responden_sql import assign_ti_responden_banyak

# Sumber tunggal whitelist & state machine.
from .sesi import _ERR_NON_DRAFT, _VALID_TRANSITIONS, SEARCHABLE_FIELDS


def _sesi_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiSesiModel.id),
        "jabatan_id": FieldSpec(column=TiSesiModel.jabatan_id),
        "periode": FieldSpec(column=TiSesiModel.periode),
        "status": FieldSpec(column=TiSesiModel.status),
        "created_at": FieldSpec(column=TiSesiModel.created_at, order_column=TiSesiModel.created_at),
    }


def _to_read(rec: TiSesiModel, jabatan_nama: str | None = None) -> TiSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    terpilih = rec.task_terpilih  # None bila belum di-freeze
    return TiSesiRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        jabatan_nama=jabatan_nama,
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        koordinator_id=rec.koordinator_id,
        min_responden=rec.min_responden,
        max_responden=rec.max_responden,
        jumlah_task_terpilih=(len(terpilih) if terpilih is not None else None),
        catatan=rec.catatan,
        created_at=created,
    )


class SqlTiSesiService:
    """`TiSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sesi_id: str) -> TiSesiModel:
        rec = self._s.get(TiSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
        return rec

    def _jabatan_map(self, jabatan_ids: list[str]) -> dict[str, str]:
        if not jabatan_ids:
            return {}
        rows = self._s.scalars(select(JabatanModel).where(JabatanModel.id.in_(jabatan_ids))).all()
        return {j.id: j.nama for j in rows}

    def list(self, *, limit: int, offset: int) -> tuple[list[TiSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiSesiModel)) or 0
        rows = self._s.scalars(
            select(TiSesiModel).order_by(TiSesiModel.created_at.desc()).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total

    def get(self, sesi_id: str) -> TiSesiRead:
        rec = self._get_model(sesi_id)
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def create(self, data: TiSesiCreate) -> TiSesiRead:
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        dup = self._s.scalar(
            select(TiSesiModel.id).where(
                TiSesiModel.jabatan_id == data.jabatan_id,
                TiSesiModel.periode == data.periode,
            )
        )
        if dup is not None:
            raise ConflictError(
                f"Sesi untuk jabatan '{data.jabatan_id}'" f" periode '{data.periode}' sudah ada."
            )
        rec = TiSesiModel(
            id=f"tises_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            periode=data.periode,
            status="DRAFT",
            koordinator_id=data.koordinator_id,
            min_responden=data.min_responden,
            max_responden=data.max_responden,
            catatan=data.catatan,
        )
        self._s.add(rec)
        # Flush sesi TERLEBIH DAHULU, sebelum insert responden auto-populate di
        # bawah. `TiRespondenModel.sesi_id` adalah FK murni tanpa `relationship()`
        # ORM ke `TiSesiModel` — tanpa flush eksplisit ini, urutan INSERT saat
        # flush gabungan TIDAK terjamin (unit-of-work SQLAlchemy mengurutkan
        # INSERT berdasar `relationship()` yang dikonfigurasi, bukan sekadar FK
        # kolom mentah), sehingga bisa mencoba INSERT responden sebelum sesi ada
        # → `ForeignKeyViolation`. Diverifikasi lewat E2E yang mereproduksi
        # persis kegagalan ini (lihat CHANGELOG).
        self._s.flush()

        # Auto-populate best-effort: anggota SME panel jabatan ini langsung jadi
        # responden. Panel tidak ada/kosong → sesi tetap dibuat kosong (tidak error).
        panel = self._s.scalar(
            select(SMEPanelModel).where(SMEPanelModel.jabatan_id == data.jabatan_id)
        )
        if panel is not None and panel.anggota:
            assign_ti_responden_banyak(
                self._s, rec.id, panel.partisipan_ids, max_responden=data.max_responden
            )
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def update(self, sesi_id: str, data: TiSesiUpdate) -> TiSesiRead:
        rec = self._get_model(sesi_id)
        changes = data.model_dump(exclude_unset=True)
        if rec.status != "DRAFT" and any(k != "koordinator_id" for k in changes):
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
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

    def freeze_task_terpilih(self, sesi_id: str, kodes: list[str]) -> TiSesiRead:
        """Bekukan himpunan task terpilih saat transisi TAHAP2 → TAHAP3."""
        rec = self._get_model(sesi_id)
        if rec.status != "TAHAP2":
            raise ValidationAppError(
                f"Himpunan task hanya dapat dibekukan dari status TAHAP2"
                f" (saat ini: {rec.status})."
            )
        if not kodes:
            raise ValidationAppError("Tidak ada task relevan; tidak dapat masuk TAHAP3.")
        rec.task_terpilih_links.clear()
        for kode in sorted(set(kodes)):
            rec.task_terpilih_links.append(TiSesiTaskTerpilihModel(task_kode=kode))
        rec.task_frozen = True
        rec.status = "TAHAP3"
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def get_task_terpilih(self, sesi_id: str) -> list[str]:
        rec = self._get_model(sesi_id)
        terpilih = rec.task_terpilih
        return list(terpilih) if terpilih is not None else []

    def transition(self, sesi_id: str, target: StatusSesi) -> TiSesiRead:
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

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TiSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _sesi_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [TiSesiModel.created_at.desc()]
        total = self._s.scalar(select(func.count()).select_from(TiSesiModel).where(cond)) or 0
        rows = self._s.scalars(
            select(TiSesiModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total
