"""SEAM akses data untuk detailing Tahap 2 (entri CalHR per task)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ..schemas.detail import TiDetailRead, TiDetailSubmit


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
    ai_mode: str
    va_type: str
    dcs_flag: bool
    catatan: str | None = None


class TiDetailService(Protocol):
    """Kontrak operasi terhadap detail Tahap 2."""

    def submit(
        self, responden_id: str, sesi_id: str, data: TiDetailSubmit, valid_kodes: set[str]
    ) -> list[TiDetailRead]: ...
    def list_by_responden(self, responden_id: str) -> list[TiDetailRead]: ...
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

    def submit(
        self, responden_id: str, sesi_id: str, data: TiDetailSubmit, valid_kodes: set[str]
    ) -> list[TiDetailRead]:
        kodes = [item.task_kode for item in data.detail]
        if len(kodes) != len(set(kodes)):
            raise ValidationAppError("Terdapat task_kode duplikat dalam payload detail.")
        unknown = set(kodes) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"task_kode di luar himpunan terpilih: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        with self._lock:
            if any(r.responden_id == responden_id for r in self._data.values()):
                raise ConflictError(f"Responden '{responden_id}' sudah submit detail Tahap 2.")
            new: list[_Record] = []
            for item in data.detail:
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
                    ai_mode=item.ai_mode,
                    va_type=item.va_type,
                    dcs_flag=item.dcs_flag,
                    catatan=item.catatan,
                )
                self._data[rec.id] = rec
                new.append(rec)
        return [self._to_read(r) for r in new]

    def list_by_responden(self, responden_id: str) -> list[TiDetailRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.task_kode,
            )
        return [self._to_read(r) for r in ordered]

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
