"""Implementasi PostgreSQL `SkemaDbService` (hanya baca)."""

from __future__ import annotations

import logging
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..errors import ServiceUnavailableError
from ..migrate import current_heads
from ..models import Base
from ..schemas.skema_db import SkemaDbRead

logger = logging.getLogger(__name__)


def _nama_objek(op: str, args: tuple[Any, ...]) -> str:
    """Turunkan nama objek ringkas (tanpa data) dari satu entri diff Alembic."""
    if op in ("add_table", "remove_table"):
        return str(args[0].name)
    if op in ("add_column", "remove_column"):
        return f"{args[1]}.{args[2].name}"
    if op.startswith("modify_"):
        return f"{args[1]}.{args[2]}"
    obj = args[0]
    nama = getattr(obj, "name", None)
    tabel = getattr(getattr(obj, "table", None), "name", None)
    if nama:
        return str(nama)
    return str(tabel or obj)


def _ratakan(diff: list[Any]) -> list[str]:
    """Ratakan diff Alembic (boleh bersarang) jadi daftar '<operasi>:<nama objek>'."""
    hasil: list[str] = []
    for entri in diff:
        if isinstance(entri, list):
            hasil.extend(_ratakan(entri))
        else:
            hasil.append(f"{entri[0]}:{_nama_objek(entri[0], entri[1:])}")
    return hasil


def _hitung_selisih(connection: Connection) -> list[str]:
    """Bandingkan skema aktual dengan `Base.metadata` (``compare_type=True``)."""
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return _ratakan(compare_metadata(context, Base.metadata))


class SqlSkemaDbService:
    """`SkemaDbService` di atas satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def baca(self) -> SkemaDbRead:
        """Baca revisi aktif, head kode, dan selisih skema terhadap model ORM."""
        try:
            conn = self._s.connection()
            ada = inspect(conn).has_table("alembic_version")
            baris = conn.execute(text("SELECT version_num FROM alembic_version")) if ada else []
            revisi = sorted(str(r[0]) for r in baris)
        except OperationalError as exc:
            raise ServiceUnavailableError("Basis data tidak dapat dijangkau.") from exc
        head = sorted(current_heads())
        try:
            with self._s.begin_nested():
                selisih = _hitung_selisih(self._s.connection())
            terbaca = True
        except Exception:
            logger.warning("skema_db_banding_gagal", exc_info=True)
            selisih, terbaca = [], False
        return SkemaDbRead(
            revisi_db=revisi,
            head_kode=head,
            selaras=bool(revisi) and bool(head) and set(revisi) == set(head),
            selisih_model=selisih,
            selisih_terbaca=terbaca,
        )
