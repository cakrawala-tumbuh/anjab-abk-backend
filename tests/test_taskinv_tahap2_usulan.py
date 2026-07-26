"""Test review Tahap 2 & materialisasi usulan Tahap 1 (backlog #27).

Cakupan: `GET/POST /sesi/{id}/tahap2` menampilkan & memutuskan usulan bersama task
partial, dan `POST /sesi/{id}/mulai-tahap3` memateralisasikan usulan disetujui
menjadi baris katalog `ti_uraian_tugas` berkode `TIU...`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/task-inventory"
SESI = f"{BASE}/sesi"
UT_BASE = f"{BASE}/uraian-tugas"
TP_BASE = f"{BASE}/tugas-pokok"
DT_BASE = f"{BASE}/detil-tugas"
JABATAN_BASE = "/api/v1/jabatan"
UNIT = "ALL"


# --------------------------------------------------------------------------- #
# Helpers (mengikuti pola test_taskinv.py & test_taskinv_usulan.py)
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


def _create_tp(client: TestClient, jabatan_ids: list[str], nama: str | None = None) -> dict:
    payload = {"jabatan_ids": jabatan_ids, "nama": nama or f"Tugas Pokok {_uniq()}"}
    r = client.post(TP_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_dt(
    client: TestClient, tugas_pokok_id: str, jabatan_ids: list[str], nama: str | None = None
) -> dict:
    payload = {
        "nama": nama or f"Detil Tugas {_uniq()}",
        "tugas_pokok_id": tugas_pokok_id,
        "jabatan_ids": jabatan_ids,
    }
    r = client.post(DT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_sesi(client: TestClient, jabatan_id: str, **over) -> dict:
    payload = {"jabatan_id": jabatan_id, "cabang": "Bandung"}
    payload.update(over)
    r = client.post(SESI, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _add_responden(client: TestClient, sesi_id: str, **over) -> dict:
    payload = {"nama": "Responden"}
    payload.update(over)
    r = client.post(f"{SESI}/{sesi_id}/responden", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _catalog_kodes(client: TestClient, jabatan_id: str, n: int, unit: str = UNIT) -> list[str]:
    r = client.get(BASE + "/catalog", params={"unit": unit, "jabatan_id": jabatan_id})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= n
    return [it["kode"] for it in items[:n]]


def _seleksi_submit(client: TestClient, responden_id: str, kodes: list[str]) -> None:
    r = client.put(f"{SESI}/responden/{responden_id}/seleksi", json={"task_kode": kodes})
    assert r.status_code == 200, r.text
    r2 = client.post(f"{SESI}/responden/{responden_id}/seleksi/submit")
    assert r2.status_code == 201, r2.text


def _create_usulan(
    client: TestClient,
    responden_id: str,
    tugas_pokok_id: str,
    detil_tugas_id: str | None,
    uraian: str,
) -> dict:
    payload = {"tugas_pokok_id": tugas_pokok_id, "uraian": uraian}
    if detil_tugas_id is not None:
        payload["detil_tugas_id"] = detil_tugas_id
    r = client.post(f"{SESI}/responden/{responden_id}/usulan", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _tp_dt_for_jabatan(client: TestClient, jabatan_id: str) -> tuple[str, str]:
    tp = _create_tp(client, jabatan_ids=[jabatan_id])
    dt = _create_dt(client, tp["id"], jabatan_ids=[jabatan_id])
    return tp["id"], dt["id"]


@pytest.fixture
def tp_dt(client: TestClient, jabatan_id_tk: str) -> tuple[str, str]:
    return _tp_dt_for_jabatan(client, jabatan_id_tk)


# --------------------------------------------------------------------------- #
# GET tahap2: usulan muncul & ikut dihitung jumlah_belum_diputuskan
# --------------------------------------------------------------------------- #


def test_tahap2_get_review_includes_usulan(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kode = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, nama="A")
    rb = _add_responden(client, sid, nama="B")

    usulan_a = _create_usulan(client, ra["id"], tp_id, dt_id, "Usulan dari A.")
    usulan_b = _create_usulan(client, rb["id"], tp_id, None, "Usulan dari B.")

    # Sama-sama pilih kode yang sama -> unanimous, tidak ada task partial.
    _seleksi_submit(client, ra["id"], [kode])
    _seleksi_submit(client, rb["id"], [kode])

    r2 = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r2.status_code == 200, r2.text

    rv = client.get(f"{SESI}/{sid}/tahap2")
    assert rv.status_code == 200, rv.text
    review = rv.json()
    assert review["tasks"] == []
    usulan_ids = {u["usulan_id"] for u in review["usulan"]}
    assert {usulan_a["id"], usulan_b["id"]} == usulan_ids
    assert all(u["disetujui"] is None for u in review["usulan"])
    # responden_nama ter-resolve (bukan None) untuk responden yang diberi nama.
    by_id = {u["usulan_id"]: u for u in review["usulan"]}
    assert by_id[usulan_a["id"]]["responden_nama"] == "A"
    assert by_id[usulan_a["id"]]["tugas_pokok"]
    assert by_id[usulan_a["id"]]["detil_tugas"]
    assert by_id[usulan_b["id"]]["detil_tugas"] is None
    # jumlah_belum_diputuskan = 0 task partial + 2 usulan belum diputuskan.
    assert review["jumlah_belum_diputuskan"] == 2


# --------------------------------------------------------------------------- #
# POST tahap2: submit keputusan usulan + materialisasi di mulai-tahap3
# --------------------------------------------------------------------------- #


def test_tahap2_submit_dan_materialize_usulan_disetujui(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kode = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    baseline_total = client.get(
        BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk}
    ).json()["total"]

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    rsp = _add_responden(client, sid, nama="A")
    usulan_setuju = _create_usulan(client, rsp["id"], tp_id, dt_id, "Usulan yang disetujui.")
    usulan_tolak = _create_usulan(client, rsp["id"], tp_id, dt_id, "Usulan yang ditolak.")
    _seleksi_submit(client, rsp["id"], [kode])

    r2 = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r2.status_code == 200, r2.text

    rk = client.post(
        f"{SESI}/{sid}/tahap2",
        json={
            "keputusan": [],
            "keputusan_usulan": [
                {"usulan_id": usulan_setuju["id"], "disetujui": True},
                {"usulan_id": usulan_tolak["id"], "disetujui": False},
            ],
        },
    )
    assert rk.status_code == 200, rk.text
    body = rk.json()
    by_id = {u["usulan_id"]: u for u in body["usulan"]}
    assert by_id[usulan_setuju["id"]]["disetujui"] is True
    assert by_id[usulan_tolak["id"]]["disetujui"] is False

    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "TAHAP3"

    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200
    terpilih_kodes = {t["kode"] for t in tt.json()["items"]}
    tiu_kodes = {k for k in terpilih_kodes if k.startswith("TIU")}
    assert len(tiu_kodes) == 1

    after_total = client.get(
        BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk}
    ).json()["total"]
    assert after_total == baseline_total + 1

    usulan_list = client.get(f"{SESI}/responden/{rsp['id']}/usulan").json()
    by_usulan_id = {u["id"]: u for u in usulan_list}
    assert by_usulan_id[usulan_setuju["id"]]["task_kode"] in tiu_kodes
    assert by_usulan_id[usulan_tolak["id"]]["task_kode"] is None


def test_tahap2_submit_kedua_daftar_kosong_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kode = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    rsp = _add_responden(client, sid, nama="A")
    _seleksi_submit(client, rsp["id"], [kode])
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    r = client.post(f"{SESI}/{sid}/tahap2", json={"keputusan": [], "keputusan_usulan": []})
    assert r.status_code == 422, r.text


def test_tahap2_submit_usulan_id_sesi_lain_422(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    kode = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    sesi_a = _create_sesi(client, jabatan_id_tk, cabang="Bandung")
    sesi_b = _create_sesi(client, jabatan_id_tk, cabang="Semarang")

    client.post(f"{SESI}/{sesi_a['id']}/mulai-tahap1")
    client.post(f"{SESI}/{sesi_b['id']}/mulai-tahap1")
    rsp_a = _add_responden(client, sesi_a["id"], nama="A")
    rsp_b = _add_responden(client, sesi_b["id"], nama="B")
    usulan_a = _create_usulan(client, rsp_a["id"], tp_id, dt_id, "Usulan sesi A.")
    usulan_b = _create_usulan(client, rsp_b["id"], tp_id, dt_id, "Usulan sesi B.")
    _seleksi_submit(client, rsp_a["id"], [kode])
    _seleksi_submit(client, rsp_b["id"], [kode])
    client.post(f"{SESI}/{sesi_a['id']}/mulai-tahap2")
    client.post(f"{SESI}/{sesi_b['id']}/mulai-tahap2")

    r = client.post(
        f"{SESI}/{sesi_a['id']}/tahap2",
        json={
            "keputusan": [],
            "keputusan_usulan": [{"usulan_id": usulan_b["id"], "disetujui": True}],
        },
    )
    assert r.status_code == 422, r.text

    # Tidak ada keputusan yang tersimpan untuk usulan sesi A sendiri.
    rv = client.get(f"{SESI}/{sesi_a['id']}/tahap2")
    by_id = {u["usulan_id"]: u for u in rv.json()["usulan"]}
    assert by_id[usulan_a["id"]]["disetujui"] is None

    # Keputusan usulan sesi B pun tidak ikut tersimpan.
    rv_b = client.get(f"{SESI}/{sesi_b['id']}/tahap2")
    by_id_b = {u["usulan_id"]: u for u in rv_b.json()["usulan"]}
    assert by_id_b[usulan_b["id"]]["disetujui"] is None


def test_mulai_tahap3_usulan_tanpa_baris_katalog_422(client: TestClient) -> None:
    """Jabatan tanpa satu pun baris katalog saat materialisasi -> 422, sesi tetap TAHAP2."""
    jbt = _create_jabatan(client)
    tp = _create_tp(client, jabatan_ids=[jbt["id"]])

    # Satu baris katalog placeholder — WAJIB ada agar POST /sesi lolos validasi
    # `valid_kodes_for_jabatan`, lalu dihapus sebelum mulai-tahap3.
    placeholder = client.post(
        UT_BASE,
        json={
            "kode": _uniq("TIX"),
            "uraian": "Placeholder.",
            "unit": "ZZ",
            "urutan": 1,
            "jabatan_id": jbt["id"],
            "tugas_pokok_id": tp["id"],
        },
    )
    assert placeholder.status_code == 201, placeholder.text
    placeholder_kode = placeholder.json()["kode"]
    placeholder_id = placeholder.json()["id"]

    sesi = _create_sesi(client, jbt["id"])
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    rsp = _add_responden(client, sid, nama="A")
    usulan = _create_usulan(client, rsp["id"], tp["id"], None, "Usulan tanpa unit diturunkan.")
    _seleksi_submit(client, rsp["id"], [placeholder_kode])

    r2 = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r2.status_code == 200, r2.text

    rk = client.post(
        f"{SESI}/{sid}/tahap2",
        json={
            "keputusan": [],
            "keputusan_usulan": [{"usulan_id": usulan["id"], "disetujui": True}],
        },
    )
    assert rk.status_code == 200, rk.text

    # Hapus satu-satunya baris katalog jabatan ini -> unit tak dapat diturunkan.
    r_del = client.delete(f"{UT_BASE}/{placeholder_id}")
    assert r_del.status_code == 204

    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 422, r3.text

    r_sesi = client.get(f"{SESI}/{sid}")
    assert r_sesi.json()["status"] == "TAHAP2"

    r_catalog = client.get(BASE + "/catalog", params={"unit": "ZZ", "jabatan_id": jbt["id"]})
    assert r_catalog.json()["total"] == 0

    usulan_list = client.get(f"{SESI}/responden/{rsp['id']}/usulan").json()
    assert usulan_list[0]["task_kode"] is None


def test_materialize_approved_idempotent_tidak_menggandakan(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str], db_session
) -> None:
    """Memanggil `materialize_approved` ulang tidak menggandakan baris katalog.

    `mulai-tahap3` tidak bisa dipanggil dua kali lewat HTTP (endpoint menolak sesi
    yang sudah TAHAP3), jadi idempotensi diverifikasi langsung di lapisan seam,
    memakai `db_session` (sesi yang sama dengan `client`, lihat conftest.py).
    """
    from anjab_abk_backend.taskinv.services.detil_tugas_sql import SqlDetilTugasService
    from anjab_abk_backend.taskinv.services.tugas_pokok_sql import SqlTugasPokokService
    from anjab_abk_backend.taskinv.services.usulan_sql import SqlTiUsulanService

    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kode = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    baseline_total = client.get(
        BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk}
    ).json()["total"]

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    rsp = _add_responden(client, sid, nama="A")
    usulan = _create_usulan(client, rsp["id"], tp_id, dt_id, "Usulan idempotensi.")
    _seleksi_submit(client, rsp["id"], [kode])
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(
        f"{SESI}/{sid}/tahap2",
        json={
            "keputusan": [],
            "keputusan_usulan": [{"usulan_id": usulan["id"], "disetujui": True}],
        },
    )
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text

    after_total = client.get(
        BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk}
    ).json()["total"]
    assert after_total == baseline_total + 1

    svc = SqlTiUsulanService(
        db_session,
        tp_svc=SqlTugasPokokService(db_session),
        dt_svc=SqlDetilTugasService(db_session),
    )
    kodes_lagi = svc.materialize_approved(sid, jabatan_id_tk)
    assert len(kodes_lagi) == 1

    after_total_lagi = client.get(
        BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk}
    ).json()["total"]
    assert after_total_lagi == baseline_total + 1
