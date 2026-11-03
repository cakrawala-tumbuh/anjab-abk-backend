"""Agregat deskriptif RAW per item untuk hasil WCP/DCS saat skoring dimatikan."""

from __future__ import annotations

import statistics
from collections.abc import Iterable

from ..schemas.common import HasilRawItemRead


def agregat_raw_per_item(
    responden_raw: list[tuple[str, dict[str, int]]],
    items: Iterable[tuple[str, str, int]],
) -> list[HasilRawItemRead]:
    """Hitung frekuensi dan statistik deskriptif raw tiap item.

    Args:
        responden_raw: Daftar ``(responden_id, {item_id: skor_raw})`` responden ber-submit.
        items: Iterable ``(item_id, kelompok_kode, urutan)`` katalog aktif.

    Returns:
        Daftar `HasilRawItemRead` terurut ``urutan``. Nilai jawaban dipakai apa adanya
        (tanpa reverse); jawaban yang tidak ada dihitung di ``n_kosong`` dan tidak pernah
        dianggap 0. ``mean_raw`` null bila ``n`` < 1, ``sd_raw`` null bila ``n`` < 2.
    """
    total = len(responden_raw)
    hasil: list[HasilRawItemRead] = []
    for item_id, kelompok, urutan in sorted(items, key=lambda x: x[2]):
        nilai = [raw[item_id] for _, raw in responden_raw if item_id in raw]
        frekuensi = {str(k): nilai.count(k) for k in range(1, 6)}
        hasil.append(
            HasilRawItemRead(
                item_id=item_id,
                kelompok_kode=kelompok,
                urutan=urutan,
                n=len(nilai),
                n_kosong=total - len(nilai),
                frekuensi=frekuensi,
                mean_raw=round(statistics.mean(nilai), 2) if nilai else None,
                sd_raw=round(statistics.stdev(nilai), 2) if len(nilai) > 1 else None,
            )
        )
    return hasil
