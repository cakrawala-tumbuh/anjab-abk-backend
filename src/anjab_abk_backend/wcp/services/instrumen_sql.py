"""Implementasi `WcpInstrumenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpInstrumenService` TANPA mengubah kontrak Protocol. Baris
singleton (`id='wcp'`) dijamin ada oleh migrasi — `get()` TIDAK auto-create bila
baris hilang, melainkan `raise AppError` (500).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ...errors import AppError, ValidationAppError
from ...models import WcpInstrumenModel
from ..schemas.instrumen import StatusInstrumenWcp, WcpInstrumenRead, WcpInstrumenUpdate

# Sumber tunggal id singleton & state machine.
from .instrumen import _ERR_MISSING_ROW, _VALID_TRANSITIONS, INSTRUMEN_ID


def _to_read(rec: WcpInstrumenModel) -> WcpInstrumenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    closed = rec.closed_at
    if closed is not None and closed.tzinfo is None:
        closed = closed.replace(tzinfo=UTC)
    return WcpInstrumenRead(
        id=rec.id,
        status=rec.status,  # type: ignore[arg-type]
        min_responden=rec.min_responden,
        catatan=rec.catatan,
        closed_at=closed,
        created_at=created,
    )


class SqlWcpInstrumenService:
    """`WcpInstrumenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self) -> WcpInstrumenModel:
        rec = self._s.get(WcpInstrumenModel, INSTRUMEN_ID)
        if rec is None:
            raise AppError(_ERR_MISSING_ROW)
        return rec

    def get(self) -> WcpInstrumenRead:
        return _to_read(self._get_model())

    def update(self, data: WcpInstrumenUpdate) -> WcpInstrumenRead:
        rec = self._get_model()
        changes = data.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        return _to_read(rec)

    def _transition(self, target: StatusInstrumenWcp) -> WcpInstrumenRead:
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

    def tutup(self) -> WcpInstrumenRead:
        return self._transition("CLOSED")

    def buka_ulang(self) -> WcpInstrumenRead:
        return self._transition("OPEN")

    def set_analyzed(self) -> WcpInstrumenRead:
        return self._transition("ANALYZED")
