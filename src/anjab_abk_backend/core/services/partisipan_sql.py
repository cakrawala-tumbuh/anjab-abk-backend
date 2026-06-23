"""Implementasi `PartisipanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryPartisipanService` TANPA mengubah kontrak Protocol — signature &
return type identik, termasuk method khusus `get_by_subject(subject)` dan
`create(data, *, authentik_user_id=None)`. Validasi & pesan error meniru PERSIS
placeholder in-memory (`NotFoundError` 404).

`jabatan_tambahan_ids` disimpan di tabel anak `PartisipanJabatanTambahanModel`.
Saat update koleksi di-diff (hapus yang dibuang, tambah yang baru) agar tidak
melanggar `UniqueConstraint(partisipan_id, jabatan_id)`. `created_at` (TIMESTAMPTZ)
terisi via default Python setelah `flush()`.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import PartisipanJabatanTambahanModel, PartisipanModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.partisipan import PartisipanCreate, PartisipanRead, PartisipanUpdate
from .partisipan import SEARCHABLE_FIELDS


def _field_map() -> FieldMap:
    m = PartisipanModel
    return {
        "id": FieldSpec(column=m.id),
        "nama": FieldSpec(column=m.nama),
        "email": FieldSpec(column=m.email),
        "sekolah_id": FieldSpec(column=m.sekolah_id),
        "jabatan_utama_id": FieldSpec(column=m.jabatan_utama_id),
        "masa_kerja_tahun": FieldSpec(column=m.masa_kerja_tahun),
        "masa_kerja_bulan": FieldSpec(column=m.masa_kerja_bulan),
        "mata_pelajaran_utama_id": FieldSpec(column=m.mata_pelajaran_utama_id),
        "aktif": FieldSpec(column=m.aktif),
        "created_at": FieldSpec(column=m.created_at, order_column=m.created_at),
    }


def _to_read(rec: PartisipanModel) -> PartisipanRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return PartisipanRead(
        id=rec.id,
        nama=rec.nama,
        email=rec.email,
        authentik_user_id=rec.authentik_user_id,
        sekolah_id=rec.sekolah_id,
        jabatan_utama_id=rec.jabatan_utama_id,
        jabatan_tambahan_ids=rec.jabatan_tambahan_ids,
        masa_kerja_tahun=rec.masa_kerja_tahun,
        masa_kerja_bulan=rec.masa_kerja_bulan,
        mata_pelajaran_utama_id=rec.mata_pelajaran_utama_id,
        aktif=rec.aktif,
        created_at=created,
    )


class SqlPartisipanService:
    """`PartisipanService` berbasis PostgreSQL. Satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, partisipan_id: str) -> PartisipanModel:
        rec = self._s.get(PartisipanModel, partisipan_id)
        if rec is None:
            raise NotFoundError(f"Partisipan '{partisipan_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[PartisipanRead], int]:
        m = PartisipanModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.nama.asc()).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def get(self, partisipan_id: str) -> PartisipanRead:
        return _to_read(self._get_model(partisipan_id))

    def get_by_subject(self, subject: str) -> PartisipanRead | None:
        m = PartisipanModel
        rec = self._s.scalars(select(m).where(m.authentik_user_id == subject).limit(1)).first()
        if rec is None:
            rec = self._s.scalars(select(m).where(m.email == subject).limit(1)).first()
        if rec is None:
            return None
        return _to_read(rec)

    def create(
        self, data: PartisipanCreate, *, authentik_user_id: str | None = None
    ) -> PartisipanRead:
        rec = PartisipanModel(
            id=f"par_{uuid.uuid4().hex[:8]}",
            nama=data.nama,
            email=data.email,
            sekolah_id=data.sekolah_id,
            jabatan_utama_id=data.jabatan_utama_id,
            masa_kerja_tahun=data.masa_kerja_tahun,
            masa_kerja_bulan=data.masa_kerja_bulan,
            mata_pelajaran_utama_id=data.mata_pelajaran_utama_id,
            aktif=data.aktif,
            authentik_user_id=authentik_user_id,
            jabatan_tambahan=[
                PartisipanJabatanTambahanModel(jabatan_id=j)
                for j in dict.fromkeys(data.jabatan_tambahan_ids)
            ],
        )
        self._s.add(rec)
        self._flush_checked(on_conflict="Pembuatan partisipan melanggar batasan keunikan.")
        return _to_read(rec)

    def update(self, partisipan_id: str, data: PartisipanUpdate) -> PartisipanRead:
        rec = self._get_model(partisipan_id)
        changes = data.model_dump(exclude_unset=True)
        if "jabatan_tambahan_ids" in changes:
            desired = list(dict.fromkeys(changes.pop("jabatan_tambahan_ids")))
            current = {link.jabatan_id: link for link in rec.jabatan_tambahan}
            for jid, link in list(current.items()):
                if jid not in desired:
                    rec.jabatan_tambahan.remove(link)
            for jid in desired:
                if jid not in current:
                    rec.jabatan_tambahan.append(PartisipanJabatanTambahanModel(jabatan_id=jid))
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan partisipan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, partisipan_id: str) -> None:
        rec = self._get_model(partisipan_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus partisipan.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PartisipanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = PartisipanModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.nama.asc()]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
