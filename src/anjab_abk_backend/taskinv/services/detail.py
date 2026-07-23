"""SEAM akses data untuk detailing Tahap 2 (entri CalHR per task)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...errors import ValidationAppError
from ..schemas.detail import TiDetailRead, TiDetailUpsert


@dataclass
class _Record:
    id: str
    responden_id: str
    sesi_id: str
    task_kode: str
    sumber_bukti: str
    kondisi: str
    frekuensi_teks: str
    durasi_per_kali: int
    jam_per_minggu: float
    peak4w_hours: float
    va_type: str
    setuju_standar: bool = True
    catatan: str | None = None


class TiDetailService(Protocol):
    """Kontrak operasi terhadap detail Tahap 2."""

    def upsert(
        self, responden_id: str, sesi_id: str, data: TiDetailUpsert, valid_kodes: set[str]
    ) -> list[TiDetailRead]: ...
    def submit(self, responden_id: str) -> list[TiDetailRead]: ...
    def list_by_responden(
        self, responden_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[TiDetailRead], int]: ...
    def list_by_sesi(self, sesi_id: str) -> list[TiDetailRead]: ...
    def count_responden_submitted(self, sesi_id: str) -> int: ...
    def delete_by_responden(self, responden_id: str) -> None: ...


class InMemoryTiDetailService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TiDetailRead:
        return TiDetailRead.model_validate(rec)

    def upsert(
        self, responden_id: str, sesi_id: str, data: TiDetailUpsert, valid_kodes: set[str]
    ) -> list[TiDetailRead]:
        kodes = [item.task_kode for item in data.detail]
        unknown = set(kodes) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"task_kode di luar himpunan terpilih: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        with self._lock:
            results: list[_Record] = []
            for item in data.detail:
                existing = next(
                    (
                        r
                        for r in self._data.values()
                        if r.responden_id == responden_id and r.task_kode == item.task_kode
                    ),
                    None,
                )
                if existing is not None:
                    existing.sumber_bukti = item.sumber_bukti
                    existing.kondisi = item.kondisi
                    existing.frekuensi_teks = item.frekuensi_teks
                    existing.durasi_per_kali = item.durasi_per_kali
                    existing.jam_per_minggu = item.jam_per_minggu
                    existing.peak4w_hours = item.peak4w_hours
                    existing.va_type = item.va_type
                    existing.setuju_standar = item.setuju_standar
                    existing.catatan = item.catatan
                    results.append(existing)
                else:
                    rec = _Record(
                        id=f"tdet_{uuid.uuid4().hex[:8]}",
                        responden_id=responden_id,
                        sesi_id=sesi_id,
                        task_kode=item.task_kode,
                        sumber_bukti=item.sumber_bukti,
                        kondisi=item.kondisi,
                        frekuensi_teks=item.frekuensi_teks,
                        durasi_per_kali=item.durasi_per_kali,
                        jam_per_minggu=item.jam_per_minggu,
                        peak4w_hours=item.peak4w_hours,
                        va_type=item.va_type,
                        setuju_standar=item.setuju_standar,
                        catatan=item.catatan,
                    )
                    self._data[rec.id] = rec
                    results.append(rec)
        return [self._to_read(r) for r in results]

    def submit(self, responden_id: str) -> list[TiDetailRead]:
        rows, _ = self.list_by_responden(responden_id)
        if not rows:
            raise ValidationAppError(
                "Responden harus mengisi minimal 1 entri detail sebelum submit Tahap 3."
            )
        return rows

    def list_by_responden(
        self, responden_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[TiDetailRead], int]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.task_kode,
            )
        total = len(ordered)
        page = ordered[offset:] if limit is None else ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], total

    def list_by_sesi(self, sesi_id: str) -> list[TiDetailRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.sesi_id == sesi_id),
                key=lambda r: (r.task_kode, r.responden_id),
            )
        return [self._to_read(r) for r in ordered]

    def count_responden_submitted(self, sesi_id: str) -> int:
        with self._lock:
            return len({r.responden_id for r in self._data.values() if r.sesi_id == sesi_id})

    def delete_by_responden(self, responden_id: str) -> None:
        with self._lock:
            to_delete = [rid for rid, r in self._data.items() if r.responden_id == responden_id]
            for rid in to_delete:
                del self._data[rid]
