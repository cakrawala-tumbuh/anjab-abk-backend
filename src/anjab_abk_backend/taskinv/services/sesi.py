"""SEAM akses data untuk resource `TiSesi` (sesi Task Inventory)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.sesi import StatusSesi, TiSesiCreate, TiSesiRead, TiSesiUpdate

SEARCHABLE_FIELDS = frozenset({"id", "jabatan_id", "cabang", "status", "created_at"})

_VALID_TRANSITIONS: dict[StatusSesi, StatusSesi] = {
    "DRAFT": "TAHAP1",
    "TAHAP1": "TAHAP2",
    "TAHAP2": "TAHAP3",
    "TAHAP3": "CLOSED",
    "CLOSED": "ANALYZED",
}

_ERR_NON_DRAFT = (
    "Sesi hanya dapat dihapus saat berstatus DRAFT."
    " Gunakan paksa=true untuk menghapus sesi beserta SELURUH responden & jawabannya."
)


@dataclass
class _Record:
    id: str
    jabatan_id: str
    cabang: str | None
    status: str
    created_at: datetime
    koordinator_id: str | None = None
    catatan: str | None = None
    task_terpilih: list[str] | None = field(default=None)


class TiSesiService(Protocol):
    """Kontrak operasi terhadap TiSesi."""

    def list(self, *, limit: int, offset: int) -> tuple[list[TiSesiRead], int]: ...
    def get(self, sesi_id: str) -> TiSesiRead: ...
    def create(self, data: TiSesiCreate) -> TiSesiRead: ...
    def update(self, sesi_id: str, data: TiSesiUpdate) -> TiSesiRead: ...
    def delete(self, sesi_id: str, *, paksa: bool = False) -> None: ...
    def transition(self, sesi_id: str, target: StatusSesi) -> TiSesiRead: ...
    def freeze_task_terpilih(self, sesi_id: str, kodes: list[str]) -> TiSesiRead: ...
    def get_task_terpilih(self, sesi_id: str) -> list[str]: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TiSesiRead], int]: ...


class InMemoryTiSesiService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TiSesiRead:
        return TiSesiRead(
            id=rec.id,
            jabatan_id=rec.jabatan_id,
            cabang=rec.cabang,  # type: ignore[arg-type]
            status=rec.status,  # type: ignore[arg-type]
            koordinator_id=rec.koordinator_id,
            jumlah_task_terpilih=(
                len(rec.task_terpilih) if rec.task_terpilih is not None else None
            ),
            catatan=rec.catatan,
            created_at=rec.created_at,
        )

    def list(self, *, limit: int, offset: int) -> tuple[list[TiSesiRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sesi_id: str) -> TiSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: TiSesiCreate) -> TiSesiRead:
        # Seam in-memory ini TIDAK punya akses ke data SME panel (tidak ada store
        # panel di sini) — berbeda dari `SqlTiSesiService.create()` yang mewarisi
        # `koordinator_id` dari `SmePanel.koordinator_id` jabatan bila payload tidak
        # mengirimnya. Perilaku itu sengaja TIDAK direplikasi di seam ini.
        with self._lock:
            if any(
                r.jabatan_id == data.jabatan_id and r.cabang == data.cabang
                for r in self._data.values()
            ):
                raise ConflictError(
                    f"Sesi untuk jabatan '{data.jabatan_id}' cabang '{data.cabang}' sudah ada."
                )
            rec = _Record(
                id=f"tises_{uuid.uuid4().hex[:8]}",
                jabatan_id=data.jabatan_id,
                cabang=data.cabang,
                status="DRAFT",
                koordinator_id=data.koordinator_id,
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sesi_id: str, data: TiSesiUpdate) -> TiSesiRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT" and any(k != "koordinator_id" for k in changes):
                raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, sesi_id: str, *, paksa: bool = False) -> None:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT" and not paksa:
                raise ValidationAppError(_ERR_NON_DRAFT)
            del self._data[sesi_id]

    def transition(self, sesi_id: str, target: StatusSesi) -> TiSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
            expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
            if expected != target:
                raise ValidationAppError(
                    f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                    f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
                )
            rec.status = target
            return self._to_read(rec)

    def freeze_task_terpilih(self, sesi_id: str, kodes: list[str]) -> TiSesiRead:
        """Bekukan himpunan task terpilih saat transisi TAHAP2 → TAHAP3."""
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
            if rec.status != "TAHAP2":
                raise ValidationAppError(
                    f"Himpunan task hanya dapat dibekukan dari status TAHAP2"
                    f" (saat ini: {rec.status})."
                )
            if not kodes:
                raise ValidationAppError("Tidak ada task relevan; tidak dapat masuk TAHAP3.")
            rec.task_terpilih = sorted(set(kodes))
            rec.status = "TAHAP3"
            return self._to_read(rec)

    def get_task_terpilih(self, sesi_id: str) -> list[str]:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
            return list(rec.task_terpilih) if rec.task_terpilih is not None else []

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TiSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [
                {
                    "id": r.id,
                    "jabatan_id": r.jabatan_id,
                    "cabang": r.cabang,
                    "status": r.status,
                    "created_at": r.created_at,
                }
                for r in self._data.values()
            ]
            read_by_id = {r.id: self._to_read(r) for r in self._data.values()}
        page, total = run_search(records, domain, order, limit, offset)
        return [read_by_id[row["id"]] for row in page], total
