"""Tes sumber narasi (`narasi_sumber`): simpan teks tak berubah, hash, jenis, izin, otorisasi."""

from __future__ import annotations

import hashlib
import logging

URL = "/api/v1/narasi/sumber"


def _tim(client_as, subject: str = "tim-narasi"):
    return client_as(subject, groups=["tim-kajian"])


def _body(**ubah) -> dict:
    body = {
        "judul": "Pedoman akademik",
        "jenis": "SINTETIS",
        "versi": "v1",
        "periode": "2026/27",
        "teks": "Isi sumber ✓ tempelan.",
        "izin_ai": False,
        "izin_catatan": None,
        "menggantikan_id": None,
    }
    body.update(ubah)
    return body


def test_buat_lalu_baca_hash_cocok_dan_pembuat_dari_token(client_as):
    c = _tim(client_as, "tim-satu")
    r = c.post(URL, json=_body(dibuat_oleh="orang-lain"))
    assert r.status_code == 422  # extra forbid: aktor tidak boleh dari body
    r = c.post(URL, json=_body())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["teks_hash"] == hashlib.sha256("Isi sumber ✓ tempelan.".encode()).hexdigest()
    assert d["dibuat_oleh"] == "tim-satu"
    assert len(d["id"]) == 36
    g = c.get(f"{URL}/{d['id']}")
    assert g.status_code == 200
    assert g.json()["teks"] == "Isi sumber ✓ tempelan."
    assert g.json()["teks_hash"] == d["teks_hash"]


def test_jenis_di_luar_daftar_422(client_as):
    c = _tim(client_as)
    assert c.post(URL, json=_body(jenis="WCP_JAWABAN")).status_code == 422


def test_teks_kosong_dan_terlalu_panjang_422(client_as):
    c = _tim(client_as)
    assert c.post(URL, json=_body(teks="")).status_code == 422
    assert c.post(URL, json=_body(teks="a" * 200_001)).status_code == 422
    assert c.post(URL, json=_body(teks="a" * 200_000)).status_code == 201


def test_izin_ai_tanpa_catatan_dan_menggantikan_tak_dikenal_422(client_as):
    c = _tim(client_as)
    assert c.post(URL, json=_body(izin_ai=True)).status_code == 422
    assert c.post(URL, json=_body(izin_ai=True, izin_catatan="  ")).status_code == 422
    ok = c.post(URL, json=_body(izin_ai=True, izin_catatan="Dokumen publik, izin tertulis."))
    assert ok.status_code == 201
    assert ok.json()["izin_ai"] is True
    r = c.post(URL, json=_body(menggantikan_id="tidak-ada"))
    assert r.status_code == 422


def test_revisi_dengan_menggantikan_id(client_as):
    c = _tim(client_as)
    lama = c.post(URL, json=_body()).json()
    baru = c.post(URL, json=_body(teks="revisi", menggantikan_id=lama["id"]))
    assert baru.status_code == 201
    assert baru.json()["menggantikan_id"] == lama["id"]
    assert baru.json()["teks_hash"] != lama["teks_hash"]


def test_list_dan_search_tanpa_teks_filter_dan_whitelist(client_as):
    c = _tim(client_as)
    c.post(URL, json=_body(periode="2031/32", judul="Alfa uniq"))
    c.post(URL, json=_body(periode="2031/32", jenis="DOKUMEN_RESMI", judul="Beta uniq"))
    lst = c.get(URL, params={"jenis": "DOKUMEN_RESMI", "periode": "2031/32"})
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1 and items[0]["judul"] == "Beta uniq"
    assert all("teks" not in i for i in items)
    s = c.post(f"{URL}/search", json={"domain": [["judul", "ilike", "uniq"]]})
    assert s.status_code == 200
    assert s.json()["total"] == 2
    assert all("teks" not in i for i in s.json()["items"])
    bad = c.post(f"{URL}/search", json={"domain": [["teks", "ilike", "x"]]})
    assert bad.status_code == 422
    bad2 = c.post(
        f"{URL}/search", json={"domain": [["judul", "=", "a"]], "order": [["teks", "asc"]]}
    )
    assert bad2.status_code == 422


def test_otorisasi(anon_client, client_as):
    sid = _tim(client_as).post(URL, json=_body()).json()["id"]
    assert anon_client.get(URL).status_code == 401
    assert anon_client.post(URL, json=_body()).status_code == 401
    for grup in (["admin"], ["sekolah-pengisi"]):
        c = client_as("non-tim", groups=grup)
        assert c.get(URL).status_code == 403
        assert c.get(f"{URL}/{sid}").status_code == 403
        assert c.post(URL, json=_body()).status_code == 403
        assert c.post(f"{URL}/search", json={}).status_code == 403
    assert _tim(client_as).get(f"{URL}/tidak-ada").status_code == 404


def test_tanpa_patch_dan_delete_di_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p, ops in paths.items():
        if p.startswith(URL):
            assert not ({"patch", "put", "delete"} & set(ops)), p


def test_teks_tidak_masuk_log(client_as, caplog):
    c = _tim(client_as)
    rahasia = "KALIMAT-RAHASIA-UNIK-12345"
    with caplog.at_level(logging.DEBUG):
        c.post(URL, json=_body(teks=rahasia))
        c.post(URL, json=_body(teks=rahasia, jenis="WCP_JAWABAN"))
        c.post(URL, json=_body(teks=rahasia, menggantikan_id="tidak-ada"))
    assert rahasia not in caplog.text


def test_keterangan_orang_201_dan_terfilter(client_as):
    c = _tim(client_as)
    r = c.post(URL, json=_body(jenis="KETERANGAN_ORANG", periode="2033/34", judul="Cerita uniq"))
    assert r.status_code == 201, r.text
    lst = c.get(URL, params={"jenis": "KETERANGAN_ORANG", "periode": "2033/34"})
    assert lst.status_code == 200
    assert r.json()["id"] in [x["id"] for x in lst.json()["items"]]
    assert c.post(URL, json=_body(jenis="ASLI_LAIN")).status_code == 422
