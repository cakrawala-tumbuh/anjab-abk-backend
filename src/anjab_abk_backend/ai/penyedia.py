"""Pilihan penyedia model AI: mode, model, effort, dan validasinya.

Hanya konstanta dan aturan murni; penyimpanan ada di `services/ai_penyedia_sql.py`.
"""

from __future__ import annotations

import re
from enum import StrEnum

from ..errors import ValidationAppError

__all__ = [
    "AI_EFFORT_BAWAAN",
    "AI_MODEL_BAWAAN",
    "AiEffort",
    "AiPenyediaMode",
    "ModelDitolak",
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

    error_code = "model_ditolak"


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
