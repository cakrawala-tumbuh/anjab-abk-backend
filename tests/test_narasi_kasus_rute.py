"""Tes rute `/api/v1/narasi/kasus`: buat kasus, revisi manual, baca, list/search, otorisasi."""

from __future__ import annotations

import uuid

URL = "/api/v1/narasi/kasus"
SUMBER = "/api/v1/narasi/sumber"


def _tim(client_as, subject: str = "tim-kasus"):
    return client_as(subject, groups=["tim-kajian"])


def _body(**ubah) -> dict:
    body = {
        "instrument_id": "wcp",
        "field_key": f"f-{uuid.uuid4().hex[:8]}",
        "peran_ref": "guru",
        "periode": "2026/27",
        "narrative_kind": "F1_FORMAL",
        "intended_use": "uji",
        "permission_scope": "internal",
        "sensitivity_class": "NONPRIBADI",
    }
    body.update(ubah)
    return body


def _sumber(c, teks: str = "isi sumber") -> str:
    r = c.post(
        SUMBER,
        json={
            "judul": "j",
            "jenis": "SINTETIS",
            "versi": "v1",
            "periode": "2026/27",
            "teks": teks,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _kasus(c, **ubah) -> dict:
    r = c.post(URL, json=_body(**ubah))
    assert r.status_code == 201, r.text
    return r.json()


def _revisi(sumber_id: str, **ubah) -> dict:
    body = {
        "teks": "narasi manual",
        "sumber": [{"sumber_id": sumber_id, "basis_relation": "DIRECT", "source_span": "1-5"}],
        "supersedes_id": None,
    }
    body.update(ubah)
    return body


def test_alur_positif_buat_revisi_detail_riwayat(client_as):
    c = _tim(client_as, "tim-alur")
    k = _kasus(c)
    assert k["status"] == "SOURCE_CHECKED"
    assert k["dibuat_oleh"] == "tim-alur"
    sid = _sumber(c)
    r = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid))
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["revision_no"] == 1
    assert v["revision_origin"] == "REVIEWER_EDIT"
    assert v["status_hasil"] == "TEAM_REVIEW"
    assert v["dibuat_oleh"] == "tim-alur"
    assert "metadata_ai" not in v
    d = c.get(f"{URL}/{k['id']}").json()
    assert d["status"] == "TEAM_REVIEW"
    assert d["versi_terbaru"]["id"] == v["id"]
    assert d["versi_terbaru"]["sumber"][0]["sumber_id"] == sid
    assert "teks" not in d["versi_terbaru"]["sumber"][0]
    r2 = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid, supersedes_id=v["id"], teks="v2"))
    assert r2.status_code == 201
    assert r2.json()["revision_no"] == 2
    rw = c.get(f"{URL}/{k['id']}/riwayat").json()
    assert [x["revision_no"] for x in rw["versi"]] == [1, 2]
    assert rw["event"] == []
    assert "metadata_ai" in rw["versi"][0]


def test_jenis_selain_f1_dan_sensitif_422(client_as):
    c = _tim(client_as)
    r = c.post(URL, json=_body(narrative_kind="F2_ACTUAL"))
    assert r.status_code == 422
    assert "narasi_jenis_belum_dibuka" in r.text
    r = c.post(URL, json=_body(sensitivity_class="SENSITIF"))
    assert r.status_code == 422
    assert "narasi_sensitif_belum_dibuka" in r.text


def test_lingkup_ganda_409_termasuk_kolom_null(client_as):
    c = _tim(client_as)
    body = _body()
    assert c.post(URL, json=body).status_code == 201
    r = c.post(URL, json=body)
    assert r.status_code == 409
    assert "narasi_lingkup_ganda" in r.text


def test_revisi_tanpa_sumber_dan_sumber_tak_dikenal_422(client_as):
    c = _tim(client_as)
    k = _kasus(c)
    assert c.post(f"{URL}/{k['id']}/revisi", json=_revisi("x", sumber=[])).status_code == 422
    r = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(str(uuid.uuid4())))
    assert r.status_code == 422


def test_supersedes_basi_409(client_as):
    c = _tim(client_as)
    k = _kasus(c)
    sid = _sumber(c)
    v1 = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid)).json()
    r = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid))  # supersedes None, sudah basi
    assert r.status_code == 409
    assert "versi_basi" in r.text
    r = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid, supersedes_id=v1["id"]))
    assert r.status_code == 201


def test_dibuat_oleh_dari_body_diabaikan(client_as):
    c = _tim(client_as, "tim-token")
    k = c.post(URL, json=_body(dibuat_oleh="orang-lain")).json()
    assert k["dibuat_oleh"] == "tim-token"
    sid = _sumber(c)
    v = c.post(f"{URL}/{k['id']}/revisi", json=_revisi(sid, dibuat_oleh="orang-lain")).json()
    assert v["dibuat_oleh"] == "tim-token"


def test_list_dan_search(client_as):
    c = _tim(client_as)
    periode = f"p{uuid.uuid4().hex[:6]}"
    a = _kasus(c, periode=periode, instrument_id="dcs")
    _kasus(c, periode=periode, instrument_id="wcp")
    sid = _sumber(c)
    c.post(f"{URL}/{a['id']}/revisi", json=_revisi(sid))
    r = c.get(URL, params={"periode": periode})
    assert r.json()["total"] == 2
    r = c.get(URL, params={"periode": periode, "status": "TEAM_REVIEW"})
    assert [x["id"] for x in r.json()["items"]] == [a["id"]]
    r = c.get(URL, params={"periode": periode, "instrument_id": "wcp"})
    assert r.json()["total"] == 1
    r = c.post(
        f"{URL}/search",
        json={"domain": [["periode", "=", periode], ["instrument_id", "=", "dcs"]]},
    )
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["items"]] == [a["id"]]
    r = c.post(f"{URL}/search", json={"domain": [["dibuat_oleh", "=", "x"]]})
    assert r.status_code == 422


def test_otorisasi(client_as, anon_client):
    assert anon_client.get(URL).status_code == 401
    assert anon_client.post(URL, json=_body()).status_code == 401
    for grup in (["admin"], ["sekolah-pengisi"]):
        c = client_as("bukan-tim", groups=grup)
        assert c.get(URL).status_code == 403
        assert c.post(URL, json=_body()).status_code == 403
        assert c.post(f"{URL}/search", json={}).status_code == 403
        assert c.get(f"{URL}/x/riwayat").status_code == 403
        assert c.post(f"{URL}/x/revisi", json=_revisi("y")).status_code == 403
    c = _tim(client_as)
    tak_ada = str(uuid.uuid4())
    assert c.get(f"{URL}/{tak_ada}").status_code == 404
    assert c.get(f"{URL}/{tak_ada}/riwayat").status_code == 404
    assert c.post(f"{URL}/{tak_ada}/revisi", json=_revisi("y")).status_code == 404


def test_openapi_tanpa_patch_delete(client):
    paths = client.get("/openapi.json").json()["paths"]
    narasi = {p: v for p, v in paths.items() if p.startswith("/api/v1/narasi/kasus")}
    # 6 path kasus bawaan + 2 path rute pengaju draf AI (#98: draf-ai, permintaan-ai).
    assert len(narasi) == 8
    assert {p.rsplit("/", 1)[1] for p in narasi if p.endswith(("/draf-ai", "/permintaan-ai"))} == {
        "draf-ai",
        "permintaan-ai",
    }
    for p, ops in narasi.items():
        assert not ({"patch", "delete", "put"} & set(ops)), p
