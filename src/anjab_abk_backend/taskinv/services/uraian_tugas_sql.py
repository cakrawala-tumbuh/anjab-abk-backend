"""Implementasi `UraianTugasService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryUraianTugasService` TANPA mengubah kontrak Protocol.

Sejak refactor m2m via association object (`anjab-abk-backend#23`), penyimpanan
terbagi dua tabel: `TiUraianTugasModel` (kanonik — hanya `id`/`uraian`/`created_at`)
dan `TiUraianTugasJabatanModel` (link per-jabatan — `kode`, `unit`, `jabatan_id`,
`urutan`, `tugas_pokok_id`, `detil_tugas_id`, `std_*`). Migrasi awal bersifat 1:1
non-lossy, sehingga **setiap kanonik yang dikelola lewat seam ini selalu punya TEPAT
SATU link** — `create()` selalu membuat pasangan kanonik+link sekaligus, dan
`delete()` menghapus kanonik yang mengalir ke link via cascade. Kontrak
`UraianTugasCreate`/`Update`/`Read` (satu `jabatan_id` per payload) dijaga identik;
pemanggil (router, catalog, seed) tidak perlu tahu pemisahan tabel ini.

`kode` unik global (kini kolom `TiUraianTugasJabatanModel.kode`, bukan lagi
`TiUraianTugasModel.kode`). Validasi "jabatan_id ∈ jabatan_ids DetilTugas induk"
(bila detil_tugas_id diisi) direplikasi langsung lewat query DB ke `ti_detil_tugas`,
alih-alih memanggil service lain. Parameter `dt_svc` dipertahankan agar signature
kompatibel dengan InMemory, tetapi tidak diperlukan oleh implementasi SQL.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import TiDetilTugasModel, TiUraianTugasJabatanModel, TiUraianTugasModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.uraian_tugas import UraianTugasCreate, UraianTugasRead, UraianTugasUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .uraian_tugas import SEARCHABLE_FIELDS

# Kolom link yang boleh disalin langsung dari payload create/update (semua field
# UraianTugasCreate/Update KECUALI `uraian`, yang tinggal di kanonik).
_LINK_FIELDS = (
    "kode",
    "unit",
    "jabatan_id",
    "urutan",
    "tugas_pokok_id",
    "detil_tugas_id",
    "std_sumber_bukti",
    "std_kondisi",
    "std_frekuensi_teks",
    "std_durasi_per_kali",
    "std_jam_per_minggu",
    "std_peak4w_hours",
    "std_va_type",
    "std_opm_importance",
    "std_opm_frequency",
    "std_opm_criticality",
)


def _uraian_tugas_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiUraianTugasModel.id),
        "kode": FieldSpec(column=TiUraianTugasJabatanModel.kode),
        "uraian": FieldSpec(column=TiUraianTugasModel.uraian),
        "unit": FieldSpec(column=TiUraianTugasJabatanModel.unit),
        "jabatan_id": FieldSpec(column=TiUraianTugasJabatanModel.jabatan_id),
        "urutan": FieldSpec(
            column=TiUraianTugasJabatanModel.urutan,
            order_column=TiUraianTugasJabatanModel.urutan,
        ),
        "detil_tugas_id": FieldSpec(column=TiUraianTugasJabatanModel.detil_tugas_id),
        "tugas_pokok_id": FieldSpec(column=TiUraianTugasJabatanModel.tugas_pokok_id),
        "created_at": FieldSpec(
            column=TiUraianTugasModel.created_at, order_column=TiUraianTugasModel.created_at
        ),
    }


def _to_read(rec: TiUraianTugasModel) -> UraianTugasRead:
    """Rakit `UraianTugasRead` dari kanonik + link tunggalnya (`rec.jabatan_links[0]`).

    `jabatan_links` dimuat eager (`lazy="selectin"`), jadi tidak ada query N+1.
    Non-lossy 1:1 dijamin oleh migrasi awal & `create()`/`delete()` di kelas ini.
    """
    if not rec.jabatan_links:
        raise NotFoundError(f"UraianTugas '{rec.id}' tidak memiliki link jabatan.")
    link = rec.jabatan_links[0]
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return UraianTugasRead(
        id=rec.id,
        kode=link.kode,
        uraian=rec.uraian,
        unit=link.unit,
        jabatan_id=link.jabatan_id,
        urutan=link.urutan,
        detil_tugas_id=link.detil_tugas_id,
        tugas_pokok_id=link.tugas_pokok_id,
        std_sumber_bukti=link.std_sumber_bukti,  # type: ignore[arg-type]
        std_kondisi=link.std_kondisi,  # type: ignore[arg-type]
        std_frekuensi_teks=link.std_frekuensi_teks,
        std_durasi_per_kali=link.std_durasi_per_kali,
        std_jam_per_minggu=link.std_jam_per_minggu,
        std_peak4w_hours=link.std_peak4w_hours,
        std_va_type=link.std_va_type,  # type: ignore[arg-type]
        std_opm_importance=link.std_opm_importance,
        std_opm_frequency=link.std_opm_frequency,
        std_opm_criticality=link.std_opm_criticality,
        created_at=created,
    )


class SqlUraianTugasService:
    """`UraianTugasService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session, *, dt_svc: Any | None = None) -> None:
        self._s = session
        self._dt = dt_svc  # tidak dipakai; validasi langsung lewat DB.

    def _get_model(self, ut_id: str) -> TiUraianTugasModel:
        rec = self._s.get(TiUraianTugasModel, ut_id)
        if rec is None:
            raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
        return rec

    def _get_link(self, rec: TiUraianTugasModel) -> TiUraianTugasJabatanModel:
        if not rec.jabatan_links:
            raise NotFoundError(f"UraianTugas '{rec.id}' tidak memiliki link jabatan.")
        return rec.jabatan_links[0]

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def _validate_jabatan_in_dt(self, jabatan_id: str, detil_tugas_id: str) -> None:
        dt = self._s.get(TiDetilTugasModel, detil_tugas_id)
        if dt is None:
            raise NotFoundError(f"DetilTugas '{detil_tugas_id}' tidak ditemukan.")
        if jabatan_id not in dt.jabatan_ids:
            raise ValidationAppError(
                f"Jabatan '{jabatan_id}' bukan bagian dari jabatan_ids"
                f" DetilTugas '{detil_tugas_id}'."
            )

    def _base_query(self):  # noqa: ANN202 — tipe Select generik, dipakai internal saja
        return select(TiUraianTugasModel).join(
            TiUraianTugasJabatanModel,
            TiUraianTugasJabatanModel.uraian_tugas_id == TiUraianTugasModel.id,
        )

    def list(self, *, limit: int, offset: int) -> tuple[list[UraianTugasRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiUraianTugasModel)) or 0
        rows = self._s.scalars(
            self._base_query()
            .order_by(
                TiUraianTugasJabatanModel.jabatan_id,
                TiUraianTugasJabatanModel.unit,
                TiUraianTugasJabatanModel.urutan,
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, ut_id: str) -> UraianTugasRead:
        return _to_read(self._get_model(ut_id))

    def get_by_kode(self, kode: str) -> UraianTugasRead:
        link = self._s.scalar(
            select(TiUraianTugasJabatanModel).where(TiUraianTugasJabatanModel.kode == kode)
        )
        if link is None:
            raise NotFoundError(f"UraianTugas dengan kode '{kode}' tidak ditemukan.")
        return _to_read(self._get_model(link.uraian_tugas_id))

    def create(self, data: UraianTugasCreate) -> UraianTugasRead:
        if data.detil_tugas_id:
            self._validate_jabatan_in_dt(data.jabatan_id, data.detil_tugas_id)
        exists = self._s.scalar(
            select(TiUraianTugasJabatanModel.id).where(TiUraianTugasJabatanModel.kode == data.kode)
        )
        if exists is not None:
            raise ConflictError(f"UraianTugas dengan kode '{data.kode}' sudah ada.")
        link = TiUraianTugasJabatanModel(**{f: getattr(data, f) for f in _LINK_FIELDS})
        rec = TiUraianTugasModel(
            id=f"ut_{uuid.uuid4().hex[:8]}",
            uraian=data.uraian,
            jabatan_links=[link],
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"UraianTugas dengan kode '{data.kode}' sudah ada.")
        return _to_read(rec)

    def update(self, ut_id: str, data: UraianTugasUpdate) -> UraianTugasRead:
        rec = self._get_model(ut_id)
        link = self._get_link(rec)
        changes = data.model_dump(exclude_unset=True)
        if "kode" in changes and changes["kode"] != link.kode:
            clash = self._s.scalar(
                select(TiUraianTugasJabatanModel.id).where(
                    TiUraianTugasJabatanModel.kode == changes["kode"],
                    TiUraianTugasJabatanModel.id != link.id,
                )
            )
            if clash is not None:
                raise ConflictError(f"UraianTugas dengan kode '{changes['kode']}' sudah ada.")
        new_jabatan_id = changes.get("jabatan_id", link.jabatan_id)
        new_detil_id = changes.get("detil_tugas_id", link.detil_tugas_id)
        if new_detil_id and ("jabatan_id" in changes or "detil_tugas_id" in changes):
            self._validate_jabatan_in_dt(new_jabatan_id, new_detil_id)
        if "uraian" in changes:
            rec.uraian = changes.pop("uraian")
        for key, value in changes.items():
            setattr(link, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, ut_id: str) -> None:
        rec = self._get_model(ut_id)
        self._s.delete(rec)  # cascade delete-orphan menghapus link (& ON DELETE CASCADE di DB)
        self._flush_checked(on_conflict="Tidak dapat menghapus UraianTugas.")

    def list_by_unit_jabatan(self, unit: str, jabatan_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            self._base_query()
            .where(
                TiUraianTugasJabatanModel.unit == unit,
                TiUraianTugasJabatanModel.jabatan_id == jabatan_id,
            )
            .order_by(TiUraianTugasJabatanModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_jabatan(self, jabatan_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            self._base_query()
            .where(TiUraianTugasJabatanModel.jabatan_id == jabatan_id)
            .order_by(TiUraianTugasJabatanModel.unit, TiUraianTugasJabatanModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_detil_tugas(self, dt_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            self._base_query()
            .where(TiUraianTugasJabatanModel.detil_tugas_id == dt_id)
            .order_by(TiUraianTugasJabatanModel.unit, TiUraianTugasJabatanModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_tugas_pokok(self, tp_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            self._base_query()
            .where(TiUraianTugasJabatanModel.tugas_pokok_id == tp_id)
            .order_by(TiUraianTugasJabatanModel.unit, TiUraianTugasJabatanModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]:
        rows = self._s.scalars(
            select(TiUraianTugasJabatanModel.kode).where(
                TiUraianTugasJabatanModel.unit == unit,
                TiUraianTugasJabatanModel.jabatan_id == jabatan_id,
            )
        ).all()
        return set(rows)

    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]:
        rows = self._s.scalars(
            select(TiUraianTugasJabatanModel.kode).where(
                TiUraianTugasJabatanModel.jabatan_id == jabatan_id
            )
        ).all()
        return set(rows)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[UraianTugasRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _uraian_tugas_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [
            TiUraianTugasJabatanModel.jabatan_id,
            TiUraianTugasJabatanModel.unit,
            TiUraianTugasJabatanModel.urutan,
        ]
        total = (
            self._s.scalar(
                select(func.count())
                .select_from(TiUraianTugasModel)
                .join(
                    TiUraianTugasJabatanModel,
                    TiUraianTugasJabatanModel.uraian_tugas_id == TiUraianTugasModel.id,
                )
                .where(cond)
            )
            or 0
        )
        rows = self._s.scalars(
            self._base_query().where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
