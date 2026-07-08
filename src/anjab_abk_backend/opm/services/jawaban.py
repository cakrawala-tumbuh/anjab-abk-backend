"""SEAM akses data untuk resource `OpmJawaban`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...errors import ValidationAppError
from ..schemas.jawaban import OpmJawabanRead, OpmJawabanUpsert


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


def _validate_task_subset(kodes_list: list[str], valid_task_kodes: set[str]) -> None:
    """Set task_kode yang di-upsert (draft, boleh parsial) harus subset dari snapshot sesi."""
    unknown = set(kodes_list) - valid_task_kodes
    if unknown:
        raise ValidationAppError(f"Kode task tidak dikenal: {', '.join(sorted(unknown))}.")


class OpmJawabanService(Protocol):
    """Kontrak operasi terhadap OpmJawaban."""

    def list_by_responden(self, responden_id: str) -> list[OpmJawabanRead]: ...
    def get_raw_by_responden(self, responden_id: str) -> dict[str, tuple[int, int, int]]: ...
    def upsert(
        self, responden_id: str, data: OpmJawabanUpsert, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]: ...
    def submit(self, responden_id: str, valid_task_kodes: set[str]) -> list[OpmJawabanRead]: ...
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

    def upsert(
        self, responden_id: str, data: OpmJawabanUpsert, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]:
        _validate_task_subset([j.task_kode for j in data.jawaban], valid_task_kodes)

        with self._lock:
            results: list[_Record] = []
            for item in data.jawaban:
                existing = next(
                    (
                        r
                        for r in self._data.values()
                        if r.responden_id == responden_id and r.task_kode == item.task_kode
                    ),
                    None,
                )
                if existing is not None:
                    existing.importance = item.importance
                    existing.frequency = item.frequency
                    existing.criticality = item.criticality
                    existing.catatan = item.catatan
                    results.append(existing)
                else:
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
                    results.append(rec)
        return [self._to_read(r) for r in results]

    def submit(self, responden_id: str, valid_task_kodes: set[str]) -> list[OpmJawabanRead]:
        with self._lock:
            rows = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.task_kode,
            )
        _validate_task_set([r.task_kode for r in rows], valid_task_kodes)
        return [self._to_read(r) for r in rows]

    def delete_by_responden(self, responden_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
