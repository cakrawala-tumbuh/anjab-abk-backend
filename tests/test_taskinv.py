"""Test endpoint Task Inventory: catalog, alur 2 tahap, transisi, agregasi."""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/task-inventory"
SESI = f"{BASE}/sesi"
UNIT = "TK"
KATEGORI = "Kepala Sekolah"

_year_counter = itertools.count(2000)


def _uniq_periode() -> str:
    """Periode YYYY-MM unik per pemanggilan (hindari konflik unit+jabatan+periode)."""
    return f"{next(_year_counter)}-01"


def _sesi_payload(periode: str | None = None, **over) -> dict:
    payload = {
        "unit": UNIT,
        "kategori_jabatan": KATEGORI,
        "periode": periode or _uniq_periode(),
        "min_responden": 1,
        "max_responden": 10,
    }
    payload.update(over)
    return payload


def _catalog_kodes(client: TestClient, n: int) -> list[str]:
    r = client.get(BASE + "/catalog", params={"unit": UNIT, "kategori_jabatan": KATEGORI})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= n
    return [it["kode"] for it in items[:n]]


def _create_sesi(client: TestClient, **over) -> dict:
    r = client.post(SESI, json=_sesi_payload(**over))
    assert r.status_code == 201, r.text
    return r.json()


def _add_responden(client: TestClient, sesi_id: str, nama: str) -> dict:
    r = client.post(f"{SESI}/{sesi_id}/responden", json={"nama": nama})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def test_catalog_kombinasi(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog/kombinasi")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 51
    target = next(x for x in rows if x["unit"] == UNIT and x["kategori_jabatan"] == KATEGORI)
    assert target["jumlah_task"] > 0


def test_catalog_list_by_kombinasi(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog", params={"unit": UNIT, "kategori_jabatan": KATEGORI})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == UNIT and it["kategori_jabatan"] == KATEGORI for it in items)
    assert items[0]["kode"].startswith("TI")


def test_catalog_unknown_kombinasi_empty(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog", params={"unit": "ZZ", "kategori_jabatan": "X"})
    assert r.status_code == 200
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Sesi CRUD
# --------------------------------------------------------------------------- #


def test_sesi_create_and_get(client: TestClient) -> None:
    sesi = _create_sesi(client)
    assert sesi["id"].startswith("tises_")
    assert sesi["status"] == "DRAFT"
    assert sesi["jumlah_task_terpilih"] is None
    r = client.get(f"{SESI}/{sesi['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == sesi["id"]


def test_sesi_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(SESI, json=_sesi_payload())
    assert r.status_code == 401


def test_sesi_create_invalid_kombinasi(client: TestClient) -> None:
    r = client.post(SESI, json=_sesi_payload(unit="ZZ", kategori_jabatan="X"))
    assert r.status_code in (400, 422)


def test_sesi_duplicate_conflict(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(SESI, json=_sesi_payload(periode=sesi["periode"]))
    assert r.status_code == 409


def test_sesi_min_gt_max_rejected(client: TestClient) -> None:
    r = client.post(SESI, json=_sesi_payload(min_responden=5, max_responden=2))
    assert r.status_code in (400, 422)


def test_sesi_update_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.patch(f"{SESI}/{sesi['id']}", json={"catatan": "halo"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "halo"


def test_sesi_delete_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.delete(f"{SESI}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{SESI}/{sesi['id']}").status_code == 404


def test_sesi_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{SESI}/tises_xxx").status_code == 404


def test_sesi_search(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(
        f"{SESI}/search", json={"domain": [["id", "=", sesi["id"]]], "limit": 10, "offset": 0}
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


# --------------------------------------------------------------------------- #
# Transisi tahap
# --------------------------------------------------------------------------- #


def test_mulai_tahap1(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    assert r.status_code == 200
    assert r.json()["status"] == "TAHAP1"


def test_mulai_tahap2_invalid_from_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap2")
    assert r.status_code in (400, 422)


def test_mulai_tahap2_guard_belum_semua_submit(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r1 = _add_responden(client, sid, "A")
    _add_responden(client, sid, "B")  # tidak submit
    kodes = _catalog_kodes(client, 3)
    assert (
        client.post(
            f"{SESI}/responden/{r1['id']}/seleksi", json={"task_kode": kodes[:2]}
        ).status_code
        == 201
    )
    # 1 dari 2 submit → tanpa paksa harus gagal
    r = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r.status_code in (400, 422)
    # dengan paksa → sukses, union = 2 task
    r = client.post(f"{SESI}/{sid}/mulai-tahap2", params={"paksa": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "TAHAP2"
    assert r.json()["jumlah_task_terpilih"] == 2


# --------------------------------------------------------------------------- #
# Seleksi Tahap 1
# --------------------------------------------------------------------------- #


def test_seleksi_invalid_kode(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": ["TItidakvalid"]})
    assert res.status_code in (400, 422)


def test_seleksi_requires_tahap1(client: TestClient) -> None:
    sesi = _create_sesi(client)  # masih DRAFT
    sid = sesi["id"]
    # responden hanya bisa ditambah saat DRAFT/TAHAP1; tambah saat DRAFT
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 1)
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code in (400, 422)


def test_seleksi_double_submit_conflict(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 2)
    assert (
        client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes}).status_code
        == 201
    )
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code in (400, 409, 422)
    # get seleksi
    g = client.get(f"{SESI}/responden/{r['id']}/seleksi")
    assert g.status_code == 200
    assert set(g.json()["task_kode"]) == set(kodes)


# --------------------------------------------------------------------------- #
# Alur penuh 2 tahap + agregasi
# --------------------------------------------------------------------------- #


def test_full_two_phase_flow(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 3)  # K0, K1, K2

    # Tahap 1
    assert client.post(f"{SESI}/{sid}/mulai-tahap1").json()["status"] == "TAHAP1"
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # A pilih K0,K1 ; B pilih K1,K2  → union = K0,K1,K2 ; K1 relevan utk 2 orang
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0], kodes[1]]})
    client.post(f"{SESI}/responden/{rb['id']}/seleksi", json={"task_kode": [kodes[1], kodes[2]]})

    # Tahap 2 (semua submit → tanpa paksa)
    r2 = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r2.status_code == 200, r2.text
    assert r2.json()["jumlah_task_terpilih"] == 3

    # task-terpilih: K1 harus n_relevan=2
    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200
    by_kode = {x["kode"]: x for x in tt.json()}
    assert by_kode[kodes[1]]["n_relevan"] == 2
    assert by_kode[kodes[0]]["n_relevan"] == 1

    # Detail Tahap 2: A isi K0,K1 ; B isi K1,K2
    def _ditem(kode: str, jpm: float) -> dict:
        return {
            "task_kode": kode,
            "sumber_bukti": "Aktual",
            "kondisi": "Baseline",
            "frekuensi_teks": "Mingguan",
            "durasi_per_kali": 60,
            "jam_per_minggu": jpm,
            "peak4w_hours": 0,
            "ai_mode": "Human-led",
            "va_type": "VA-Core",
            "dcs_flag": False,
        }

    da = client.post(
        f"{SESI}/responden/{ra['id']}/detail",
        json={"detail": [_ditem(kodes[0], 2.0), _ditem(kodes[1], 4.0)]},
    )
    assert da.status_code == 201, da.text
    db = client.post(
        f"{SESI}/responden/{rb['id']}/detail",
        json={"detail": [_ditem(kodes[1], 6.0), _ditem(kodes[2], 1.0)]},
    )
    assert db.status_code == 201, db.text

    # Tutup → analisis
    assert client.post(f"{SESI}/{sid}/tutup").json()["status"] == "CLOSED"
    an = client.post(f"{SESI}/{sid}/analisis")
    assert an.status_code == 200, an.text
    hasil = an.json()
    assert hasil["status"] if "status" in hasil else True
    assert hasil["n_responden_tahap1"] == 2
    assert hasil["n_responden_tahap2"] == 2
    assert hasil["jumlah_task_terpilih"] == 3

    tasks = {t["kode"]: t for t in hasil["tasks"]}
    # K1: rata-rata jam/minggu (4+6)/2 = 5 → jam/tahun = 225
    assert tasks[kodes[1]]["jam_per_minggu_mean"] == 5.0
    assert tasks[kodes[1]]["jam_per_tahun_mean"] == 225.0
    assert tasks[kodes[1]]["n_detail"] == 2
    assert tasks[kodes[0]]["jam_per_minggu_mean"] == 2.0
    # total jam/minggu = 2 + 5 + 1 = 8
    assert hasil["total_jam_per_minggu"] == 8.0

    # hasil GET tersedia setelah ANALYZED
    hg = client.get(f"{SESI}/{sid}/hasil")
    assert hg.status_code == 200
    assert hg.json()["jumlah_task_terpilih"] == 3


def test_detail_kode_diluar_terpilih_ditolak(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 4)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0]]})
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    # kodes[3] tidak ada di union (hanya kodes[0])
    res = client.post(
        f"{SESI}/responden/{ra['id']}/detail",
        json={
            "detail": [
                {
                    "task_kode": kodes[3],
                    "sumber_bukti": "Aktual",
                    "kondisi": "Baseline",
                    "frekuensi_teks": "Harian",
                    "durasi_per_kali": 30,
                    "jam_per_minggu": 1.0,
                    "ai_mode": "Co-Pilot",
                    "va_type": "VA-Enable",
                }
            ]
        },
    )
    assert res.status_code in (400, 422)


def test_hasil_belum_analyzed(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.get(f"{SESI}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)


def test_responden_delete_setelah_submit_ditolak(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    r = client.delete(f"{SESI}/responden/{ra['id']}")
    assert r.status_code in (400, 422)


@pytest.mark.parametrize("field", ["sumber_bukti", "ai_mode", "va_type"])
def test_detail_enum_invalid(client: TestClient, field: str) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    item = {
        "task_kode": kodes[0],
        "sumber_bukti": "Aktual",
        "kondisi": "Baseline",
        "frekuensi_teks": "Harian",
        "durasi_per_kali": 30,
        "jam_per_minggu": 1.0,
        "ai_mode": "Human-led",
        "va_type": "VA-Core",
    }
    item[field] = "NILAI_SALAH"
    res = client.post(f"{SESI}/responden/{ra['id']}/detail", json={"detail": [item]})
    assert res.status_code == 422
