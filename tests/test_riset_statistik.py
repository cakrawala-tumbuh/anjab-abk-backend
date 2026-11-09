"""Tes statistik riset (`riset_statistik`): protokol terkunci, verifikasi independen, otorisasi."""

from __future__ import annotations

PROTOKOL = "/api/v1/riset/protokol"
STATISTIK = "/api/v1/riset/statistik"


def _tim(client_as, subject: str = "pengunggah"):
    """Client anggota `tim-kajian`; identitas terakhir yang dibuat berlaku untuk app."""
    return client_as(subject, groups=["tim-kajian"])


def _protokol(client_as, kode: str, *, kunci: bool = True) -> str:
    """Buat protokol (dan kunci bila diminta); kembalikan id-nya."""
    c = _tim(client_as, "penyusun-protokol")
    r = c.post(PROTOKOL, json={"kode": kode, "judul": "Protokol uji", "isi": "Isi protokol."})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if kunci:
        assert c.post(f"{PROTOKOL}/{pid}/kunci").status_code == 200
    return pid


def _body(**ubah) -> dict:
    body = {
        "nama_analisis": "Cronbach alpha DCS",
        "keluaran": "alpha = 0.81 ✓\nn = 42",
        "kode_sumber_ref": "analisis/dcs_alpha.py@3f2a9c1",
    }
    body.update(ubah)
    return body


def test_buat_draf_lalu_verifikasi_subjek_kedua_terverifikasi(client_as):
    pid = _protokol(client_as, "STAT-POS")
    r = _tim(client_as, "pengunggah").post(f"{PROTOKOL}/{pid}/statistik", json=_body())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "DRAF" and d["protokol_id"] == pid
    assert d["dibuat_oleh"] == "pengunggah"
    assert d["keluaran"] == _body()["keluaran"]
    assert d["diverifikasi_oleh"] is None and d["diverifikasi_pada"] is None
    assert len(d["id"]) == 36

    v = _tim(client_as, "pemverifikasi").post(f"{STATISTIK}/{d['id']}/verifikasi")
    assert v.status_code == 200, v.text
    dv = v.json()
    assert dv["status"] == "TERVERIFIKASI"
    assert dv["diverifikasi_oleh"] == "pemverifikasi" and dv["diverifikasi_pada"] is not None
    assert dv["dibuat_oleh"] == "pengunggah"


def test_get_filter_status_hanya_terverifikasi(client_as):
    pid = _protokol(client_as, "STAT-FILTER")
    c = _tim(client_as, "pengunggah")
    a = c.post(f"{PROTOKOL}/{pid}/statistik", json=_body(nama_analisis="A")).json()
    c.post(f"{PROTOKOL}/{pid}/statistik", json=_body(nama_analisis="B"))
    _tim(client_as, "pemverifikasi").post(f"{STATISTIK}/{a['id']}/verifikasi")

    c = _tim(client_as, "pembaca")
    semua = c.get(f"{PROTOKOL}/{pid}/statistik")
    assert semua.status_code == 200 and semua.json()["total"] == 2
    t = c.get(f"{PROTOKOL}/{pid}/statistik", params={"status": "TERVERIFIKASI"}).json()
    assert t["total"] == 1 and [i["id"] for i in t["items"]] == [a["id"]]
    assert all(i["status"] == "TERVERIFIKASI" for i in t["items"])
    dr = c.get(f"{PROTOKOL}/{pid}/statistik", params={"status": "DRAF"}).json()
    assert dr["total"] == 1 and dr["items"][0]["nama_analisis"] == "B"
    assert c.get(f"{PROTOKOL}/{pid}/statistik", params={"status": "BATAL"}).status_code == 422


def test_protokol_draf_409_dan_protokol_asing_404(client_as):
    draf = _protokol(client_as, "STAT-DRAF", kunci=False)
    c = _tim(client_as)
    r = c.post(f"{PROTOKOL}/{draf}/statistik", json=_body())
    assert r.status_code == 409
    assert r.json()["error"] == "PROTOKOL_BELUM_TERKUNCI"
    assert c.get(f"{PROTOKOL}/{draf}/statistik").json()["total"] == 0
    assert c.post(f"{PROTOKOL}/tidak-ada/statistik", json=_body()).status_code == 404
    assert c.get(f"{PROTOKOL}/tidak-ada/statistik").status_code == 404


def test_verifikasi_pengunggah_409_lalu_verifikasi_ulang_409(client_as):
    pid = _protokol(client_as, "STAT-INDEP")
    r = _tim(client_as, "pengunggah").post(f"{PROTOKOL}/{pid}/statistik", json=_body())
    sid = r.json()["id"]
    sendiri = _tim(client_as, "pengunggah").post(f"{STATISTIK}/{sid}/verifikasi")
    assert sendiri.status_code == 409
    assert sendiri.json()["error"] == "PEMVERIFIKASI_TIDAK_INDEPENDEN"
    daftar = _tim(client_as, "pengunggah").get(f"{PROTOKOL}/{pid}/statistik").json()
    assert daftar["items"][0]["status"] == "DRAF"

    assert _tim(client_as, "pemverifikasi").post(f"{STATISTIK}/{sid}/verifikasi").status_code == 200
    ulang = _tim(client_as, "pemverifikasi-lain").post(f"{STATISTIK}/{sid}/verifikasi")
    assert ulang.status_code == 409
    assert ulang.json()["error"] == "STATISTIK_SUDAH_TERVERIFIKASI"
    item = _tim(client_as, "pembaca").get(f"{PROTOKOL}/{pid}/statistik").json()["items"][0]
    assert item["diverifikasi_oleh"] == "pemverifikasi"
    assert _tim(client_as).post(f"{STATISTIK}/tidak-ada/verifikasi").status_code == 404


def test_validasi_422(client_as):
    pid = _protokol(client_as, "STAT-VALID")
    c = _tim(client_as)
    url = f"{PROTOKOL}/{pid}/statistik"
    assert c.post(url, json=_body(kode_sumber_ref="")).status_code == 422
    assert c.post(url, json=_body(kode_sumber_ref="   ")).status_code == 422
    assert c.post(url, json=_body(kode_sumber_ref="r" * 501)).status_code == 422
    body = _body()
    del body["kode_sumber_ref"]
    assert c.post(url, json=body).status_code == 422
    assert c.post(url, json=_body(keluaran="")).status_code == 422
    assert c.post(url, json=_body(keluaran="k" * 200_001)).status_code == 422
    assert c.post(url, json=_body(nama_analisis="")).status_code == 422
    assert c.post(url, json=_body(dibuat_oleh="orang-lain")).status_code == 422
    assert c.post(url, json=_body(status="TERVERIFIKASI")).status_code == 422
    assert c.post(url, json=_body(keluaran="k" * 200_000)).status_code == 201
    assert c.get(url).json()["total"] == 1


def test_otorisasi_tanpa_grup_tim_kajian(anon_client, client_as):
    pid = _protokol(client_as, "STAT-AUTH")
    sid = _tim(client_as).post(f"{PROTOKOL}/{pid}/statistik", json=_body()).json()["id"]
    assert anon_client.get(f"{PROTOKOL}/{pid}/statistik").status_code == 401
    assert anon_client.post(f"{PROTOKOL}/{pid}/statistik", json=_body()).status_code == 401
    assert anon_client.post(f"{STATISTIK}/{sid}/verifikasi").status_code == 401
    for grup in (["admin"], ["partisipan"]):
        c = client_as("bukan-tim", groups=grup)
        assert c.get(f"{PROTOKOL}/{pid}/statistik").status_code == 403
        assert c.post(f"{PROTOKOL}/{pid}/statistik", json=_body()).status_code == 403
        assert c.post(f"{STATISTIK}/{sid}/verifikasi").status_code == 403
    item = _tim(client_as, "pembaca").get(f"{PROTOKOL}/{pid}/statistik").json()["items"][0]
    assert item["status"] == "DRAF"


def test_openapi_tiga_endpoint_terdokumentasi_tanpa_sunting(client_as, client):
    pid = _protokol(client_as, "STAT-IMUT")
    sid = _tim(client_as).post(f"{PROTOKOL}/{pid}/statistik", json=_body()).json()["id"]
    c = _tim(client_as)
    assert c.patch(f"{STATISTIK}/{sid}", json={"keluaran": "x"}).status_code in (404, 405)
    assert c.delete(f"{STATISTIK}/{sid}").status_code in (404, 405)
    assert c.put(f"{PROTOKOL}/{pid}/statistik", json=_body()).status_code == 405

    paths = client.get("/openapi.json").json()["paths"]
    daftar = paths[f"{PROTOKOL}/{{protokol_id}}/statistik"]
    verif = paths[f"{STATISTIK}/{{statistik_id}}/verifikasi"]
    assert set(daftar) == {"get", "post"} and set(verif) == {"post"}
    assert not [p for p in paths if p.startswith(STATISTIK) and not p.endswith("/verifikasi")]
    for op in (daftar["get"], daftar["post"], verif["post"]):
        assert op["summary"] and op["tags"] == ["riset"]
        assert {"401", "403", "404"} <= set(op["responses"])
    assert {"409", "422"} <= set(daftar["post"]["responses"])
    assert "409" in verif["post"]["responses"]
