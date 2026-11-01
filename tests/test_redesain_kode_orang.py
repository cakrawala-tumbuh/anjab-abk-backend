"""Tes kode orang (pseudonim) redesain (backlog `#49`)."""

from __future__ import annotations

import re

from anjab_abk_backend.redesain.services.kode_orang_sql import format_kode

URL = "/api/v1/redesain/kode-orang"
POLA = re.compile(r"^O-\d{4,}$")


def test_format_kode_nol_depan_dan_tanpa_potong():
    assert format_kode(1) == "O-0001"
    assert format_kode(12345) == "O-12345"


def test_saya_dua_kali_kode_identik(client_as, partisipan_factory):
    partisipan_factory("sp-1")
    c = client_as("sp-1", groups=["sekolah-pengisi"])
    r1 = c.get(f"{URL}/saya")
    r2 = c.get(f"{URL}/saya")
    assert r1.status_code == 200
    assert POLA.match(r1.json()["kode"])
    assert r1.json() == r2.json()
    assert set(r1.json()) == {"kode"}


def test_saya_subject_tanpa_partisipan_403(client_as):
    c = client_as("tak-ada", groups=["tim-kajian"])
    assert c.get(f"{URL}/saya").status_code == 403


def test_saya_bukan_grup_403(client_as, partisipan_factory):
    partisipan_factory("x-1")
    assert client_as("x-1", groups=["admin"]).get(f"{URL}/saya").status_code == 403


def test_list_sebagai_pengisi_atau_admin_403(client_as):
    for g in (["sekolah-pengisi"], ["admin"]):
        assert client_as("a", groups=g).get(URL).status_code == 403


def test_narasumber_berurutan_dan_riwayat(client_as, partisipan_factory):
    partisipan_factory("tk-1")
    c = client_as("tk-1", groups=["tim-kajian"])
    a = c.post(URL, json={"keterangan_peran": "Narasumber A"})
    b = c.post(URL, json={"keterangan_peran": "Narasumber B"})
    assert a.status_code == b.status_code == 201
    assert a.json()["partisipan_id"] is None
    na = int(a.json()["kode"][2:])
    assert int(b.json()["kode"][2:]) == na + 1
    rw = c.get("/api/v1/redesain/riwayat", params={"entitas_id": a.json()["id"]}).json()
    assert rw["total"] == 1
    assert rw["items"][0]["entitas"] == "kode_orang"
    assert POLA.match(rw["items"][0]["pelaku_kode_orang"])


def test_post_partisipan_sudah_berkode_409(client_as, partisipan_factory):
    partisipan_factory("tk-2")
    pid = partisipan_factory("tgt-2")
    c = client_as("tk-2", groups=["tim-kajian"])
    assert c.post(URL, json={"keterangan_peran": "p", "partisipan_id": pid}).status_code == 201
    assert c.post(URL, json={"keterangan_peran": "p", "partisipan_id": pid}).status_code == 409


def test_post_partisipan_tak_ada_404(client_as, partisipan_factory):
    partisipan_factory("tk-3")
    c = client_as("tk-3", groups=["tim-kajian"])
    r = c.post(URL, json={"keterangan_peran": "p", "partisipan_id": "par_nope"})
    assert r.status_code == 404


def test_patch_dan_get_id_tak_ada_404(client_as, partisipan_factory):
    partisipan_factory("tk-4")
    c = client_as("tk-4", groups=["tim-kajian"])
    assert c.patch(f"{URL}/zzz", json={"keterangan_peran": "x"}).status_code == 404
    assert c.get(f"{URL}/zzz").status_code == 404


def test_patch_ubah_peran_dan_search(client_as, partisipan_factory):
    partisipan_factory("tk-5")
    c = client_as("tk-5", groups=["tim-kajian"])
    row = c.post(URL, json={"keterangan_peran": "lama"}).json()
    r = c.patch(f"{URL}/{row['id']}", json={"keterangan_peran": "baru"})
    assert r.status_code == 200
    assert r.json()["keterangan_peran"] == "baru"
    assert r.json()["kode"] == row["kode"]
    s = c.post(f"{URL}/search", json={"domain": [["kode", "=", row["kode"]]]})
    assert [i["id"] for i in s.json()["items"]] == [row["id"]]
    assert c.post(f"{URL}/search", json={"domain": [["x", "=", 1]]}).status_code == 422


def test_tidak_ada_delete_di_openapi(app):
    paths = app.openapi()["paths"]
    ops = {(m, p) for p, v in paths.items() if p.startswith(URL) for m in v}
    assert not any(m == "delete" for m, _ in ops)
    assert ("get", f"{URL}/saya") in ops


def test_tanpa_token_401(anon_client):
    assert anon_client.get(URL).status_code == 401
    assert anon_client.get(f"{URL}/saya").status_code == 401
