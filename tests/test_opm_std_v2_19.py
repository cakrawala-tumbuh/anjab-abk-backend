"""Test penjaga backlog `anjab-abk-backend#33` — nilai standar OPM di katalog TI.

Dua lapis:

1. Unit murni (tanpa DB): konsistensi berkas beku
   `migrations/data/20260729_opm_std_values_v2_19.json` — 1138 entri, `kode` unik &
   urut, seluruh `kode` ada di `task_catalog.json`, `importance`/`criticality` 1-5
   penuh, `frequency` 1-5 atau `null` (tepat 15 entri `null`), dan nilainya sinkron
   dengan `std_opm_*` yang sudah ditulis ke `task_catalog.json` pada commit yang sama.
2. Integrasi (DB ter-seed, fixture `client` di `conftest.py`): endpoint search
   `uraian-tugas` menyajikan `std_opm_*` sesuai berkas beku untuk kode kontrol.

Test level migrasi (upgrade/downgrade `ti_uraian_tugas_jabatan.std_opm_*`) ada di
`tests/test_migrations.py`, mengikuti pola `fresh_db_url` yang sudah ada di sana.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

UT_BASE = "/api/v1/task-inventory/uraian-tugas"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOG_PATH = _REPO_ROOT / "src" / "anjab_abk_backend" / "taskinv" / "data" / "task_catalog.json"
_FROZEN_PATH = _REPO_ROOT / "migrations" / "data" / "20260729_opm_std_values_v2_19.json"


def _muat_katalog() -> list[dict]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _muat_frozen() -> list[dict[str, object]]:
    with _FROZEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_frozen_1138_entri_kode_unik_urut() -> None:
    """Berkas beku berisi tepat 1138 entri, `kode` unik, urut menaik menurut `kode`."""
    frozen = _muat_frozen()
    assert len(frozen) == 1138
    kodes = [e["kode"] for e in frozen]
    assert len(set(kodes)) == 1138, "kode harus unik"
    assert kodes == sorted(kodes), "entri harus urut menaik menurut kode"


def test_frozen_semua_kode_ada_di_katalog() -> None:
    """Setiap `kode` di berkas beku ada di `task_catalog.json` (1138 entri, tak berubah)."""
    katalog = {e["kode"]: e for e in _muat_katalog()}
    assert len(katalog) == 1138, "task_catalog.json harus tetap 1138 entri"
    for entry in _muat_frozen():
        assert entry["kode"] in katalog, f"kode {entry['kode']} tidak ada di task_catalog.json"


def test_frozen_importance_dan_criticality_penuh_1_5() -> None:
    """`importance`/`criticality` terisi penuh (tidak ada `null`), rentang 1-5."""
    for entry in _muat_frozen():
        assert entry["importance"] is not None, f"importance null utk {entry['kode']}"
        assert 1 <= entry["importance"] <= 5
        assert entry["criticality"] is not None, f"criticality null utk {entry['kode']}"
        assert 1 <= entry["criticality"] <= 5


def test_frozen_frequency_1_5_atau_null_tepat_15_null() -> None:
    """`frequency` bernilai 1-5 atau `null`; tepat 15 entri `null` (Frequency kotor)."""
    frozen = _muat_frozen()
    n_null = 0
    for entry in frozen:
        freq = entry["frequency"]
        if freq is None:
            n_null += 1
        else:
            assert 1 <= freq <= 5, f"frequency di luar rentang utk {entry['kode']}: {freq}"
    assert n_null == 15, f"harus tepat 15 entri frequency null, dapat {n_null}"


def test_frozen_sinkron_dengan_task_catalog_json() -> None:
    """Nilai `std_opm_*` di `task_catalog.json` sama persis dengan berkas beku per kode."""
    katalog = {e["kode"]: e for e in _muat_katalog()}
    for entry in _muat_frozen():
        row = katalog[entry["kode"]]
        assert row["std_opm_importance"] == entry["importance"], entry["kode"]
        assert row["std_opm_frequency"] == entry["frequency"], entry["kode"]
        assert row["std_opm_criticality"] == entry["criticality"], entry["kode"]


def test_katalog_kode_kontrol_bawa_nilai_standar_opm(client: TestClient) -> None:
    """`KS-ALL-LEAD-001` (nilai penuh, tanpa Frequency kotor) tersaji sesuai berkas beku
    di DB ter-seed."""
    frozen = {e["kode"]: e for e in _muat_frozen()}
    entry = frozen["KS-ALL-LEAD-001"]
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", "KS-ALL-LEAD-001"]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["std_opm_importance"] == entry["importance"]
    assert item["std_opm_frequency"] == entry["frequency"]
    assert item["std_opm_criticality"] == entry["criticality"]


def test_katalog_kode_kontrol_frequency_kotor_null(client: TestClient) -> None:
    """`GKSD-SD-ADMIN-002` (Frequency kotor `Baseline`) → `std_opm_frequency = null`."""
    frozen = {e["kode"]: e for e in _muat_frozen()}
    entry = frozen["GKSD-SD-ADMIN-002"]
    assert entry["frequency"] is None
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", "GKSD-SD-ADMIN-002"]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["std_opm_importance"] == entry["importance"]
    assert item["std_opm_frequency"] is None
    assert item["std_opm_criticality"] == entry["criticality"]
