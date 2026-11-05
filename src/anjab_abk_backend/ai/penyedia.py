"""Pilihan penyedia model AI: mode, model, effort, dan validasinya.

Hanya konstanta dan aturan murni; penyimpanan ada di `services/ai_penyedia_sql.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ValidationAppError
from .klien import AnthropicKlienModel, KlienModel

if TYPE_CHECKING:
    from ..schemas.ai_penyedia import AiPenyediaStatusRead

__all__ = [
    "AI_EFFORT_BAWAAN",
    "AI_MODEL_BAWAAN",
    "AiEffort",
    "AiPenyediaMode",
    "KlienTerpilih",
    "ModelDitolak",
    "PenyediaMati",
    "PenyediaTidakTersedia",
    "buat_klien_model",
    "validasi_effort",
    "validasi_model",
]

AI_MODEL_BAWAAN = "claude-opus-5-5"
"""Model bila kolom `model` kosong (keputusan K-4)."""

AI_EFFORT_BAWAAN = "high"
"""Effort bila kolom `effort` kosong."""

_POLA_MODEL = re.compile(r"^claude-[a-z0-9-]{1,90}$")
_AWALAN_DITOLAK = ("claude-fable", "claude-mythos")


class AiPenyediaMode(StrEnum):
    """Penyedia model AI yang dipilih admin. Memilih tidak menyalakan AI."""

    MATI = "MATI"
    API_ANTHROPIC = "API_ANTHROPIC"
    LANGGANAN_CLAUDE = "LANGGANAN_CLAUDE"


class AiEffort(StrEnum):
    """Kedalaman berpikir yang diizinkan."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ModelDitolak(ValidationAppError):
    """422: nama model tidak sah atau mewajibkan retensi (dikecualikan K-4)."""

    error_code = "MODEL_DITOLAK"


def validasi_model(model: str) -> str:
    """Pastikan nama model sah dan bukan model yang mewajibkan retensi.

    Args:
        model: Nama model, mis. ``claude-opus-5-5``.

    Returns:
        Nama yang sama bila sah.

    Raises:
        ModelDitolak: Bentuk tidak cocok ``^claude-[a-z0-9-]{1,90}$`` atau berawalan
            ``claude-fable``/``claude-mythos``.
    """
    if not _POLA_MODEL.fullmatch(model):
        raise ModelDitolak("Nama model tidak sah.")
    if model.startswith(_AWALAN_DITOLAK):
        raise ModelDitolak("Model ini mewajibkan retensi data dan tidak diizinkan.")
    return model


def validasi_effort(effort: str) -> str:
    """Pastikan ``effort`` salah satu nilai `AiEffort`.

    Raises:
        ValidationAppError: Nilai di luar ``low|medium|high|xhigh|max``.
    """
    if effort not in {e.value for e in AiEffort}:
        raise ValidationAppError("Effort harus salah satu dari low, medium, high, xhigh, max.")
    return effort


class PenyediaMati(Exception):
    """Mode penyedia ``MATI``: tidak ada model yang boleh dipanggil."""


class PenyediaTidakTersedia(Exception):
    """Mode penyedia dipilih tetapi belum punya driver (``LANGGANAN_CLAUDE`` sampai #112)."""


@dataclass(frozen=True)
class KlienTerpilih:
    """Hasil pabrik: klien siap pakai beserta nilai yang dipakai membuatnya.

    ``repr`` aman: klien (``AnthropicKlienModel``) tidak memuat kunci di ``repr``-nya.

    Attributes:
        klien: Klien model yang siap memanggil.
        mode: Mode penyedia saat klien dibuat.
        model: Model yang diminta.
        effort: Kedalaman berpikir.
    """

    klien: KlienModel
    mode: AiPenyediaMode
    model: str
    effort: str


def buat_klien_model(
    session: Session,
    settings: Settings,
    *,
    status: AiPenyediaStatusRead | None = None,
) -> KlienTerpilih:
    """Bangun klien model dari pengaturan penyedia di basis data, tanpa cache.

    Dibaca ulang tiap pemanggilan sehingga perubahan admin berlaku pada job berikutnya
    tanpa restart. Satu-satunya pemanggil ``baca_kunci_api``; kunci tidak disimpan di
    luar objek klien dan tidak dicatat.

    Args:
        session: Sesi basis data (dipakai hanya untuk membaca; pemanggil menutupnya
            sebelum model dipanggil).
        settings: Pengaturan aplikasi.
        status: Status penyedia yang sudah dibaca pemanggil (opsional, menghindari
            pembacaan ganda).

    Returns:
        ``KlienTerpilih`` untuk mode ``API_ANTHROPIC``.

    Raises:
        PenyediaMati: Mode ``MATI``.
        PenyediaTidakTersedia: Mode ``LANGGANAN_CLAUDE`` (driver di #112).
        KunciModelTidakAda: Kunci kosong, tak terbaca, atau gagal didekripsi.
    """
    from ..services.ai_penyedia_sql import SqlAiPenyediaService

    svc = SqlAiPenyediaService(session, settings)
    st = status or svc.status()
    if st.mode is AiPenyediaMode.MATI:
        raise PenyediaMati
    if st.mode is AiPenyediaMode.LANGGANAN_CLAUDE:
        raise PenyediaTidakTersedia
    klien = AnthropicKlienModel(
        settings, kunci_api=svc.baca_kunci_api(), model=st.model, effort=st.effort.value
    )
    return KlienTerpilih(klien=klien, mode=st.mode, model=st.model, effort=st.effort.value)
