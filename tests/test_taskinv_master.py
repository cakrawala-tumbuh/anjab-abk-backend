"""Test CRUD + search endpoint TugasPokok, DetilTugas, UraianTugas."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

TP_BASE = "/api/v1/task-inventory/tugas-pokok"
DT_BASE = "/api/v1/task-inventory/detil-tugas"
UT_BASE = "/api/v1/task-inventory/uraian-tugas"
CATALOG_BASE = "/api/v1/task-inventory/catalog"
JABATAN_BASE = "/api/v1/jabatan"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _uniq(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _create_jabatan(client: TestClient, nama: str | None = None) -> dict:
    kode = _uniq("JBT")
    payload = {
        "kode": kode,
        "nama": nama or f"Jabatan {_uniq()}",
        "jenis": "fungsional",
        "aktif": True,
    }
    r = client.post(JABATAN_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_tp(
    client: TestClient,
    jabatan_ids: list[str] | None = None,
    nama: str | None = None,
) -> dict:
    if jabatan_ids is None:
        jbt = _create_jabatan(client)
        jabatan_ids = [jbt["id"]]
    payload = {"jabatan_ids": jabatan_ids, "nama": nama or f"Tugas Pokok {_uniq()}"}
    r = client.post(TP_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_dt(
    client: TestClient,
    tugas_pokok_id: str,
    jabatan_ids: list[str],
    nama: str | None = None,
) -> dict:
    payload = {
        "nama": nama or f"Detil Tugas {_uniq()}",
        "tugas_pokok_id": tugas_pokok_id,
        "jabatan_ids": jabatan_ids,
    }
    r = client.post(DT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_ut(
    client: TestClient,
    detil_tugas_id: str,
    tugas_pokok_id: str,
    jabatan_id: str,
) -> dict:
    kode = f"TI{uuid.uuid4().hex[:8]}"
    payload = {
        "kode": kode,
        "uraian": f"Uraian tugas {kode}",
        "unit": "TK",
        "urutan": 1,
        "detil_tugas_id": detil_tugas_id,
        "tugas_pokok_id": tugas_pokok_id,
        "jabatan_id": jabatan_id,
    }
    r = client.post(UT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# TugasPokok
# --------------------------------------------------------------------------- #


def test_tp_list_ok(client: TestClient) -> None:
    r = client.get(TP_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] > 0  # seeded from task_catalog.json


def test_tp_create_and_get(client: TestClient) -> None:
    tp = _create_tp(client)
    assert tp["id"].startswith("tp_")
    assert tp["nama"]
    assert isinstance(tp["jabatan_ids"], list)
    assert len(tp["jabatan_ids"]) >= 1
    r = client.get(f"{TP_BASE}/{tp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == tp["id"]


def test_tp_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(TP_BASE, json={"jabatan_ids": ["jbt_xxx"], "nama": "Tanpa Auth"})
    assert r.status_code == 401


def test_tp_create_conflict_same_nama(client: TestClient) -> None:
    """Nama sama → 409 (nama adalah kunci unik global, jabatan_ids tidak relevan)."""
    jbt = _create_jabatan(client)
    nama = f"TP Duplikat {_uniq()}"
    _create_tp(client, jabatan_ids=[jbt["id"]], nama=nama)
    # Sama nama → 409, walaupun jabatan_ids berbeda
    jbt2 = _create_jabatan(client)
    r = client.post(TP_BASE, json={"jabatan_ids": [jbt2["id"]], "nama": nama})
    assert r.status_code == 409


def test_tp_create_multi_jabatan(client: TestClient) -> None:
    """TP boleh punya lebih dari satu jabatan (M2M)."""
    jbt1 = _create_jabatan(client)
    jbt2 = _create_jabatan(client)
    tp = _create_tp(client, jabatan_ids=[jbt1["id"], jbt2["id"]])
    assert set(tp["jabatan_ids"]) == {jbt1["id"], jbt2["id"]}


def test_tp_etag_304(client: TestClient) -> None:
    tp = _create_tp(client)
    r1 = client.get(f"{TP_BASE}/{tp['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{TP_BASE}/{tp['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_tp_update(client: TestClient) -> None:
    tp = _create_tp(client)
    nama_baru = f"Updated {_uniq()}"
    r = client.patch(f"{TP_BASE}/{tp['id']}", json={"nama": nama_baru})
    assert r.status_code == 200
    assert r.json()["nama"] == nama_baru


def test_tp_update_jabatan_ids(client: TestClient) -> None:
    """Update jabatan_ids harus menggantikan seluruh daftar lama."""
    jbt1 = _create_jabatan(client)
    tp = _create_tp(client, jabatan_ids=[jbt1["id"]])
    jbt2 = _create_jabatan(client)
    r = client.patch(f"{TP_BASE}/{tp['id']}", json={"jabatan_ids": [jbt1["id"], jbt2["id"]]})
    assert r.status_code == 200
    assert set(r.json()["jabatan_ids"]) == {jbt1["id"], jbt2["id"]}


def test_tp_delete(client: TestClient) -> None:
    tp = _create_tp(client)
    assert client.delete(f"{TP_BASE}/{tp['id']}").status_code == 204
    assert client.get(f"{TP_BASE}/{tp['id']}").status_code == 404


def test_tp_not_found(client: TestClient) -> None:
    assert client.get(f"{TP_BASE}/tp_tidakada").status_code == 404


def test_tp_search(client: TestClient) -> None:
    tp = _create_tp(client)
    r = client.post(
        f"{TP_BASE}/search",
        json={"domain": [["id", "=", tp["id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == tp["id"]


def test_tp_search_by_nama(client: TestClient) -> None:
    nama = f"TP Search Nama {_uniq()}"
    tp = _create_tp(client, nama=nama)
    r = client.post(
        f"{TP_BASE}/search",
        json={"domain": [["nama", "=", nama]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == tp["id"] for it in body["items"])


# --------------------------------------------------------------------------- #
# DetilTugas
# --------------------------------------------------------------------------- #


@pytest.fixture
def tp_jbt_for_dt(client: TestClient) -> tuple[dict, str]:
    """Returns (tp_dict, jabatan_id) so DT tests can pass jabatan_ids."""
    jbt = _create_jabatan(client)
    tp = _create_tp(client, jabatan_ids=[jbt["id"]], nama=f"TP untuk DT {_uniq()}")
    return tp, jbt["id"]


def test_dt_list_ok(client: TestClient) -> None:
    r = client.get(DT_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] > 0  # seeded from task_catalog.json


def test_dt_create_and_get(client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    dt = _create_dt(client, tp["id"], jabatan_ids=[jbt_id])
    assert dt["id"].startswith("dt_")
    assert dt["tugas_pokok_id"] == tp["id"]
    assert isinstance(dt["jabatan_ids"], list)
    assert jbt_id in dt["jabatan_ids"]
    r = client.get(f"{DT_BASE}/{dt['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == dt["id"]


def test_dt_create_requires_auth(anon_client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    r = anon_client.post(
        DT_BASE,
        json={
            "nama": "Tanpa Auth",
            "tugas_pokok_id": tp["id"],
            "jabatan_ids": [jbt_id],
        },
    )
    assert r.status_code == 401


def test_dt_jabatan_ids_must_be_subset_of_tp(
    client: TestClient, tp_jbt_for_dt: tuple[dict, str]
) -> None:
    """jabatan_ids DT yang bukan subset dari TP → 422."""
    tp, _ = tp_jbt_for_dt
    jbt_lain = _create_jabatan(client)
    r = client.post(
        DT_BASE,
        json={
            "nama": f"DT Invalid {_uniq()}",
            "tugas_pokok_id": tp["id"],
            "jabatan_ids": [jbt_lain["id"]],
        },
    )
    assert r.status_code == 422


def test_dt_etag_304(client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    dt = _create_dt(client, tp["id"], jabatan_ids=[jbt_id])
    r1 = client.get(f"{DT_BASE}/{dt['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{DT_BASE}/{dt['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_dt_update(client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    dt = _create_dt(client, tp["id"], jabatan_ids=[jbt_id])
    nama_baru = f"Updated DT {_uniq()}"
    r = client.patch(f"{DT_BASE}/{dt['id']}", json={"nama": nama_baru})
    assert r.status_code == 200
    assert r.json()["nama"] == nama_baru


def test_dt_delete(client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    dt = _create_dt(client, tp["id"], jabatan_ids=[jbt_id])
    assert client.delete(f"{DT_BASE}/{dt['id']}").status_code == 204
    assert client.get(f"{DT_BASE}/{dt['id']}").status_code == 404


def test_dt_not_found(client: TestClient) -> None:
    assert client.get(f"{DT_BASE}/dt_tidakada").status_code == 404


def test_dt_search(client: TestClient, tp_jbt_for_dt: tuple[dict, str]) -> None:
    tp, jbt_id = tp_jbt_for_dt
    _create_dt(client, tp["id"], jabatan_ids=[jbt_id])
    r = client.post(
        f"{DT_BASE}/search",
        json={"domain": [["tugas_pokok_id", "=", tp["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(it["tugas_pokok_id"] == tp["id"] for it in body["items"])


# --------------------------------------------------------------------------- #
# UraianTugas
# --------------------------------------------------------------------------- #


@pytest.fixture
def tp_dt_jbt_for_ut(client: TestClient) -> tuple[dict, dict, str]:
    """Returns (tp_dict, dt_dict, jabatan_id) for UT tests."""
    jbt = _create_jabatan(client)
    tp = _create_tp(client, jabatan_ids=[jbt["id"]], nama=f"TP untuk UT {_uniq()}")
    dt = _create_dt(client, tp["id"], jabatan_ids=[jbt["id"]], nama=f"DT untuk UT {_uniq()}")
    return tp, dt, jbt["id"]


def test_ut_list_ok(client: TestClient) -> None:
    r = client.get(UT_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] >= 1140  # seeded from task_catalog.json (Task Bank v2_19)


def test_ut_create_and_get(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    assert ut["id"].startswith("ut_")
    assert ut["detil_tugas_id"] == dt["id"]
    assert ut["tugas_pokok_id"] == tp["id"]
    assert ut["jabatan_id"] == jbt_id
    r = client.get(f"{UT_BASE}/{ut['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == ut["id"]


def test_ut_create_requires_auth(
    anon_client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    r = anon_client.post(
        UT_BASE,
        json={
            "kode": f"TI{_uniq()}",
            "uraian": "Test",
            "unit": "TK",
            "urutan": 1,
            "detil_tugas_id": dt["id"],
            "tugas_pokok_id": tp["id"],
            "jabatan_id": jbt_id,
        },
    )
    assert r.status_code == 401


def test_ut_create_conflict(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.post(
        UT_BASE,
        json={
            "kode": ut["kode"],
            "uraian": "Duplikat",
            "unit": "TK",
            "urutan": 2,
            "detil_tugas_id": dt["id"],
            "tugas_pokok_id": tp["id"],
            "jabatan_id": jbt_id,
        },
    )
    assert r.status_code == 409


def test_ut_jabatan_id_must_be_in_dt(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    """jabatan_id yang tidak ada di DT's jabatan_ids → 422."""
    tp, dt, _ = tp_dt_jbt_for_ut
    jbt_lain = _create_jabatan(client)
    r = client.post(
        UT_BASE,
        json={
            "kode": f"TI{_uniq()}",
            "uraian": "Test jabatan invalid",
            "unit": "TK",
            "urutan": 1,
            "detil_tugas_id": dt["id"],
            "tugas_pokok_id": tp["id"],
            "jabatan_id": jbt_lain["id"],
        },
    )
    assert r.status_code == 422


def test_ut_etag_304(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r1 = client.get(f"{UT_BASE}/{ut['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{UT_BASE}/{ut['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_ut_update(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.patch(f"{UT_BASE}/{ut['id']}", json={"uraian": "Uraian sudah diperbarui"})
    assert r.status_code == 200
    assert r.json()["uraian"] == "Uraian sudah diperbarui"


def test_ut_delete(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    assert client.delete(f"{UT_BASE}/{ut['id']}").status_code == 204
    assert client.get(f"{UT_BASE}/{ut['id']}").status_code == 404


def test_ut_not_found(client: TestClient) -> None:
    assert client.get(f"{UT_BASE}/ut_tidakada").status_code == 404


def test_ut_search_by_tugas_pokok(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["tugas_pokok_id", "=", tp["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == ut["id"] for it in body["items"])


def test_ut_search_by_detil_tugas(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["detil_tugas_id", "=", dt["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == ut["id"] for it in body["items"])


def test_ut_search_by_kode(client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", ut["kode"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == ut["id"]


def test_ut_jabatan_id_eksplisit(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    """jabatan_id pada UraianTugas harus sama dengan yang dikirim saat create."""
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    assert ut["jabatan_id"] == jbt_id


def test_ut_seeded_data_via_catalog_endpoint(client: TestClient) -> None:
    """Pastikan catalog masih bisa diakses setelah seeding."""
    kombis = client.get(CATALOG_BASE + "/kombinasi").json()
    assert len(kombis) > 0
    first = kombis[0]
    jabatan_id = first["jabatan_id"]
    unit = first["unit"]
    # jabatan_nama harus diisi dengan nama jabatan yang sebenarnya, bukan jabatan_id
    assert "jabatan_nama" in first
    assert isinstance(first["jabatan_nama"], str)
    assert len(first["jabatan_nama"]) > 0
    assert first["jabatan_nama"] != jabatan_id

    r = client.get(CATALOG_BASE, params={"unit": unit, "jabatan_id": jabatan_id})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == unit for it in items)
    assert all(it["jabatan_id"] == jabatan_id for it in items)


def test_seeded_catalog_membawa_nilai_standar_calhr(client: TestClient) -> None:
    """Regresi: seed_catalog_models sempat tidak meneruskan field std_* ke DB sama
    sekali (CatalogItem/UraianTugasCreate tanpa std_*) walau task_catalog.json
    berisi nilainya — kolom std_* jadi NULL untuk semua baris seed meski JSON
    sumbernya lengkap. Pastikan item catalog hasil seed benar-benar membawa
    nilai standar, bukan hanya item yang dibuat langsung lewat API.
    """
    kombis = client.get(CATALOG_BASE + "/kombinasi").json()
    assert len(kombis) > 0
    first = kombis[0]
    r = client.get(CATALOG_BASE, params={"unit": first["unit"], "jabatan_id": first["jabatan_id"]})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert any(it["std_va_type"] is not None for it in items)
    assert any(it["std_sumber_bukti"] is not None for it in items)
    assert any(it["std_kondisi"] is not None for it in items)
    assert any(it["std_frekuensi_teks"] is not None for it in items)
    assert any(it["std_durasi_per_kali"] is not None for it in items)


def test_catalog_with_null_detil_tugas(client: TestClient) -> None:
    """Catalog untuk kombinasi yang punya task tanpa detil_tugas (detil_tugas_id=None) harus 200."""
    kombis = client.get(CATALOG_BASE + "/kombinasi").json()
    for kombi in kombis:
        r = client.get(
            CATALOG_BASE, params={"unit": kombi["unit"], "jabatan_id": kombi["jabatan_id"]}
        )
        assert r.status_code == 200
        items = r.json()
        if any(it["detil_tugas_id"] is None for it in items):
            return
    pytest.skip("Tidak ada task dengan detil_tugas_id=None dalam catalog")


def test_tp_list_large_limit(client: TestClient) -> None:
    """Limit hingga 500 harus diterima (le=500 di pagination_params)."""
    r = client.get(TP_BASE, params={"limit": 200})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body


def test_ut_list_large_limit(client: TestClient) -> None:
    """Limit 500 harus diterima untuk uraian-tugas."""
    r = client.get(UT_BASE, params={"limit": 500})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body


# --------------------------------------------------------------------------- #
# UraianTugas — nilai standar CalHR (std_*)
# --------------------------------------------------------------------------- #

_STD_PAYLOAD = {
    "std_sumber_bukti": "Aktual",
    "std_kondisi": "Baseline",
    "std_frekuensi_teks": "Mingguan",
    "std_durasi_per_kali": "60 menit",
    "std_jam_per_minggu": 2.5,
    "std_peak4w_hours": 4.0,
    "std_ai_mode": "Human-led",
    "std_va_type": "VA-Core",
    "std_dcs_flag": False,
}


def test_create_uraian_tugas_dengan_std(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    kode = f"TI{_uniq()}"
    payload = {
        "kode": kode,
        "uraian": f"Uraian tugas {kode}",
        "unit": "TK",
        "urutan": 1,
        "detil_tugas_id": dt["id"],
        "tugas_pokok_id": tp["id"],
        "jabatan_id": jbt_id,
        **_STD_PAYLOAD,
    }
    r = client.post(UT_BASE, json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    for key, value in _STD_PAYLOAD.items():
        assert body[key] == value

    r2 = client.get(f"{UT_BASE}/{body['id']}")
    assert r2.status_code == 200
    for key, value in _STD_PAYLOAD.items():
        assert r2.json()[key] == value


def test_create_uraian_tugas_tanpa_std(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    for key in _STD_PAYLOAD:
        assert ut[key] is None


def test_update_uraian_tugas_std(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    ut = _create_ut(client, dt["id"], tp["id"], jbt_id)
    r = client.patch(f"{UT_BASE}/{ut['id']}", json={"std_jam_per_minggu": 3.0})
    assert r.status_code == 200
    body = r.json()
    assert body["std_jam_per_minggu"] == 3.0
    # Field lain tidak berubah.
    assert body["std_sumber_bukti"] is None
    assert body["uraian"] == ut["uraian"]
    assert body["kode"] == ut["kode"]


def test_uraian_tugas_std_invalid_enum(
    client: TestClient, tp_dt_jbt_for_ut: tuple[dict, dict, str]
) -> None:
    tp, dt, jbt_id = tp_dt_jbt_for_ut
    kode = f"TI{_uniq()}"
    payload = {
        "kode": kode,
        "uraian": f"Uraian tugas {kode}",
        "unit": "TK",
        "urutan": 1,
        "detil_tugas_id": dt["id"],
        "tugas_pokok_id": tp["id"],
        "jabatan_id": jbt_id,
        "std_ai_mode": "Ngawur",
    }
    r = client.post(UT_BASE, json=payload)
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Purge & reseed katalog master (admin)
# --------------------------------------------------------------------------- #

SESI_BASE = "/api/v1/task-inventory/sesi"


def test_purge_forbidden_non_admin(client_as) -> None:
    non_admin = client_as("bukan-admin", groups=["partisipan"])
    r = non_admin.post(f"{CATALOG_BASE}/purge")
    assert r.status_code == 403


def test_purge_blocked_when_sesi_exists(client: TestClient) -> None:
    kombis = client.get(f"{CATALOG_BASE}/kombinasi").json()
    assert kombis, "Katalog kosong — tidak dapat menyiapkan sesi untuk test ini"
    jabatan_id = kombis[0]["jabatan_id"]
    r = client.post(
        SESI_BASE,
        json={
            "jabatan_id": jabatan_id,
            "periode": "2099-01",
            "min_responden": 1,
            "max_responden": 10,
        },
    )
    assert r.status_code == 201, r.text

    r2 = client.post(f"{CATALOG_BASE}/purge")
    assert r2.status_code == 409


def test_purge_reseed_round_trip(client: TestClient) -> None:
    r = client.get(UT_BASE, params={"limit": 1})
    assert r.status_code == 200
    total_awal = r.json()["total"]
    assert total_awal > 0

    r_purge = client.post(f"{CATALOG_BASE}/purge")
    assert r_purge.status_code == 200, r_purge.text
    deleted = r_purge.json()["deleted"]
    assert deleted["uraian_tugas"] == total_awal

    r_after_purge = client.get(UT_BASE, params={"limit": 1})
    assert r_after_purge.json()["total"] == 0

    r_reseed = client.post(f"{CATALOG_BASE}/reseed")
    assert r_reseed.status_code == 200, r_reseed.text
    created = r_reseed.json()["created"]
    assert created["uraian_tugas"] == total_awal

    r_after_reseed = client.get(UT_BASE, params={"limit": 1})
    assert r_after_reseed.json()["total"] == total_awal
