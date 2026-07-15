"""Literal tipe komponen CalHR — dipakai bersama oleh detail Tahap 3 & nilai standar master."""

from __future__ import annotations

from typing import Literal

SumberBukti = Literal["Formal", "Aktual", "Keduanya"]
Kondisi = Literal["Baseline", "Peak", "Both"]
VaType = Literal["VA-Core", "VA-Enable", "NVA-Residual", "Context-Dependent", "Needs Validation"]
