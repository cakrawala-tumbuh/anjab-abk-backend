"""Implementasi PostgreSQL pengaturan penyedia model AI (satu baris + event append-only)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from ..ai.kredensial import (
    KredensialTakTerbaca,
    KunciIndukTidakAda,
    dekripsi_kredensial,
    enkripsi_kredensial,
    fernet_dari,
)
from ..ai.penyedia import (
    AI_EFFORT_BAWAAN,
    AI_MODEL_BAWAAN,
    AiPenyediaMode,
    validasi_effort,
    validasi_model,
)
from ..config import Settings
from ..errors import ConflictError, ValidationAppError
from ..logging import AUDIT_LOGGER_NAME
from ..models import AiPenyediaEventModel, AiPenyediaPengaturanModel
from ..schemas.ai_penyedia import AiPenyediaAksi, AiPenyediaStatusRead

__all__ = ["ID_TUNGGAL", "SqlAiPenyediaService"]

ID_TUNGGAL = "TUNGGAL"
_audit = logging.getLogger(AUDIT_LOGGER_NAME)
_MIN_KUNCI = 8


class SqlAiPenyediaService:
    """Baca dan ubah pilihan penyedia AI di atas satu `Session` per request.

    Kredensial hanya keluar sebagai teks asli lewat `baca_kunci_api`; status, event, log,
    dan `repr` tidak pernah memuatnya.
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self._s = session
        self._settings = settings

    def _baris(self) -> AiPenyediaPengaturanModel | None:
        return self._s.get(AiPenyediaPengaturanModel, ID_TUNGGAL)

    def _baris_atau_baru(self, aktor: str) -> AiPenyediaPengaturanModel:
        rec = self._baris()
        if rec is None:
            rec = AiPenyediaPengaturanModel(
                id=ID_TUNGGAL, mode=AiPenyediaMode.MATI.value, diperbarui_oleh=aktor
            )
            self._s.add(rec)
            self._s.flush()
        return rec

    def _enkripsi_siap(self) -> bool:
        try:
            fernet_dari(self._settings.ai_kredensial_kunci_induk)
        except KunciIndukTidakAda:
            return False
        return True

    def status(self) -> AiPenyediaStatusRead:
        """Status berlaku; tanpa baris dibaca ``MATI`` dengan model dan effort bawaan."""
        rec = self._baris()
        terpasang = rec is not None and rec.kredensial_terenkripsi is not None
        terbaca = False
        if terpasang:
            try:
                dekripsi_kredensial(
                    self._settings.ai_kredensial_kunci_induk, rec.kredensial_terenkripsi
                )
                terbaca = True
            except (KredensialTakTerbaca, KunciIndukTidakAda):
                terbaca = False
        return AiPenyediaStatusRead(
            mode=AiPenyediaMode(rec.mode) if rec else AiPenyediaMode.MATI,
            model=(rec.model if rec and rec.model else AI_MODEL_BAWAAN),
            effort=(rec.effort if rec and rec.effort else AI_EFFORT_BAWAAN),
            kredensial_terpasang=terpasang,
            kredensial_akhiran=rec.kredensial_akhiran if rec else None,
            kredensial_terbaca=terbaca,
            enkripsi_siap=self._enkripsi_siap(),
            diperbarui_oleh=rec.diperbarui_oleh if rec else None,
            pada=rec.updated_at if rec else None,
        )

    def _event(
        self,
        aksi: AiPenyediaAksi,
        alasan: str,
        aktor: str,
        *,
        mode: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        akhiran: str | None = None,
    ) -> None:
        self._s.add(
            AiPenyediaEventModel(
                id=str(uuid.uuid4()),
                aksi=aksi.value,
                mode=mode,
                model=model,
                effort=effort,
                kredensial_akhiran=akhiran,
                alasan=alasan,
                aktor=aktor,
            )
        )
        self._s.flush()
        _audit.disabled = False  # alembic fileConfig dapat mematikan logger yang sudah ada
        _audit.info("ai_penyedia", extra={"actor": aktor, "resource": aksi.value})

    def ubah_mode(self, mode: AiPenyediaMode, alasan: str, aktor: str) -> AiPenyediaStatusRead:
        """Pilih penyedia. 409 bila sama dengan yang berlaku. Tidak menyalakan AI."""
        if self.status().mode is mode:
            raise ConflictError(f"Mode penyedia sudah {mode.value}.")
        rec = self._baris_atau_baru(aktor)
        rec.mode = mode.value
        rec.diperbarui_oleh = aktor
        self._event(AiPenyediaAksi.UBAH_MODE, alasan, aktor, mode=mode.value)
        return self.status()

    def ubah_model(
        self, model: str | None, effort: str | None, alasan: str, aktor: str
    ) -> AiPenyediaStatusRead:
        """Ubah model dan effort; ``None`` mengembalikan ke bawaan.

        Raises:
            ModelDitolak: Nama model tidak sah atau mewajibkan retensi.
            ValidationAppError: Effort di luar daftar.
            ConflictError: Tidak ada perubahan efektif.
        """
        if model is not None:
            validasi_model(model)
        if effort is not None:
            validasi_effort(effort)
        sekarang = self.status()
        if (model or AI_MODEL_BAWAAN) == sekarang.model and (
            effort or AI_EFFORT_BAWAAN
        ) == sekarang.effort.value:
            raise ConflictError("Model dan effort sudah demikian.")
        rec = self._baris_atau_baru(aktor)
        rec.model = model
        rec.effort = effort
        rec.diperbarui_oleh = aktor
        self._event(AiPenyediaAksi.UBAH_MODEL, alasan, aktor, model=model, effort=effort)
        return self.status()

    def pasang_kredensial(self, kunci: str, alasan: str, aktor: str) -> AiPenyediaStatusRead:
        """Simpan kunci API terenkripsi; menggantikan yang lama.

        Raises:
            KunciIndukTidakAda: Kunci induk deployment kosong/tidak sah; tidak ada yang berubah.
            ValidationAppError: Kunci kosong atau terlalu pendek.
        """
        nilai = kunci.strip()
        if len(nilai) < _MIN_KUNCI:
            raise ValidationAppError("Kunci API terlalu pendek.")
        cipher = enkripsi_kredensial(self._settings.ai_kredensial_kunci_induk, nilai)
        akhiran = nilai[-4:]
        rec = self._baris_atau_baru(aktor)
        rec.kredensial_terenkripsi = cipher
        rec.kredensial_akhiran = akhiran
        rec.diperbarui_oleh = aktor
        self._event(AiPenyediaAksi.PASANG_KREDENSIAL, alasan, aktor, akhiran=akhiran)
        return self.status()

    def hapus_kredensial(self, alasan: str, aktor: str) -> AiPenyediaStatusRead:
        """Hapus kunci API tersimpan. 409 bila tidak ada."""
        rec = self._baris()
        if rec is None or rec.kredensial_terenkripsi is None:
            raise ConflictError("Tidak ada kredensial tersimpan.")
        akhiran = rec.kredensial_akhiran
        rec.kredensial_terenkripsi = None
        rec.kredensial_akhiran = None
        rec.diperbarui_oleh = aktor
        self._event(AiPenyediaAksi.HAPUS_KREDENSIAL, alasan, aktor, akhiran=akhiran)
        return self.status()

    def baca_kunci_api(self) -> str | None:
        """Kunci API teks asli, atau ``None`` bila tidak terpasang atau tak terbaca.

        Satu-satunya jalan keluar teks asli; hanya pabrik klien (#111) yang boleh memanggil.
        """
        rec = self._baris()
        if rec is None or rec.kredensial_terenkripsi is None:
            return None
        try:
            return dekripsi_kredensial(
                self._settings.ai_kredensial_kunci_induk, rec.kredensial_terenkripsi
            )
        except (KredensialTakTerbaca, KunciIndukTidakAda):
            return None
