"""SEAM akses data untuk resource `OpmJawaban`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ..schemas.jawaban import OpmJawabanBulkCreate, OpmJawabanRead


@dataclass
class _Record:
    id: str
    responden_id: str
    task_kode: str
    importance: int
    frequency: int
    criticality: int
    catatan: str | None = None


def _validate_task_set(kodes_list: list[str], valid_task_kodes: set[str]) -> None:
    """Set task_kode yang disubmit harus PERSIS sama dengan snapshot sesi."""
    kodes_set = set(kodes_list)
    missing = valid_task_kodes - kodes_set
    extra = kodes_set - valid_task_kodes
    duplicates = {k for k in kodes_set if kodes_list.count(k) > 1}
    if missing or extra or duplicates:
        problems = []
        if missing:
            problems.append(f"kurang: {', '.join(sorted(missing))}")
        if extra:
            problems.append(f"asing: {', '.join(sorted(extra))}")
        if duplicates:
            problems.append(f"duplikat: {', '.join(sorted(duplicates))}")
        raise ValidationAppError(
            "Set task jawaban tidak sesuai snapshot sesi (" + "; ".join(problems) + ")."
        )


class OpmJawabanService(Protocol):
    """Kontrak operasi terhadap OpmJawaban."""

    def list_by_responden(self, responden_id: str) -> list[OpmJawabanRead]: ...
    def get_raw_by_responden(self, responden_id: str) -> dict[str, tuple[int, int, int]]: ...
    def bulk_create(
        self, responden_id: str, data: OpmJawabanBulkCreate, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]: ...
    def delete_by_responden(self, responden_id: str) -> None: ...


class InMemoryOpmJawabanService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> OpmJawabanRead:
        return OpmJawabanRead.model_validate(rec)

    def list_by_responden(self, responden_id: str) -> list[OpmJawabanRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.task_kode,
            )
        return [self._to_read(r) for r in ordered]

    def get_raw_by_responden(self, responden_id: str) -> dict[str, tuple[int, int, int]]:
        with self._lock:
            return {
                r.task_kode: (r.importance, r.frequency, r.criticality)
                for r in self._data.values()
                if r.responden_id == responden_id
            }

    def bulk_create(
        self, responden_id: str, data: OpmJawabanBulkCreate, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]:
        _validate_task_set([j.task_kode for j in data.jawaban], valid_task_kodes)

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
                    id=f"opjw_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    task_kode=item.task_kode,
                    importance=item.importance,
                    frequency=item.frequency,
                    criticality=item.criticality,
                    catatan=item.catatan,
                )
                self._data[rec.id] = rec
                new_records.append(rec)
        return [self._to_read(r) for r in new_records]

    def delete_by_responden(self, responden_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
