"""Integritas bank item instrumen (WCP/DCS): hash bank, status terhadap paket R1.1, item kembar.

Modul bersama untuk `wcp.bank_item` dan `dcs.bank_item`. Tidak pernah mengubah teks item:
semua fungsi di sini hanya MEMBACA item dan data referensi paket (CSV R1.1 yang disalin
apa adanya ke `wcp/data/wcp_item.csv` dan `dcs/data/dcs_item.csv`).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Literal

StatusPaket = Literal["SAMA", "REDAKSI_BEDA", "TIDAK_ADA_DI_PAKET"]

_ROOT = Path(__file__).resolve().parent.parent
PATH_PAKET_WCP = _ROOT / "wcp" / "data" / "wcp_item.csv"
PATH_PAKET_DCS = _ROOT / "dcs" / "data" / "dcs_item.csv"


def normalisasi_redaksi(teks: str) -> str:
    """Normalisasi redaksi untuk perbandingan: trim + rapatkan spasi berurutan.

    Tanda baca dan huruf besar/kecil sengaja TIDAK dinormalisasi (dianggap beda).

    Args:
        teks: Teks pernyataan mentah.

    Returns:
        Teks dengan spasi di tepi dibuang dan spasi/tab/newline berurutan jadi satu spasi.
    """
    return " ".join(teks.split())


@lru_cache(maxsize=8)
def muat_paket(path: Path) -> dict[str, str]:
    """Baca CSV paket R1.1 menjadi pemetaan `item_id` -> redaksi ternormalisasi.

    Args:
        path: Lokasi `wcp_item.csv` atau `dcs_item.csv`.

    Returns:
        Dict `{item_id: pernyataan_ternormalisasi}` (hasil di-cache per path).
    """
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["item_id"]: normalisasi_redaksi(r["pernyataan"]) for r in csv.DictReader(fh)}


def status_terhadap_paket(item_id: str, pernyataan: str, paket: dict[str, str]) -> StatusPaket:
    """Tentukan status sebuah item terhadap data referensi paket.

    Args:
        item_id: Kode item.
        pernyataan: Redaksi item aktif (belum dinormalisasi).
        paket: Hasil `muat_paket` untuk instrumen item ini.

    Returns:
        `TIDAK_ADA_DI_PAKET` bila kode tak ada di paket, `SAMA` bila redaksi ternormalisasi
        identik, selain itu `REDAKSI_BEDA`.
    """
    ref = paket.get(item_id)
    if ref is None:
        return "TIDAK_ADA_DI_PAKET"
    return "SAMA" if normalisasi_redaksi(pernyataan) == ref else "REDAKSI_BEDA"


@lru_cache(maxsize=1)
def pasangan_kembar() -> tuple[dict[str, str], dict[str, str]]:
    """Turunkan pasangan item kembar dari kesamaan redaksi antar dua CSV paket.

    Returns:
        Tuple `(kembar_wcp, kembar_dcs)`: `kembar_wcp[item_id_wcp]` = `"DCS:<item_id>"` dan
        sebaliknya `kembar_dcs[item_id_dcs]` = `"WCP:<item_id>"`. Bukan berdasarkan teks DB.
    """
    wcp = muat_paket(PATH_PAKET_WCP)
    dcs = muat_paket(PATH_PAKET_DCS)
    dcs_by_teks: dict[str, list[str]] = {}
    for item_id, teks in dcs.items():
        dcs_by_teks.setdefault(teks, []).append(item_id)
    kembar_wcp: dict[str, str] = {}
    kembar_dcs: dict[str, str] = {}
    for item_id, teks in wcp.items():
        pasangan = dcs_by_teks.get(teks, [])
        if len(pasangan) == 1:
            kembar_wcp[item_id] = f"DCS:{pasangan[0]}"
            kembar_dcs[pasangan[0]] = f"WCP:{item_id}"
    return kembar_wcp, kembar_dcs


def hitung_hash(items: Iterable[dict[str, object]]) -> str:
    """Hash sha256 hex atas JSON kanonik daftar item aktif.

    Tiap item berbentuk `{item_id, kelompok_kode, pernyataan, arah_atau_reverse, urutan}`.
    Daftar diurutkan menurut `urutan` (lalu `item_id`) sehingga urutan input tidak berpengaruh.
    JSON: `sort_keys`, separator rapat, `ensure_ascii=False`.

    Args:
        items: Item aktif bank.

    Returns:
        String hex sha256 (64 karakter).
    """
    ordered = sorted(items, key=lambda i: (int(i["urutan"]), str(i["item_id"])))  # type: ignore[call-overload]
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
