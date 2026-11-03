"""Implementasi `DcsInstrumenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryDcsInstrumenService` TANPA mengubah kontrak Protocol. Baris
singleton (`id='dcs'`) dijamin ada oleh migrasi — `get()` TIDAK auto-create bila
baris hilang, melainkan `raise AppError` (500).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ...errors import AppError, ValidationAppError
from ...instrumen_guard import guard_tanpa_jawaban
from ...models import DcsInstrumenModel, DcsJawabanModel, DcsRespondenModel
from ..schemas.instrumen import DcsInstrumenRead, DcsInstrumenUpdate, StatusInstrumenDcs

# Sumber tunggal id singleton & state machine.
from .instrumen import _ERR_MISSING_ROW, _VALID_TRANSITIONS, INSTRUMEN_ID


def _to_read(rec: DcsInstrumenModel) -> DcsInstrumenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    closed = rec.closed_at
    if closed is not None and closed.tzinfo is None:
        closed = closed.replace(tzinfo=UTC)
    return DcsInstrumenRead(
        id=rec.id,
        status=rec.status,  # type: ignore[arg-type]
        min_responden=rec.min_responden,
        catatan=rec.catatan,
        closed_at=closed,
        created_at=created,
    )


class SqlDcsInstrumenService:
    """`DcsInstrumenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self) -> DcsInstrumenModel:
        rec = self._s.get(DcsInstrumenModel, INSTRUMEN_ID)
        if rec is None:
            raise AppError(_ERR_MISSING_ROW)
        return rec

    def get(self) -> DcsInstrumenRead:
        return _to_read(self._get_model())

    def update(self, data: DcsInstrumenUpdate) -> DcsInstrumenRead:
        rec = self._get_model()
        changes = data.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        return _to_read(rec)

    def _transition(self, target: StatusInstrumenDcs) -> DcsInstrumenRead:
        rec = self._get_model()
        allowed = _VALID_TRANSITIONS.get(rec.status, set())  # type: ignore[arg-type]
        if target not in allowed:
            raise ValidationAppError(
                f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                f" Transisi yang diizinkan dari '{rec.status}': {sorted(allowed) or '(tidak ada)'}."
            )
        rec.status = target
        if target == "CLOSED":
            rec.closed_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def tutup(self) -> DcsInstrumenRead:
        return self._transition("CLOSED")

    def buka_ulang(self) -> DcsInstrumenRead:
        """Buka kembali instrumen `CLOSED` atau `ANALYZED` ke `OPEN` (non-destruktif).

        Responden, jawaban, dan status submit tetap utuh; hasil analisis dihitung
        ulang saat `analisis` berikutnya dijalankan.
        """
        return self._transition("OPEN")

    def set_analyzed(self) -> DcsInstrumenRead:
        return self._transition("ANALYZED")

    def reset(self) -> DcsInstrumenRead:
        """Hapus SEMUA responden DCS (jawaban ikut lewat `ON DELETE CASCADE`) dan
        kembalikan instrumen ke `OPEN`, `closed_at=NULL` — dalam satu transaksi.

        DITOLAK (409 `instrument_has_responses`) bila instrumen sudah berisi >= 1
        jawaban (draft maupun submit) — jalan keluar dari `ANALYZED` kini
        `buka_ulang()` yang non-destruktif. Hanya instrumen tanpa jawaban yang
        bisa di-reset.

        Melewati `_VALID_TRANSITIONS`: `reset()` sah dipanggil dari status APA PUN
        selama instrumen belum berisi jawaban (idempoten). Bulk-delete lewat
        `Query.delete()` meniru pola `purge_catalog()`
        (`taskinv/services/catalog_admin.py`) — operasi admin bulk lintas-baris
        dalam satu domain, bukan lewat `RespondenService` per-baris (yang menolak
        baris `sudah_submit`).
        """
        rec = self._get_model()
        guard_tanpa_jawaban(self._s, DcsJawabanModel, "reset")
        self._s.query(DcsRespondenModel).delete()
        rec.status = "OPEN"
        rec.closed_at = None
        self._s.flush()
        return _to_read(rec)
