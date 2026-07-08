"""SEAM akses data untuk seleksi relevansi Tahap 1.

Disimpan per pasangan (responden, task_kode) agar mudah menghitung union antar responden
dan jumlah relevansi per task.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ValidationAppError
from ..schemas.seleksi import TiSeleksiRead


@dataclass
class _Record:
    id: str
    responden_id: str
    sesi_id: str
    task_kode: str
    created_at: datetime


class TiSeleksiService(Protocol):
    """Kontrak operasi terhadap seleksi Tahap 1."""

    def save_draft(
        self, responden_id: str, sesi_id: str, kodes: list[str], valid_kodes: set[str]
    ) -> TiSeleksiRead: ...
    def submit(self, responden_id: str) -> TiSeleksiRead: ...
    def get_by_responden(self, responden_id: str) -> TiSeleksiRead | None: ...
    def union_terpilih(self, sesi_id: str) -> list[str]: ...
    def unanimous_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]: ...
    def partial_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]: ...
    def count_relevan_per_task(self, sesi_id: str) -> dict[str, int]: ...
    def delete_by_responden(self, responden_id: str) -> None: ...


class InMemoryTiSeleksiService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    def save_draft(
        self, responden_id: str, sesi_id: str, kodes: list[str], valid_kodes: set[str]
    ) -> TiSeleksiRead:
        unik = sorted(set(kodes))
        unknown = set(unik) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"Kode task tidak valid untuk kombinasi sesi: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
            now = datetime.now(UTC)
            for kode in unik:
                rec = _Record(
                    id=f"tsel_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    sesi_id=sesi_id,
                    task_kode=kode,
                    created_at=now,
                )
                self._data[rec.id] = rec
        return TiSeleksiRead(
            responden_id=responden_id, sesi_id=sesi_id, task_kode=unik, submitted_at=now
        )

    def submit(self, responden_id: str) -> TiSeleksiRead:
        result = self.get_by_responden(responden_id)
        if result is None or not result.task_kode:
            raise ValidationAppError(
                "Responden harus memilih minimal 1 task sebelum submit Tahap 1."
            )
        return result

    def get_by_responden(self, responden_id: str) -> TiSeleksiRead | None:
        with self._lock:
            recs = [r for r in self._data.values() if r.responden_id == responden_id]
        if not recs:
            return None
        return TiSeleksiRead(
            responden_id=responden_id,
            sesi_id=recs[0].sesi_id,
            task_kode=sorted(r.task_kode for r in recs),
            submitted_at=min(r.created_at for r in recs),
        )

    def union_terpilih(self, sesi_id: str) -> list[str]:
        with self._lock:
            return sorted({r.task_kode for r in self._data.values() if r.sesi_id == sesi_id})

    def unanimous_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]:
        """Task yang dipilih oleh SEMUA responden yang sudah submit Tahap 1."""
        counts = self.count_relevan_per_task(sesi_id)
        if total_submitted == 0:
            return []
        return sorted(kode for kode, n in counts.items() if n >= total_submitted)

    def partial_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]:
        """Task yang dipilih oleh SEBAGIAN (bukan semua) responden — butuh review koordinator."""
        counts = self.count_relevan_per_task(sesi_id)
        if total_submitted == 0:
            return []
        return sorted(kode for kode, n in counts.items() if 0 < n < total_submitted)

    def count_relevan_per_task(self, sesi_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._lock:
            for r in self._data.values():
                if r.sesi_id == sesi_id:
                    counts[r.task_kode] = counts.get(r.task_kode, 0) + 1
        return counts

    def delete_by_responden(self, responden_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
