"""Guard bersama: tolak operasi destruktif pada instrumen yang sudah berisi jawaban."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from .errors import InstrumenBerisiJawabanError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def guard_tanpa_jawaban(session: Session, jawaban_model: type, aksi: str) -> None:
    """Tolak `aksi` (409) bila tabel jawaban instrumen punya >= 1 baris (draft maupun submit).

    Args:
        session: Session SQLAlchemy yang sama dengan operasi yang dijaga, sehingga
            pengecekan berada dalam transaksi yang sama dengan penghapusan/perubahan.
        jawaban_model: Kelas ORM jawaban (`WcpJawabanModel`/`DcsJawabanModel`), wajib
            punya kolom `responden_id`.
        aksi: Frasa pendek aksi yang ditolak, dipakai di pesan (mis. "reset").

    Raises:
        InstrumenBerisiJawabanError: Bila ada jawaban; pesan menyebut jumlah responden
            berjawaban.
    """
    n = session.scalar(select(func.count(func.distinct(jawaban_model.responden_id)))) or 0  # type: ignore[attr-defined]
    if n > 0:
        raise InstrumenBerisiJawabanError(
            f"Instrumen sudah berisi jawaban dari {n} responden; {aksi} ditolak."
        )
