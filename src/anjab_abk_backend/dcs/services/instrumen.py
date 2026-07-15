"""SEAM akses data untuk instrumen singleton `DcsInstrumen`."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import AppError, ValidationAppError
from ..schemas.instrumen import DcsInstrumenRead, DcsInstrumenUpdate, StatusInstrumenDcs

# Instrumen singleton: SATU baris tetap, dibuat oleh migrasi. Tidak ada create/delete.
INSTRUMEN_ID = "dcs"

_VALID_TRANSITIONS: dict[StatusInstrumenDcs, set[StatusInstrumenDcs]] = {
    "OPEN": {"CLOSED"},
    "CLOSED": {"OPEN", "ANALYZED"},
    "ANALYZED": set(),
}

_ERR_MISSING_ROW = (
    "Baris instrumen DCS ('dcs') tidak ditemukan. Ini menandakan migrasi database belum"
    " dijalankan dengan benar — baris ini WAJIB dibuat oleh migrasi, bukan diciptakan otomatis."
)


@dataclass
class _Record:
    id: str
    status: str
    min_responden: int
    created_at: datetime
    catatan: str | None = None
    closed_at: datetime | None = None


class DcsInstrumenService(Protocol):
    """Kontrak operasi terhadap instrumen singleton DCS (tanpa create/delete/list)."""

    def get(self) -> DcsInstrumenRead: ...
    def update(self, data: DcsInstrumenUpdate) -> DcsInstrumenRead: ...
    def tutup(self) -> DcsInstrumenRead: ...
    def buka_ulang(self) -> DcsInstrumenRead: ...
    def set_analyzed(self) -> DcsInstrumenRead: ...
    def reset(self) -> DcsInstrumenRead: ...


class InMemoryDcsInstrumenService:
    """Placeholder in-memory thread-safe. Baris awal dibuat di `__init__` (meniru migrasi).

    Tidak mengimplementasikan `reset()` — operasi itu butuh menghapus SEMUA baris
    `DcsResponden`, yang berada di seam terpisah tanpa referensi balik ke sini (pola
    yang sama dengan `InMemoryDcsRespondenService` yang tidak mengimplementasikan
    `create_banyak`). Implementasi nyata ada di `SqlDcsInstrumenService`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rec = _Record(
            id=INSTRUMEN_ID, status="OPEN", min_responden=6, created_at=datetime.now(UTC)
        )

    def _to_read(self) -> DcsInstrumenRead:
        return DcsInstrumenRead.model_validate(self._rec)

    def get(self) -> DcsInstrumenRead:
        with self._lock:
            if self._rec is None:
                raise AppError(_ERR_MISSING_ROW)
            return self._to_read()

    def update(self, data: DcsInstrumenUpdate) -> DcsInstrumenRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            for key, value in changes.items():
                setattr(self._rec, key, value)
            return self._to_read()

    def _transition(self, target: StatusInstrumenDcs) -> DcsInstrumenRead:
        with self._lock:
            current = self._rec.status
            allowed = _VALID_TRANSITIONS.get(current, set())  # type: ignore[arg-type]
            if target not in allowed:
                allowed_desc = sorted(allowed) or "(tidak ada)"
                raise ValidationAppError(
                    f"Transisi dari '{current}' ke '{target}' tidak valid."
                    f" Transisi yang diizinkan dari '{current}': {allowed_desc}."
                )
            self._rec.status = target
            if target == "CLOSED":
                self._rec.closed_at = datetime.now(UTC)
            return self._to_read()

    def tutup(self) -> DcsInstrumenRead:
        return self._transition("CLOSED")

    def buka_ulang(self) -> DcsInstrumenRead:
        return self._transition("OPEN")

    def set_analyzed(self) -> DcsInstrumenRead:
        return self._transition("ANALYZED")
