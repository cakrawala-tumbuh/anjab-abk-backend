"""Integritas bank item WCP: hash bank, status terhadap paket R1.1, item kembar."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..core.bank_item import (
    PATH_PAKET_WCP,
    StatusPaket,
    hitung_hash,
    muat_paket,
    pasangan_kembar,
    status_terhadap_paket,
)


def hitung_item_bank_hash(items: Iterable[Any]) -> str:
    """Hitung hash bank item WCP aktif.

    Args:
        items: Objek bermember `item_id`, `dimensi_kode`, `pernyataan`, `reverse_type`,
            `urutan` (mis. `WcpItemRead` atau `WcpItemModel`).

    Returns:
        sha256 hex (64 karakter); lihat `core.bank_item.hitung_hash`.
    """
    return hitung_hash(
        {
            "item_id": i.item_id,
            "kelompok_kode": i.dimensi_kode,
            "pernyataan": i.pernyataan,
            "arah_atau_reverse": i.reverse_type,
            "urutan": i.urutan,
        }
        for i in items
    )


def status_dan_kembar(item_id: str, pernyataan: str) -> tuple[StatusPaket, str | None]:
    """Status paket + pasangan kembar (`"DCS:<item_id>"`) untuk satu item WCP.

    Args:
        item_id: Kode item WCP.
        pernyataan: Redaksi item aktif.

    Returns:
        Tuple `(status_paket, kembar_dengan)`; `kembar_dengan` None bila tak punya kembar.
    """
    status = status_terhadap_paket(item_id, pernyataan, muat_paket(PATH_PAKET_WCP))
    return status, pasangan_kembar()[0].get(item_id)


def ringkasan_bank(items: Iterable[Any]) -> dict[str, Any]:
    """Ringkasan bank untuk `WcpInstrumenRead`.

    Args:
        items: Item aktif (lihat `hitung_item_bank_hash`).

    Returns:
        Dict `item_bank_hash`, `jumlah_item`, `jumlah_redaksi_beda`, `jumlah_tidak_di_paket`.
    """
    daftar = list(items)
    statuses = [status_dan_kembar(i.item_id, i.pernyataan)[0] for i in daftar]
    return {
        "item_bank_hash": hitung_item_bank_hash(daftar),
        "jumlah_item": len(daftar),
        "jumlah_redaksi_beda": statuses.count("REDAKSI_BEDA"),
        "jumlah_tidak_di_paket": statuses.count("TIDAK_ADA_DI_PAKET"),
    }
