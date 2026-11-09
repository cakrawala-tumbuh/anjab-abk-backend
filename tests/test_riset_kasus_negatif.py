"""Tes kasus negatif riset (`riset_kasus_negatif`): protokol terkunci, append-only, otorisasi."""

from __future__ import annotations

PROTOKOL = "/api/v1/riset/protokol"


def _tim(client_as, subject: str = "pencatat"):
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
        "ringkasan": "Sekolah A ✓ beban tinggi tetapi skor DCS rendah.",
        "alasan_negatif": "Hipotesis memperkirakan beban tinggi menaikkan tuntutan kerja.",
        "sumber_ref": "statistik:abc",
    }
    body.update(ubah)
    return body


def _url(pid: str) -> str:
    return f"{PROTOKOL}/{pid}/kasus-negatif"


def test_buat_dua_kasus_lalu_get_urut_waktu(client_as):
    pid = _protokol(client_as, "KN-POS")
    c = _tim(client_as)
    r1 = c.post(_url(pid), json=_body(ringkasan="Kasus pertama"))
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    assert d1["protokol_id"] == pid and d1["dibuat_oleh"] == "pencatat"
    assert d1["sumber_ref"] == "statistik:abc" and len(d1["id"]) == 36
    tanpa_ref = _body(ringkasan="Kasus kedua")
    del tanpa_ref["sumber_ref"]
    r2 = c.post(_url(pid), json=tanpa_ref)
    assert r2.status_code == 201, r2.text
    assert r2.json()["sumber_ref"] is None

    g = _tim(client_as, "pembaca").get(_url(pid))
    assert g.status_code == 200
    d = g.json()
    assert d["total"] == 2
    assert [i["id"] for i in d["items"]] == [d1["id"], r2.json()["id"]]
    assert d["items"][0]["created_at"] <= d["items"][1]["created_at"]


def test_protokol_draf_409_dan_protokol_asing_404(client_as):
    draf = _protokol(client_as, "KN-DRAF", kunci=False)
    c = _tim(client_as)
    r = c.post(_url(draf), json=_body())
    assert r.status_code == 409
    assert r.json()["error"] == "PROTOKOL_BELUM_TERKUNCI"
    assert c.get(_url(draf)).json()["total"] == 0
    assert c.post(_url("tidak-ada"), json=_body()).status_code == 404
    assert c.get(_url("tidak-ada")).status_code == 404


def test_validasi_422(client_as):
    pid = _protokol(client_as, "KN-VALID")
    c = _tim(client_as)
    url = _url(pid)
    for field in ("ringkasan", "alasan_negatif"):
        assert c.post(url, json=_body(**{field: ""})).status_code == 422
        assert c.post(url, json=_body(**{field: "   "})).status_code == 422
        assert c.post(url, json=_body(**{field: "x" * 5_001})).status_code == 422
        body = _body()
        del body[field]
        assert c.post(url, json=body).status_code == 422
    assert c.post(url, json=_body(sumber_ref="r" * 501)).status_code == 422
    assert c.get(url).json()["total"] == 0
    batas = _body(ringkasan="x" * 5_000, alasan_negatif="y" * 5_000)
    assert c.post(url, json=batas).status_code == 201


def test_dibuat_oleh_di_body_diabaikan_nilai_dari_token(client_as):
    pid = _protokol(client_as, "KN-AKTOR")
    c = _tim(client_as, "subjek-token")
    r = c.post(_url(pid), json=_body(dibuat_oleh="orang-lain"))
    assert r.status_code == 201, r.text
    assert r.json()["dibuat_oleh"] == "subjek-token"
    items = c.get(_url(pid)).json()["items"]
    assert [i["dibuat_oleh"] for i in items] == ["subjek-token"]
    # Field asing lain tetap ditolak.
    assert c.post(_url(pid), json=_body(status="X")).status_code == 422


def test_otorisasi_tanpa_grup_tim_kajian(anon_client, client_as):
    pid = _protokol(client_as, "KN-AUTH")
    assert anon_client.get(_url(pid)).status_code == 401
    assert anon_client.post(_url(pid), json=_body()).status_code == 401
    for grup in (["admin"], ["partisipan"]):
        c = client_as("bukan-tim", groups=grup)
        assert c.get(_url(pid)).status_code == 403
        assert c.post(_url(pid), json=_body()).status_code == 403
    assert _tim(client_as, "pembaca").get(_url(pid)).json()["total"] == 0


def test_openapi_dua_endpoint_terdokumentasi_tanpa_sunting(client_as, client):
    pid = _protokol(client_as, "KN-IMUT")
    kid = _tim(client_as).post(_url(pid), json=_body()).json()["id"]
    c = _tim(client_as)
    assert c.put(_url(pid), json=_body()).status_code == 405
    assert c.patch(_url(pid), json=_body()).status_code == 405
    assert c.delete(_url(pid)).status_code == 405
    assert c.patch(f"{_url(pid)}/{kid}", json={"ringkasan": "x"}).status_code in (404, 405)
    assert c.delete(f"{_url(pid)}/{kid}").status_code in (404, 405)

    paths = client.get("/openapi.json").json()["paths"]
    kasus = [p for p in paths if "kasus-negatif" in p]
    assert kasus == [f"{PROTOKOL}/{{protokol_id}}/kasus-negatif"]
    ops = paths[kasus[0]]
    assert set(ops) == {"get", "post"}
    for op in ops.values():
        assert op["summary"] and op["tags"] == ["riset"]
        assert {"401", "403", "404"} <= set(op["responses"])
    assert {"409", "422"} <= set(ops["post"]["responses"])
