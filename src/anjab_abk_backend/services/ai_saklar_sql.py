"""Implementasi PostgreSQL `SaklarAiService`."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ConflictError
from ..fitur import fitur_aktif
from ..models import AiSaklarEventModel
from ..schemas.ai_saklar import AiSaklarAksi, SaklarAiRead
from ..schemas.common import FiturKode

__all__ = ["SqlSaklarAiService", "event_terakhir"]


def event_terakhir(session: Session, layanan: FiturKode) -> AiSaklarEventModel | None:
    """Ambil event saklar terakhir ``layanan`` atau ``None`` bila belum ada."""
    return session.scalars(
        select(AiSaklarEventModel)
        .where(AiSaklarEventModel.layanan == layanan.value)
        .order_by(AiSaklarEventModel.created_at.desc())
        .limit(1)
    ).first()


class SqlSaklarAiService:
    """`SaklarAiService` di atas satu `Session` per request."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._s = session
        self._settings = settings

    def status(self, layanan: FiturKode) -> SaklarAiRead:
        """Hitung status dari event terakhir dan flag env."""
        ev = event_terakhir(self._s, layanan)
        flag = fitur_aktif(layanan, self._settings)
        dimatikan = ev is not None and ev.aksi == AiSaklarAksi.MATIKAN.value
        return SaklarAiRead(
            layanan=layanan,
            flag_aktif=flag,
            dimatikan=dimatikan,
            boleh_jalan=flag and not dimatikan,
            alasan=ev.alasan if ev else None,
            aktor=ev.aktor if ev else None,
            pada=ev.created_at if ev else None,
        )

    def _catat(
        self, layanan: FiturKode, aksi: AiSaklarAksi, alasan: str, aktor: str
    ) -> SaklarAiRead:
        """Tolak aksi berulang (409), selain itu tambah satu event baru."""
        sekarang_mati = self.status(layanan).dimatikan
        if (aksi is AiSaklarAksi.MATIKAN) == sekarang_mati:
            kata = "dimatikan" if sekarang_mati else "tidak dimatikan"
            raise ConflictError(f"Layanan {layanan.value} sudah {kata}.")
        self._s.add(
            AiSaklarEventModel(
                id=str(uuid.uuid4()),
                layanan=layanan.value,
                aksi=aksi.value,
                alasan=alasan,
                aktor=aktor,
            )
        )
        self._s.flush()
        return self.status(layanan)

    def matikan(self, layanan: FiturKode, alasan: str, aktor: str) -> SaklarAiRead:
        """Catat MATIKAN; 409 bila sudah dimatikan."""
        return self._catat(layanan, AiSaklarAksi.MATIKAN, alasan, aktor)

    def hidupkan(self, layanan: FiturKode, alasan: str, aktor: str) -> SaklarAiRead:
        """Catat HIDUPKAN; 409 bila tidak sedang dimatikan. Tidak menyentuh flag env."""
        return self._catat(layanan, AiSaklarAksi.HIDUPKAN, alasan, aktor)
