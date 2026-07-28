"""Test penjaga backlog `anjab-abk-backend#30` — redaksi sederhana v2.19-R1.

Dua lapis:

1. Unit murni (tanpa DB): konsistensi berkas beku
   `migrations/data/20260728_uraian_sederhana_v2_19_r1.json` terhadap
   `taskinv/data/task_catalog.json` — 740 entri, `kode` unik, seluruh `kode` ada
   di katalog, `baru` sama persis dengan nilai `uraian_tugas` katalog saat ini,
   dan `lama != baru`.
2. Integrasi (DB test yang sudah di-seed, fixture `client` di `conftest.py`):
   kode `ELIGIBLE` (`KS-ALL-ADMIN-001`) tersaji dengan redaksi sederhana; kode
   yang masih menunggu klarifikasi SME (`KS-ALL-LEAD-001`, `SPLIT_REQUIRED`)
   tetap bertext 5C asli — membuktikan seed instalasi baru & migrasi data
   memberi hasil akhir yang identik.

Test level migrasi (upgrade/downgrade langsung ke `ti_uraian_tugas`) ada di
`tests/test_migrations.py`, mengikuti pola `fresh_db_url` yang sudah ada di sana.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

UT_BASE = "/api/v1/task-inventory/uraian-tugas"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOG_PATH = _REPO_ROOT / "src" / "anjab_abk_backend" / "taskinv" / "data" / "task_catalog.json"
_FROZEN_PATH = _REPO_ROOT / "migrations" / "data" / "20260728_uraian_sederhana_v2_19_r1.json"


def _muat_katalog() -> list[dict]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _muat_frozen() -> list[dict[str, str]]:
    with _FROZEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_frozen_740_entri_kode_unik() -> None:
    """Berkas beku berisi tepat 740 entri, `kode` unik, urut menaik menurut `kode`."""
    frozen = _muat_frozen()
    assert len(frozen) == 740
    kodes = [e["kode"] for e in frozen]
    assert len(set(kodes)) == 740, "kode harus unik"
    assert kodes == sorted(kodes), "entri harus urut menaik menurut kode"


def test_frozen_semua_kode_ada_di_katalog_dan_baru_sinkron() -> None:
    """Tiap entri beku: `kode` ada di katalog, `baru` == nilai katalog saat ini, `lama != baru`."""
    katalog = {e["kode"]: e for e in _muat_katalog()}
    frozen = _muat_frozen()
    assert len(katalog) == 1138, "task_catalog.json harus tetap 1138 entri"

    for entry in frozen:
        assert entry["kode"] in katalog, f"kode {entry['kode']} tidak ada di task_catalog.json"
        assert entry["lama"] != entry["baru"], f"lama == baru utk {entry['kode']}"
        assert (
            katalog[entry["kode"]]["uraian_tugas"] == entry["baru"]
        ), f"uraian_tugas katalog utk {entry['kode']} tidak sinkron dgn nilai 'baru' beku"


def test_katalog_398_non_eligible_tidak_berubah_via_kode_kontrol() -> None:
    """Kode kontrol non-ELIGIBLE (`KS-ALL-LEAD-001`, `SPLIT_REQUIRED`) tidak ikut termasuk beku."""
    frozen_kodes = {e["kode"] for e in _muat_frozen()}
    assert "KS-ALL-LEAD-001" not in frozen_kodes
    assert "KS-ALL-ADMIN-001" in frozen_kodes


def test_katalog_eligible_bertext_sederhana(client: TestClient) -> None:
    """`KS-ALL-ADMIN-001` (ELIGIBLE) tersaji dengan redaksi sederhana v2.19-R1 di DB ter-seed."""
    frozen = {e["kode"]: e for e in _muat_frozen()}
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", "KS-ALL-ADMIN-001"]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["uraian"] == frozen["KS-ALL-ADMIN-001"]["baru"]


def test_katalog_non_eligible_tetap_5c_asli(client: TestClient) -> None:
    """`KS-ALL-LEAD-001` (SPLIT_REQUIRED, belum diklarifikasi SME) tetap bertext 5C asli."""
    katalog = {e["kode"]: e for e in _muat_katalog()}
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", "KS-ALL-LEAD-001"]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["uraian"] == katalog["KS-ALL-LEAD-001"]["uraian_tugas"]
