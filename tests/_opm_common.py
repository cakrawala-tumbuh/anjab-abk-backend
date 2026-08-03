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
UNIT = "ALL"

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


def _setup_jabatan_panel_ti(
    client: TestClient, jabatan_id: str, *, cabang: str = "Bandung"
) -> dict:
    """Bangun prasyarat OPM: jabatan (sudah ada) → SME panel (2 anggota) → sesi Task
    Inventory sampai frozen (TAHAP3, unanimous 2 kode task).

    Panel dibuat SEBELUM sesi TI (bukan sesudahnya) — `SqlTiSesiService.create()`
    auto-populate responden dari anggota panel yang ADA SAAT sesi dibuat (entri
    `[2026-07-13]` CLAUDE.md), jadi kedua anggota otomatis jadi responden TI tanpa
    perlu `POST .../responden` manual. Ini juga prasyarat wajib backlog
    `anjab-abk-backend#37`: `POST .../responden` dengan `partisipan_id` eksplisit
    menolak `422` bila partisipan itu BUKAN anggota panel jabatan sesi ini —
    membuat responden lebih dulu (sebelum panel ada) seperti pola lama sudah tidak
    mungkin lagi dikombinasikan dengan `partisipan_id` yang tervalidasi.

    Mengembalikan dict: jabatan_id, panel_id, partisipan_ids (list[str]),
    ti_sesi_id, ti_responden_ids (list[str]), kodes (list[str], 2 kode task frozen).
    """
    par1 = _buat_partisipan(client, jabatan_id, "A")
    par2 = _buat_partisipan(client, jabatan_id, "B")

    r = client.get(TI_BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id})
    assert r.status_code == 200, r.text
    catalog_items = r.json()["items"]
    assert len(catalog_items) >= 2
    kodes = [it["kode"] for it in catalog_items[:2]]

    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id})
    assert r.status_code == 201, r.text
    panel_id = r.json()["id"]
    for pid in (par1, par2):
        r = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": pid})
        assert r.status_code == 200, r.text

    r = client.post(TI_SESI, json={"jabatan_id": jabatan_id, "cabang": cabang})
    assert r.status_code == 201, r.text
    ti_sesi_id = r.json()["id"]

    responden = client.get(f"{TI_SESI}/{ti_sesi_id}/responden").json()["items"]
    assert {x["partisipan_id"] for x in responden} == {
        par1,
        par2,
    }, "auto-populate TI diharapkan mendaftarkan kedua anggota panel sebagai responden"
    responden_ids = [x["id"] for x in responden]

    r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap1")
    assert r.status_code == 200, r.text

    for rid in responden_ids:
        r = client.put(f"{TI_SESI}/responden/{rid}/seleksi", json={"task_kode": kodes})
        assert r.status_code == 200, r.text
        r = client.post(f"{TI_SESI}/responden/{rid}/seleksi/submit")
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
        "ti_responden_ids": responden_ids,
        "kodes": kodes,
    }


def _setup_jabatan_dua_cabang(client: TestClient, jabatan_id: str) -> dict:
    """Bangun prasyarat OPM dengan DUA sesi Task Inventory frozen untuk jabatan yang
    SAMA — satu Bandung, satu Semarang — masing-masing dengan submitter Tahap 1 yang
    BERBEDA, walau keduanya diambil dari SATU SME panel milik jabatan ini (backlog
    `anjab-abk-backend#37`: buktikan responden OPM per cabang tidak saling campur).

    Anggota panel diganti (hapus lalu tambah) DI ANTARA kedua sesi TI — auto-populate
    TI hanya melihat anggota panel yang ADA SAAT sesi TI dibuat, jadi hasilnya dua
    himpunan responden TI yang saling lepas meski panel-nya (dan gerbang keberadaan
    panel di langkah 3 create sesi OPM) tetap satu untuk jabatan ini sepanjang waktu.

    Mengembalikan dict: jabatan_id, panel_id,
    ti_sesi_ids ({"Bandung": id, "Semarang": id}),
    submitter_ids ({"Bandung": [partisipan_id, ...], "Semarang": [...]}), kodes.
    """
    par_bdg = _buat_partisipan(client, jabatan_id, "BDG")
    par_smg = _buat_partisipan(client, jabatan_id, "SMG")

    r = client.get(TI_BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id})
    assert r.status_code == 200, r.text
    catalog_items = r.json()["items"]
    assert len(catalog_items) >= 2
    kodes = [it["kode"] for it in catalog_items[:2]]

    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id})
    assert r.status_code == 201, r.text
    panel_id = r.json()["id"]

    ti_sesi_ids: dict[str, str] = {}
    submitter_ids: dict[str, list[str]] = {}
    for cabang, par_id in (("Bandung", par_bdg), ("Semarang", par_smg)):
        r = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par_id})
        assert r.status_code == 200, r.text

        r = client.post(TI_SESI, json={"jabatan_id": jabatan_id, "cabang": cabang})
        assert r.status_code == 201, r.text
        ti_sesi_id = r.json()["id"]
        ti_sesi_ids[cabang] = ti_sesi_id

        responden = client.get(f"{TI_SESI}/{ti_sesi_id}/responden").json()["items"]
        assert {x["partisipan_id"] for x in responden} == {par_id}
        responden_id = responden[0]["id"]

        r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap1")
        assert r.status_code == 200, r.text

        r = client.put(f"{TI_SESI}/responden/{responden_id}/seleksi", json={"task_kode": kodes})
        assert r.status_code == 200, r.text
        r = client.post(f"{TI_SESI}/responden/{responden_id}/seleksi/submit")
        assert r.status_code == 201, r.text

        r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap2")
        assert r.status_code == 200, r.text
        r = client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap3")
        assert r.status_code == 200, r.text
        assert r.json()["jumlah_task_terpilih"] == 2

        submitter_ids[cabang] = [par_id]

        # Keluarkan anggota cabang ini dari panel sebelum lanjut ke cabang
        # berikutnya, agar auto-populate sesi TI Semarang TIDAK ikut mendaftarkan
        # par_bdg (panel per-jabatan bersifat mutable & dibaca ULANG tiap sesi TI
        # baru dibuat — bukan snapshot per cabang).
        r = client.delete(f"{SME_BASE}/{panel_id}/anggota/{par_id}")
        assert r.status_code == 200, r.text

    # Panel diakhiri TIDAK kosong (anggota terakhir, par_smg, ditambahkan lagi) —
    # gerbang langkah 3 create sesi OPM ("panel wajib punya anggota") tetap terjaga.
    r = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par_smg})
    assert r.status_code == 200, r.text

    return {
        "jabatan_id": jabatan_id,
        "panel_id": panel_id,
        "ti_sesi_ids": ti_sesi_ids,
        "submitter_ids": submitter_ids,
        "kodes": kodes,
    }
