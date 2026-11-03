"""Test kunci optimistik (If-Match/ETag) dan Idempotency-Key rute tulis OPM & Task Inventory."""

from __future__ import annotations

import pytest
from _opm_common import (
    SME_BASE,
    TI_SESI,
    _buat_partisipan,
    _setup_jabatan_panel_ti,
    _uniq_periode,
)
from fastapi.testclient import TestClient

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.services.idempotency_sql import SqlIdempotencyStore

OPM_SESI = "/api/v1/opm/sesi"


def _bulk_jawaban(kodes: list[str]) -> dict:
    return {
        "jawaban": [
            {"task_kode": k, "importance": 4, "frequency": 3, "criticality": 5} for k in kodes
        ]
    }


def _buat_opm_sesi(client: TestClient, jabatan_id: str) -> tuple[dict, dict]:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id)
    r = client.post(
        OPM_SESI,
        json={
            "jabatan_id": jabatan_id,
            "ti_sesi_id": ctx["ti_sesi_id"],
            "periode": _uniq_periode(),
            "min_responden": 1,
            "max_responden": 10,
        },
    )
    assert r.status_code == 201, r.text
    return r.json(), ctx


def _wajib_if_match(app):
    app.dependency_overrides[get_settings] = lambda: Settings(
        docs_enabled=True, cors_origins=[], allowed_hosts=["*"], require_if_match=True
    )


# --- OPM: sesi ----------------------------------------------------------------


def test_opm_sesi_get_etag_patch_if_match_dan_usang_412(
    client: TestClient, jabatan_id_tk: str
) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    url = f"{OPM_SESI}/{sesi['id']}"
    etag = client.get(url).headers["etag"]

    ok = client.patch(url, json={"catatan": "A"}, headers={"If-Match": etag})
    assert ok.status_code == 200
    assert ok.headers["etag"] and ok.headers["etag"] != etag
    assert ok.headers["etag"] == client.get(url).headers["etag"]

    usang = client.patch(url, json={"catatan": "B"}, headers={"If-Match": etag})
    assert usang.status_code == 412
    assert client.get(url).json()["catatan"] == "A"


def test_opm_sesi_delete_if_match_usang_412_sesi_tetap(
    client: TestClient, jabatan_id_tk: str
) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    url = f"{OPM_SESI}/{sesi['id']}"
    etag = client.get(url).headers["etag"]
    client.patch(url, json={"catatan": "berubah"})
    assert client.delete(url, headers={"If-Match": etag}).status_code == 412
    assert client.get(url).status_code == 200
    assert (
        client.delete(url, headers={"If-Match": client.get(url).headers["etag"]}).status_code == 204
    )


def test_opm_sesi_require_if_match_428_dan_tanpa_header_default_lolos(
    app, client: TestClient, jabatan_id_tk: str
) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    url = f"{OPM_SESI}/{sesi['id']}"
    # Default (REQUIRE_IF_MATCH=false): tanpa header berperilaku seperti sebelumnya.
    assert client.patch(url, json={"catatan": "bebas"}).status_code == 200
    _wajib_if_match(app)
    try:
        assert client.patch(url, json={"catatan": "x"}).status_code == 428
        assert client.delete(url).status_code == 428
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_opm_sesi_buka_idempoten_dengan_key_sama(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    url = f"{OPM_SESI}/{sesi['id']}/buka"
    h = {"Idempotency-Key": "buka-1"}
    r1 = client.post(url, headers=h)
    r2 = client.post(url, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    # Tanpa key, pengulangan ditolak oleh state machine (perilaku lama tak berubah).
    assert client.post(url).status_code == 422


# --- OPM: responden & jawaban --------------------------------------------------


def test_opm_responden_bulk_dua_kali_key_sama_satu_set(
    client: TestClient, jabatan_id_tk: str
) -> None:
    sesi, ctx = _buat_opm_sesi(client, jabatan_id_tk)
    base = f"{OPM_SESI}/{sesi['id']}/responden"
    par = ctx["partisipan_ids"][0]
    sebelum = client.get(base).json()["total"]
    h = {"Idempotency-Key": "bulk-1"}
    r1 = client.post(f"{base}/bulk", json={"partisipan_ids": [par]}, headers=h)
    r2 = client.post(f"{base}/bulk", json={"partisipan_ids": [par]}, headers=h)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert client.get(base).json()["total"] == sebelum


def test_opm_responden_delete_if_match_usang_412(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    rid = client.get(f"{OPM_SESI}/{sesi['id']}/responden").json()["items"][0]["id"]
    url = f"{OPM_SESI}/responden/{rid}"
    etag = client.get(url).headers["etag"]
    assert client.delete(url, headers={"If-Match": '"usang"'}).status_code == 412
    assert client.get(url).status_code == 200
    assert client.delete(url, headers={"If-Match": etag}).status_code == 204


def test_opm_jawaban_put_if_match_usang_412_data_tak_berubah(
    client: TestClient, jabatan_id_tk: str
) -> None:
    sesi, ctx = _buat_opm_sesi(client, jabatan_id_tk)
    assert client.post(f"{OPM_SESI}/{sesi['id']}/buka").status_code == 200
    rid = client.get(f"{OPM_SESI}/{sesi['id']}/responden").json()["items"][0]["id"]
    url = f"{OPM_SESI}/responden/{rid}/jawaban"

    etag0 = client.get(url).headers["etag"]
    r1 = client.put(url, json=_bulk_jawaban(ctx["kodes"]), headers={"If-Match": etag0})
    assert r1.status_code == 200
    assert r1.headers["etag"] == client.get(url).headers["etag"] != etag0

    sebelum = client.get(url).json()
    usang = client.put(
        url,
        json={"jawaban": [{"task_kode": ctx["kodes"][0], "importance": 1}]},
        headers={"If-Match": etag0},
    )
    assert usang.status_code == 412
    assert client.get(url).json() == sebelum


def test_opm_jawaban_submit_idempoten_efek_sekali(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _buat_opm_sesi(client, jabatan_id_tk)
    client.post(f"{OPM_SESI}/{sesi['id']}/buka")
    rid = client.get(f"{OPM_SESI}/{sesi['id']}/responden").json()["items"][0]["id"]
    client.put(f"{OPM_SESI}/responden/{rid}/jawaban", json=_bulk_jawaban(ctx["kodes"]))
    url = f"{OPM_SESI}/responden/{rid}/jawaban/submit"
    h = {"Idempotency-Key": "submit-1"}
    r1 = client.post(url, headers=h)
    r2 = client.post(url, headers=h)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json() == r2.json()
    # Tanpa key: pengulangan ditolak karena sudah submit (perilaku lama).
    assert client.post(url).status_code == 422


def test_opm_search_tidak_menuntut_header_baru(app, client: TestClient, jabatan_id_tk: str) -> None:
    _wajib_if_match(app)
    try:
        r = client.post(f"{OPM_SESI}/search", json={"domain": []})
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert r.status_code == 200


def test_opm_key_sama_masih_diproses_409(
    client: TestClient, db_session, jabatan_id_tk: str
) -> None:
    sesi, _ = _buat_opm_sesi(client, jabatan_id_tk)
    url = f"{OPM_SESI}/{sesi['id']}/buka"
    assert SqlIdempotencyStore(db_session).reserve(f"POST:{url}:sibuk")
    r = client.post(url, headers={"Idempotency-Key": "sibuk"})
    assert r.status_code == 409


# --- Task Inventory -------------------------------------------------------------


def test_ti_sesi_patch_if_match_usang_412_dan_428(
    app, client: TestClient, jabatan_id_tk: str
) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    url = f"{TI_SESI}/{ctx['ti_sesi_id']}"
    etag = client.get(url).headers["etag"]
    # sesi sudah TAHAP3 -> PATCH selain koordinator 422, tapi If-Match diperiksa lebih dulu.
    assert (
        client.patch(url, json={"cabang": "Bandung"}, headers={"If-Match": '"usang"'}).status_code
        == 412
    )
    assert client.patch(url, json={}, headers={"If-Match": etag}).status_code != 412
    _wajib_if_match(app)
    try:
        assert client.patch(url, json={}).status_code == 428
        assert client.delete(url).status_code == 428
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_ti_responden_delete_dengan_etag_valid_204(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    rid = ctx["ti_responden_ids"][0]
    url = f"{TI_SESI}/responden/{rid}"
    etag = client.get(url).headers["etag"]
    assert client.delete(url, headers={"If-Match": '"usang"'}).status_code == 412
    assert client.get(url).status_code == 200
    # ETag valid lolos pemeriksaan If-Match (hasil akhir ditentukan aturan "sudah submit").
    assert client.delete(url, headers={"If-Match": etag}).status_code != 412


def test_ti_responden_bulk_key_sama_satu_set(client: TestClient, jabatan_id_tk: str) -> None:
    par = _buat_partisipan(client, jabatan_id_tk, "D")
    panel = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk}).json()
    client.post(f"{SME_BASE}/{panel['id']}/anggota", json={"partisipan_id": par})
    sesi = client.post(TI_SESI, json={"jabatan_id": jabatan_id_tk, "cabang": "Bandung"}).json()
    base = f"{TI_SESI}/{sesi['id']}/responden"
    awal = client.get(base).json()["total"]
    par2 = _buat_partisipan(client, jabatan_id_tk, "E")
    client.post(f"{SME_BASE}/{panel['id']}/anggota", json={"partisipan_id": par2})
    h = {"Idempotency-Key": "ti-bulk"}
    r1 = client.post(f"{base}/bulk", json={"partisipan_ids": [par2]}, headers=h)
    r2 = client.post(f"{base}/bulk", json={"partisipan_ids": [par2]}, headers=h)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert client.get(base).json()["total"] == awal + 1


def test_ti_detail_put_if_match_usang_412_dan_seleksi_submit_idempoten(
    client: TestClient, jabatan_id_tk: str
) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    rid = ctx["ti_responden_ids"][0]
    url = f"{TI_SESI}/responden/{rid}/detail"
    etag0 = client.get(url).headers["etag"]
    item = {"task_kode": ctx["kodes"][0], "jam_per_minggu": 2.0}
    ok = client.put(url, json={"detail": [item]}, headers={"If-Match": etag0})
    assert ok.status_code == 200
    etag1 = ok.headers["etag"]
    assert etag1 != etag0 and etag1 == client.get(url).headers["etag"]

    sebelum = client.get(url).json()
    usang = client.put(
        url, json={"detail": [{**item, "jam_per_minggu": 9.0}]}, headers={"If-Match": etag0}
    )
    assert usang.status_code == 412
    assert client.get(url).json() == sebelum

    # Seleksi: GET memberi ETag; PUT usang -> 412 (If-Match diperiksa sebelum cek status sesi).
    surl = f"{TI_SESI}/responden/{rid}/seleksi"
    setag = client.get(surl).headers["etag"]
    assert (
        client.put(surl, json={"task_kode": ctx["kodes"]}, headers={"If-Match": '"x"'}).status_code
        == 412
    )
    assert setag


def test_ti_seleksi_submit_dan_mulai_tahap_idempoten(
    client: TestClient, jabatan_id_tk: str
) -> None:
    par = _buat_partisipan(client, jabatan_id_tk, "F")
    cat = client.get(
        "/api/v1/task-inventory/catalog", params={"unit": "ALL", "jabatan_id": jabatan_id_tk}
    ).json()["items"]
    kodes = [c["kode"] for c in cat[:2]]
    panel = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk}).json()
    client.post(f"{SME_BASE}/{panel['id']}/anggota", json={"partisipan_id": par})
    sesi = client.post(TI_SESI, json={"jabatan_id": jabatan_id_tk, "cabang": "Bandung"}).json()
    sid = sesi["id"]
    h1 = {"Idempotency-Key": "mt1"}
    a = client.post(f"{TI_SESI}/{sid}/mulai-tahap1", headers=h1)
    b = client.post(f"{TI_SESI}/{sid}/mulai-tahap1", headers=h1)
    assert a.status_code == 200 and b.status_code == 200 and a.json() == b.json()

    rid = client.get(f"{TI_SESI}/{sid}/responden").json()["items"][0]["id"]
    client.put(f"{TI_SESI}/responden/{rid}/seleksi", json={"task_kode": kodes})
    h2 = {"Idempotency-Key": "sub1"}
    s1 = client.post(f"{TI_SESI}/responden/{rid}/seleksi/submit", headers=h2)
    s2 = client.post(f"{TI_SESI}/responden/{rid}/seleksi/submit", headers=h2)
    assert s1.status_code == 201 and s2.status_code == 200 and s1.json() == s2.json()
    assert client.post(f"{TI_SESI}/responden/{rid}/seleksi/submit").status_code == 422


@pytest.mark.parametrize("path", ["/api/v1/task-inventory/sesi/search", f"{OPM_SESI}/search"])
def test_search_tidak_menuntut_header_baru(app, client: TestClient, path: str) -> None:
    _wajib_if_match(app)
    try:
        assert client.post(path, json={"domain": []}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)
