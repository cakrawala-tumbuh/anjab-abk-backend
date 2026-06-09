"""SEAM akses data untuk resource `DcsJawaban`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...errors import ConflictError
from ..schemas.jawaban import DcsJawabanBulkCreate, DcsJawabanRead


@dataclass
class _Record:
    id: str
    responden_id: str
    item_id: str
    skor_raw: int


class DcsJawabanService(Protocol):
    """Kontrak operasi terhadap DcsJawaban."""

    def list_by_responden(self, responden_id: str) -> list[DcsJawabanRead]: ...
    def bulk_create(
        self, responden_id: str, data: DcsJawabanBulkCreate, valid_item_ids: set[str]
    ) -> list[DcsJawabanRead]: ...
    def delete_by_responden(self, responden_id: str) -> None: ...


class InMemoryDcsJawabanService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> DcsJawabanRead:
        return DcsJawabanRead.model_validate(rec)

    def list_by_responden(self, responden_id: str) -> list[DcsJawabanRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.item_id,
            )
        return [self._to_read(r) for r in ordered]

    def get_raw_by_responden(self, responden_id: str) -> dict[str, int]:
        """Kembalikan mapping {item_id: skor_raw} untuk keperluan analisis."""
        with self._lock:
            return {
                r.item_id: r.skor_raw for r in self._data.values() if r.responden_id == responden_id
            }

    def bulk_create(
        self, responden_id: str, data: DcsJawabanBulkCreate, valid_item_ids: set[str]
    ) -> list[DcsJawabanRead]:
        submitted_ids = {j.item_id for j in data.jawaban}
        missing = valid_item_ids - submitted_ids
        if missing:
            raise ConflictError(
                f"Item berikut belum dijawab: {', '.join(sorted(missing)[:5])}..."
                if len(missing) > 5
                else f"Item berikut belum dijawab: {', '.join(sorted(missing))}."
            )
        unknown = submitted_ids - valid_item_ids
        if unknown:
            raise ConflictError(f"Item tidak dikenal: {', '.join(sorted(unknown))}.")

        with self._lock:
            already_exists = any(r.responden_id == responden_id for r in self._data.values())
            if already_exists:
                raise ConflictError(
                    f"Responden '{responden_id}' sudah memiliki jawaban. "
                    "Hapus terlebih dahulu jika ingin mengisi ulang."
                )
            new_records: list[_Record] = []
            for item in data.jawaban:
                rec = _Record(
                    id=f"djwb_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    item_id=item.item_id,
                    skor_raw=item.skor_raw,
                )
                self._data[rec.id] = rec
                new_records.append(rec)
        return [self._to_read(r) for r in new_records]

    def delete_by_responden(self, responden_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
