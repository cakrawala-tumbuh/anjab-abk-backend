"""Test penjaga revisi `3889bd9af66e` — samakan redaksi klon jabatan `Koordinator …`.

Unit murni (tanpa DB): konsistensi berkas beku
`migrations/data/20260729_uraian_klon_koordinator_v2_19_r1.json` terhadap dua
sumber yang sudah ada di repo —

1. `taskinv/data/task_catalog.json`: tiap `kembaran` ada di katalog dan `baru`
   sama persis dengan `uraian_tugas` katalog saat ini (jadi klon benar-benar
   menyalin teks kembarannya, bukan varian ketiga);
2. berkas beku `cdd92c950f19` (`20260728_uraian_sederhana_v2_19_r1.json`):
   pasangan `lama`/`baru` tiap entri klon identik dengan pasangan milik
   kembarannya — bukti kedua revisi menggerakkan teks yang sama.

Ditambah penjaga bahwa kode klon (`KOEKS-`/`KOHUM-`/`KOSAR-`) memang TIDAK ada
di `task_catalog.json` — itulah alasan revisi terpisah ini perlu ada; begitu
suatu saat kode klon dimasukkan ke katalog seed, test ini gagal dan memaksa
keputusan itu ditinjau ulang.

Test level migrasi (upgrade/downgrade langsung ke `ti_uraian_tugas`) ada di
`tests/test_migrations.py`, mengikuti pola `fresh_db_url` yang sudah ada di sana.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOG_PATH = _REPO_ROOT / "src" / "anjab_abk_backend" / "taskinv" / "data" / "task_catalog.json"
_FROZEN_KLON_PATH = (
    _REPO_ROOT / "migrations" / "data" / "20260729_uraian_klon_koordinator_v2_19_r1.json"
)
_FROZEN_REDAKSI_PATH = (
    _REPO_ROOT / "migrations" / "data" / "20260728_uraian_sederhana_v2_19_r1.json"
)

# Sufiks kode kedua sisi identik — pasangan klon <-> kembaran deterministik.
_PETA_PREFIX = {"KOEKS-": "PEK-", "KOHUM-": "WKHUM-", "KOSAR-": "WKSAR-"}


def _muat(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_frozen_klon_75_entri_kode_unik() -> None:
    """Berkas beku berisi tepat 75 entri, `kode` unik, urut menaik menurut `kode`."""
    frozen = _muat(_FROZEN_KLON_PATH)
    assert len(frozen) == 75
    kodes = [e["kode"] for e in frozen]
    assert len(set(kodes)) == 75, "kode harus unik"
    assert kodes == sorted(kodes), "entri harus urut menaik menurut kode"


def test_frozen_klon_kembaran_turun_dari_sufiks_kode() -> None:
    """Tiap `kembaran` = prefix pasangannya + sufiks kode klon yang sama persis."""
    for entry in _muat(_FROZEN_KLON_PATH):
        prefix = next((p for p in _PETA_PREFIX if entry["kode"].startswith(p)), None)
        assert prefix is not None, f"kode {entry['kode']} bukan kode klon Koordinator"
        assert entry["kembaran"] == _PETA_PREFIX[prefix] + entry["kode"][len(prefix) :]


def test_frozen_klon_baru_sinkron_dengan_katalog_kembaran() -> None:
    """Tiap `kembaran` ada di katalog dan `baru` == `uraian_tugas` katalog saat ini."""
    katalog = {e["kode"]: e for e in _muat(_CATALOG_PATH)}
    for entry in _muat(_FROZEN_KLON_PATH):
        kembaran = entry["kembaran"]
        assert kembaran in katalog, f"kembaran {kembaran} tidak ada di task_catalog.json"
        assert entry["lama"] != entry["baru"], f"lama == baru utk {entry['kode']}"
        assert (
            katalog[kembaran]["uraian_tugas"] == entry["baru"]
        ), f"nilai 'baru' utk {entry['kode']} tidak sinkron dgn katalog kembarannya"


def test_frozen_klon_pasangan_teks_identik_dengan_revisi_cdd92c950f19() -> None:
    """Pasangan `lama`/`baru` tiap klon sama persis dengan pasangan milik kembarannya."""
    redaksi = {e["kode"]: e for e in _muat(_FROZEN_REDAKSI_PATH)}
    for entry in _muat(_FROZEN_KLON_PATH):
        sumber = redaksi.get(entry["kembaran"])
        assert sumber is not None, f"kembaran {entry['kembaran']} tidak ada di berkas beku 0728"
        assert entry["lama"] == sumber["lama"]
        assert entry["baru"] == sumber["baru"]


def test_kode_klon_memang_tidak_ada_di_katalog_seed() -> None:
    """Kode `KO*` tidak ada di `task_catalog.json` — alasan revisi terpisah ini ada."""
    kodes_katalog = {e["kode"] for e in _muat(_CATALOG_PATH)}
    for entry in _muat(_FROZEN_KLON_PATH):
        assert entry["kode"] not in kodes_katalog, (
            f"{entry['kode']} kini ada di task_catalog.json — tinjau ulang: klon seharusnya "
            "ikut jalur seed/`cdd92c950f19`, bukan revisi klon terpisah"
        )
