"""SEAM akses data untuk review koordinator Tahap 2 Task Inventory.

Koordinator SME panel menentukan relevansi task-task yang tidak dipilih oleh
semua anggota panel di Tahap 1 (partial selection). Task yang dipilih oleh
semua anggota otomatis masuk; yang partial butuh keputusan koordinator.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ValidationAppError
from ..schemas.tahap2 import TiTahap2KeputusanItem, TiTahap2ReviewRead, TiTahap2TaskRead


@dataclass
class _Keputusan:
    id: str
    sesi_id: str
    task_kode: str
    disetujui: bool
    submitted_at: datetime


class TiTahap2Service(Protocol):
    """Kontrak operasi terhadap review koordinator Tahap 2."""

    def get_review(
        self, sesi_id: str, partial_kodes: list[str], counts: dict[str, int], n_total: int
    ) -> TiTahap2ReviewRead: ...
    def submit_keputusan(
        self, sesi_id: str, keputusan: list[TiTahap2KeputusanItem], valid_kodes: set[str]
    ) -> TiTahap2ReviewRead: ...
    def get_approved_kodes(self, sesi_id: str) -> list[str]: ...
    def delete_by_sesi(self, sesi_id: str) -> None: ...


class InMemoryTiTahap2Service:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Keputusan] = {}

    def get_review(
        self, sesi_id: str, partial_kodes: list[str], counts: dict[str, int], n_total: int
    ) -> TiTahap2ReviewRead:
        with self._lock:
            existing: dict[str, _Keputusan] = {
                r.task_kode: r for r in self._data.values() if r.sesi_id == sesi_id
            }
        tasks: list[TiTahap2TaskRead] = []
        last_at: datetime | None = None
        for kode in partial_kodes:
            kep = existing.get(kode)
            disetujui = kep.disetujui if kep else None
            if kep and (last_at is None or kep.submitted_at > last_at):
                last_at = kep.submitted_at
            tasks.append(
                TiTahap2TaskRead(
                    task_kode=kode,
                    n_relevan=counts.get(kode, 0),
                    n_total=n_total,
                    disetujui=disetujui,
                )
            )
        belum = sum(1 for t in tasks if t.disetujui is None)
        return TiTahap2ReviewRead(
            sesi_id=sesi_id,
            tasks=tasks,
            jumlah_belum_diputuskan=belum,
            submitted_at=last_at,
        )

    def submit_keputusan(
        self, sesi_id: str, keputusan: list[TiTahap2KeputusanItem], valid_kodes: set[str]
    ) -> TiTahap2ReviewRead:
        unknown = {k.task_kode for k in keputusan} - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"Kode task tidak valid untuk sesi ini: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        now = datetime.now(UTC)
        submitted_kodes = {k.task_kode for k in keputusan}
        with self._lock:
            for item in keputusan:
                existing = next(
                    (
                        r
                        for r in self._data.values()
                        if r.sesi_id == sesi_id and r.task_kode == item.task_kode
                    ),
                    None,
                )
                if existing:
                    existing.disetujui = item.disetujui
                    existing.submitted_at = now
                else:
                    rec = _Keputusan(
                        id=f"tt2k_{uuid.uuid4().hex[:8]}",
                        sesi_id=sesi_id,
                        task_kode=item.task_kode,
                        disetujui=item.disetujui,
                        submitted_at=now,
                    )
                    self._data[rec.id] = rec
        with self._lock:
            existing_map: dict[str, _Keputusan] = {
                r.task_kode: r
                for r in self._data.values()
                if r.sesi_id == sesi_id and r.task_kode in submitted_kodes
            }
        tasks: list[TiTahap2TaskRead] = []
        for kode in sorted(submitted_kodes):
            kep = existing_map.get(kode)
            tasks.append(
                TiTahap2TaskRead(
                    task_kode=kode,
                    n_relevan=0,
                    n_total=0,
                    disetujui=kep.disetujui if kep else None,
                )
            )
        belum = sum(1 for t in tasks if t.disetujui is None)
        return TiTahap2ReviewRead(
            sesi_id=sesi_id,
            tasks=tasks,
            jumlah_belum_diputuskan=belum,
            submitted_at=now,
        )

    def get_approved_kodes(self, sesi_id: str) -> list[str]:
        """Kode task yang disetujui koordinator (untuk digabung dengan unanimous)."""
        with self._lock:
            return sorted(
                r.task_kode for r in self._data.values() if r.sesi_id == sesi_id and r.disetujui
            )

    def delete_by_sesi(self, sesi_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.sesi_id == sesi_id]
            for rid in to_delete:
                del self._data[rid]
