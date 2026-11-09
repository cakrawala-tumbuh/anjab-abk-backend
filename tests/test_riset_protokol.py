"""Tes protokol riset (`riset_protokol`): versi per kode, kunci permanen, hash, otorisasi."""

from __future__ import annotations

import hashlib

URL = "/api/v1/riset/protokol"


def _tim(client_as, subject: str = "tim-riset"):
    return client_as(subject, groups=["tim-kajian"])


def _body(**ubah) -> dict:
    body = {"kode": "P08-SINTESIS", "judul": "Protokol sintesis", "isi": "Isi protokol ✓ v1."}
    body.update(ubah)
    return body


def test_buat_draf_versi_naik_per_kode_dan_pembuat_dari_token(client_as):
    c = _tim(client_as, "tim-satu")
    r1 = c.post(URL, json=_body(kode="PRT-VERSI"))
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    assert d1["status"] == "DRAF" and d1["versi"] == 1
    assert d1["dibuat_oleh"] == "tim-satu"
    assert d1["isi_hash"] is None and d1["dikunci_oleh"] is None and d1["dikunci_pada"] is None
    assert len(d1["id"]) == 36
    r2 = c.post(URL, json=_body(kode="PRT-VERSI", isi="Perbaikan draf."))
    assert r2.status_code == 201
    assert r2.json()["versi"] == 2 and r2.json()["status"] == "DRAF"
    lain = c.post(URL, json=_body(kode="PRT-LAIN"))
    assert lain.json()["versi"] == 1
    assert c.post(URL, json=_body(dibuat_oleh="orang-lain")).status_code == 422


def test_kunci_hash_cocok_aktor_dari_token_lalu_kunci_ulang_409(client_as):
    isi = "Protokol terkunci ✓ dengan UTF-8."
    pid = _tim(client_as).post(URL, json=_body(kode="PRT-KUNCI", isi=isi)).json()["id"]
    c = _tim(client_as, "pengunci")
    r = c.post(f"{URL}/{pid}/kunci")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "TERKUNCI"
    assert d["isi_hash"] == hashlib.sha256(isi.encode("utf-8")).hexdigest()
    assert d["dikunci_oleh"] == "pengunci" and d["dikunci_pada"] is not None
    assert d["dibuat_oleh"] == "tim-riset"
    g = c.get(f"{URL}/{pid}")
    assert g.status_code == 200 and g.json()["isi"] == isi and g.json()["status"] == "TERKUNCI"
    ulang = c.post(f"{URL}/{pid}/kunci")
    assert ulang.status_code == 409
    assert ulang.json()["error"] == "PROTOKOL_TERKUNCI"
    assert c.get(f"{URL}/{pid}").json()["dikunci_oleh"] == "pengunci"


def test_tanpa_patch_put_delete(client_as, client):
    pid = _tim(client_as).post(URL, json=_body(kode="PRT-IMUT")).json()["id"]
    c = _tim(client_as)
    assert c.patch(f"{URL}/{pid}", json={"judul": "x"}).status_code == 405
    assert c.put(f"{URL}/{pid}", json={"judul": "x"}).status_code == 405
    assert c.delete(f"{URL}/{pid}").status_code == 405
    paths = client.get("/openapi.json").json()["paths"]
    rute = {p: ops for p, ops in paths.items() if p.startswith(URL)}
    assert set(rute) == {
        URL,
        f"{URL}/{{protokol_id}}",
        f"{URL}/{{protokol_id}}/kunci",
        f"{URL}/{{protokol_id}}/statistik",  # statistik riset (#122), juga tanpa sunting
        f"{URL}/{{protokol_id}}/kasus-negatif",  # kasus negatif (#123), append-only
        f"{URL}/{{protokol_id}}/sintesis-ai",  # pengajuan P08 (#126), hanya POST
    }
    for p, ops in rute.items():
        assert not ({"patch", "put", "delete"} & set(ops)), p
        for op in ops.values():
            assert op["summary"] and op["tags"] == ["riset"]
            assert {"401", "403"} <= set(op["responses"])
    assert "409" in rute[f"{URL}/{{protokol_id}}/kunci"]["post"]["responses"]
    assert "404" in rute[f"{URL}/{{protokol_id}}/kunci"]["post"]["responses"]


def test_validasi_kode_dan_isi_422(client_as):
    c = _tim(client_as)
    assert c.post(URL, json=_body(kode="ada spasi")).status_code == 422
    assert c.post(URL, json=_body(kode="")).status_code == 422
    assert c.post(URL, json=_body(kode="K" * 41)).status_code == 422
    assert c.post(URL, json=_body(isi="")).status_code == 422
    assert c.post(URL, json=_body(isi="a" * 100_001)).status_code == 422
    assert c.post(URL, json=_body(kode="PRT-BATAS", isi="a" * 100_000)).status_code == 201
    assert c.post(URL, json=_body(kode="K" * 40)).status_code == 201


def test_list_ringkas_tanpa_isi_dengan_filter(client_as):
    c = _tim(client_as)
    a = c.post(URL, json=_body(kode="PRT-DAFTAR")).json()
    c.post(URL, json=_body(kode="PRT-DAFTAR"))
    c.post(f"{URL}/{a['id']}/kunci")
    r = c.get(URL, params={"kode": "PRT-DAFTAR"})
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert all("isi" not in i for i in r.json()["items"])
    k = c.get(URL, params={"kode": "PRT-DAFTAR", "status": "TERKUNCI"}).json()
    assert k["total"] == 1 and k["items"][0]["id"] == a["id"]
    assert c.get(URL, params={"status": "BATAL"}).status_code == 422


def test_otorisasi_dan_404(anon_client, client_as):
    pid = _tim(client_as).post(URL, json=_body(kode="PRT-AUTH")).json()["id"]
    assert anon_client.get(URL).status_code == 401
    assert anon_client.post(URL, json=_body()).status_code == 401
    assert anon_client.post(f"{URL}/{pid}/kunci").status_code == 401
    for grup in (["admin"], ["partisipan"]):
        c = client_as("bukan-tim", groups=grup)
        assert c.get(URL).status_code == 403
        assert c.get(f"{URL}/{pid}").status_code == 403
        assert c.post(URL, json=_body()).status_code == 403
        assert c.post(f"{URL}/{pid}/kunci").status_code == 403
    tim = _tim(client_as)
    assert tim.get(f"{URL}/tidak-ada").status_code == 404
    assert tim.post(f"{URL}/tidak-ada/kunci").status_code == 404
    assert tim.get(f"{URL}/{pid}").json()["status"] == "DRAF"
