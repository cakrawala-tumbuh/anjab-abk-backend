"""Literal tipe komponen CalHR — dipakai bersama oleh detail Tahap 3 & nilai standar master.

`VaType` memuat 4 nilai kanonik CF-3.0 (`VA-Core`, `VA-Enable`, `NVA-Residual`) ditambah
`Context-Dependent` yang diterima sebagai prefill katalog & draft Tahap 3, tetapi ditolak
sebagai jawaban final saat submit (lihat `taskinv/services/detail.py`/`detail_sql.py`).
Nilai `Needs Validation` (placeholder katalog yang belum tervalidasi) sudah dihapus total
dari kontrak — baris seed yang memakainya turut dibersihkan dari `data/task_catalog.json`.
"""

from __future__ import annotations

from typing import Literal

SumberBukti = Literal["Formal", "Aktual", "Keduanya"]
Kondisi = Literal["Baseline", "Peak", "Both"]
VaType = Literal["VA-Core", "VA-Enable", "NVA-Residual", "Context-Dependent"]
