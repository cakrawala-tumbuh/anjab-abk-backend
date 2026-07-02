"""Helper bersama test OPM: siapkan jabatan + SME panel + sesi Task Inventory frozen.

Bukan file test (tidak diawali `test_`) — diimpor oleh `test_opm_sesi.py`,
`test_opm_responden.py`, dan `test_opm_analisis.py`. Fixture `jabatan_id_tk`
didefinisikan di `conftest.py` (dipakai bersama, tidak perlu diimpor ulang).
"""

from __future__ import annotations

import itertools
import uuid

from fastapi.testclient import TestClient

TI_BASE = "/api/v1/task-inventory"
TI_SESI = f"{TI_BASE}/sesi"
SME_BASE = "/api/v1/sme-panel"
PAR_BASE = "/api/v1/partisipan"
UNIT = "TK"

_periode_counter = itertools.count(3000)


def _uniq_periode() -> str:
    """Periode YYYY-MM unik per pemanggilan (hindari konflik sesi TI)."""
    return f"{next(_periode_counter)}-01"


def _buat_partisipan(client: TestClient, jabatan_id: str, suffix: str) -> str:
    payload = {
        "nama": f"OPM Test {suffix}",
        "email": f"opm.{suffix}.{uuid.uuid4().hex[:6]}@test.id",
        "sekolah_id": "skl_opm_test",
        "jabatan_utama_id": jabatan_id,
        "masa_kerja_tahun": 3,
    }
    r = client.post(PAR_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup_jabatan_panel_ti(client: TestClient, jabatan_id: str) -> dict:
    """Bangun prasyarat OPM: jabatan (sudah ada) → 2 partisipan → SME panel + anggota →
    sesi Task Inventory sampai frozen (TAHAP3, unanimous 2 kode task).

    Mengembalikan dict: jabatan_id, panel_id, partisipan_ids (list[str]),
    ti_sesi_id, kodes (list[str], 2 kode task yang frozen).
    """
    par1 = _buat_partisipan(client, jabatan_id, "A")
    par2 = _buat_partisipan(client, jabatan_id, "B")

    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id})
    assert r.status_code == 201, r.text
    panel = r.json()
    panel_id = panel["id"]
    for pid in (par1, par2):
        r = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": pid})
        assert r.status_code == 200, r.text

    r = client.get(TI_BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id})
    assert r.status_code == 200, r.text
    catalog_items = r.json()
    assert len(catalog_items) >= 2
    kodes = [it["kode"] for it in catalog_items[:2]]

    r = client.post(
        TI_SESI,
        json={
            "jabatan_id": jabatan_id,
            "periode": _uniq_periode(),
            "min_responden": 1,
            "max_responden": 10,
        },
    )
    assert r.status_code == 201, r.text
    ti_sesi = r.json()
    ti_sesi_id = ti_sesi["id"]

    ra = client.post(f"{TI_SESI}/{ti_sesi_id}/responden", json={"nama": "R1"})
    assert ra.status_code == 201, ra.text
    rb = client.post(f"{TI_SESI}/{ti_sesi_id}/responden", json={"nama": "R2"})
    assert rb.status_code == 201, rb.text

    r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap1")
    assert r.status_code == 200, r.text

    for rsp in (ra.json(), rb.json()):
        r = client.post(f"{TI_SESI}/responden/{rsp['id']}/seleksi", json={"task_kode": kodes})
        assert r.status_code == 201, r.text

    r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap2")
    assert r.status_code == 200, r.text

    r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap3")
    assert r.status_code == 200, r.text
    assert r.json()["jumlah_task_terpilih"] == 2

    return {
        "jabatan_id": jabatan_id,
        "panel_id": panel_id,
        "partisipan_ids": [par1, par2],
        "ti_sesi_id": ti_sesi_id,
        "kodes": kodes,
    }
