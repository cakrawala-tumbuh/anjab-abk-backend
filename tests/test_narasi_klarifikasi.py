"""Tes register klarifikasi narasi (`/api/v1/narasi/klarifikasi`): alur, duplikasi, riwayat."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

URL = "/api/v1/narasi/klarifikasi"
KASUS = "/api/v1/narasi/kasus"


def _tim(client_as, subject: str):
    return client_as(subject, groups=["tim-kajian"])


def _kasus(client_as) -> str:
    c = _tim(client_as, "penyusun-kasus")
    r = c.post(
        KASUS,
        json={
            "instrument_id": "wcp",
            "field_key": f"f-{uuid.uuid4().hex[:8]}",
            "peran_ref": "guru",
            "periode": "2026/27",
            "narrative_kind": "F1_FORMAL",
            "intended_use": "uji",
            "permission_scope": "internal",
            "sensitivity_class": "NONPRIBADI",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _body(narasi_id: str, **ubah) -> dict:
    body = {
        "narasi_id": narasi_id,
        "claim_id": "C-1",
        "source_ids_checked": ["src-1", "src-2"],
        "materiality_reason": "Menentukan beban kerja guru.",
        "alternative_hypothesis": "Beban sebenarnya lebih rendah.",
        "intended_decision": "Setujui perubahan jabatan.",
        "recipient_role": "kepala-sekolah",
        "periode": "2026/27",
        "exposure": "BELUM_TERPAPAR",
        "due_trigger": "Sebelum rapat tinjauan.",
        "question_text": "Berapa jam per minggu tugas ini dikerjakan?",
    }
    body.update(ubah)
    return body


def _buat(client_as, narasi_id: str, pembuat: str = "pembuat", **ubah) -> dict:
    r = _tim(client_as, pembuat).post(URL, json=_body(narasi_id, **ubah))
    assert r.status_code == 201, r.text
    return r.json()


def test_alur_penuh_dan_riwayat_tiga_event(client_as):
    nid = _kasus(client_as)
    d = _buat(client_as, nid)
    assert d["reviewer_approval"] == "MENUNGGU" and d["disposition"] == "TERBUKA"
    assert d["dibuat_oleh"] == "pembuat" and d["ai_usulan_id"] is None
    assert [e["aksi"] for e in d["riwayat"]] == ["DIBUAT"]
    kid = d["id"]

    r = _tim(client_as, "reviewer").post(
        f"{URL}/{kid}/persetujuan", json={"keputusan": "SETUJU", "catatan": "layak"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["reviewer_approval"] == "DISETUJUI"

    r = _tim(client_as, "fasilitator").post(
        f"{URL}/{kid}/jawaban",
        json={"response_ref": "WA-2026-11-12-01", "jawaban_mentah": "Sekitar 6 jam."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["disposition"] == "TERJAWAB"

    g = _tim(client_as, "pembaca").get(f"{URL}/{kid}")
    assert g.status_code == 200
    j = g.json()
    for k in _body(nid):
        assert j[k] == _body(nid)[k]
    assert j["response_ref"] == "WA-2026-11-12-01" and j["jawaban_mentah"] == "Sekitar 6 jam."
    assert [(e["aksi"], e["actor_key"]) for e in j["riwayat"]] == [
        ("DIBUAT", "pembuat"),
        ("DISETUJUI", "reviewer"),
        ("JAWABAN_DICATAT", "fasilitator"),
    ]


def test_duplikat_terbuka_409_lalu_batalkan_dan_buat_ulang(client_as):
    nid = _kasus(client_as)
    d = _buat(client_as, nid)
    c = _tim(client_as, "pembuat")
    r = c.post(URL, json=_body(nid))
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_GANDA"
    # klaim lain pada kasus yang sama boleh
    assert c.post(URL, json=_body(nid, claim_id="C-2")).status_code == 201

    b = c.post(f"{URL}/{d['id']}/batalkan", json={"catatan": "salah sasaran"})
    assert b.status_code == 200 and b.json()["disposition"] == "DIBATALKAN"
    assert [e["aksi"] for e in b.json()["riwayat"]] == ["DIBUAT", "DIBATALKAN"]
    assert c.post(URL, json=_body(nid)).status_code == 201
    # batalkan ulang / aksi lain pada yang sudah dibatalkan
    r = c.post(f"{URL}/{d['id']}/batalkan", json={"catatan": "sekali lagi"})
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_TIDAK_TERBUKA"
    r = _tim(client_as, "reviewer").post(
        f"{URL}/{d['id']}/persetujuan", json={"keputusan": "SETUJU"}
    )
    assert r.status_code == 409


def test_reviewer_pembuat_sendiri_409_dan_persetujuan_ganda(client_as):
    d = _buat(client_as, _kasus(client_as))
    r = _tim(client_as, "pembuat").post(
        f"{URL}/{d['id']}/persetujuan", json={"keputusan": "SETUJU"}
    )
    assert r.status_code == 409 and r.json()["error"] == "REVIEWER_TIDAK_INDEPENDEN"
    rv = _tim(client_as, "reviewer")
    assert rv.post(f"{URL}/{d['id']}/persetujuan", json={"keputusan": "SETUJU"}).status_code == 200
    r = rv.post(f"{URL}/{d['id']}/persetujuan", json={"keputusan": "TOLAK", "catatan": "terlambat"})
    assert r.status_code == 409 and r.json()["error"] == "PERSETUJUAN_SUDAH_ADA"


def test_tolak_butuh_catatan_dan_menutup_baris_sehingga_aksi_lanjutan_409(client_as):
    d = _buat(client_as, _kasus(client_as))
    rv = _tim(client_as, "reviewer")
    assert rv.post(f"{URL}/{d['id']}/persetujuan", json={"keputusan": "TOLAK"}).status_code == 422
    r = rv.post(
        f"{URL}/{d['id']}/persetujuan", json={"keputusan": "TOLAK", "catatan": "kurang jelas"}
    )
    assert r.status_code == 200 and r.json()["reviewer_approval"] == "DITOLAK"
    assert r.json()["disposition"] == "DITOLAK"
    assert [e["aksi"] for e in r.json()["riwayat"]] == ["DIBUAT", "DITOLAK"]
    r = rv.post(f"{URL}/{d['id']}/jawaban", json={"response_ref": "x", "jawaban_mentah": "y"})
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_TIDAK_TERBUKA"
    r = rv.post(f"{URL}/{d['id']}/persetujuan", json={"keputusan": "SETUJU"})
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_TIDAK_TERBUKA"
    r = _tim(client_as, "pembuat").post(f"{URL}/{d['id']}/batalkan", json={"catatan": "halo ya"})
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_TIDAK_TERBUKA"


def test_tolak_lalu_buat_baru_untuk_klaim_yang_sama(client_as):
    nid = _kasus(client_as)
    d = _buat(client_as, nid)
    _tim(client_as, "reviewer").post(
        f"{URL}/{d['id']}/persetujuan", json={"keputusan": "TOLAK", "catatan": "kurang netral"}
    )
    baru = _tim(client_as, "pembuat").post(URL, json=_body(nid))
    assert baru.status_code == 201, baru.text
    assert baru.json()["id"] != d["id"] and baru.json()["disposition"] == "TERBUKA"
    c = _tim(client_as, "pembaca")
    assert c.get(URL, params={"narasi_id": nid, "disposition": "DITOLAK"}).json()["total"] == 1


def test_jawaban_sebelum_disetujui_409_dan_ganda_409(client_as):
    d = _buat(client_as, _kasus(client_as))
    c = _tim(client_as, "fasilitator")
    jawab = {"response_ref": "REF-1", "jawaban_mentah": "Jawaban."}
    r = c.post(f"{URL}/{d['id']}/jawaban", json=jawab)
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_BELUM_DISETUJUI"
    _tim(client_as, "reviewer").post(f"{URL}/{d['id']}/persetujuan", json={"keputusan": "SETUJU"})
    assert c.post(f"{URL}/{d['id']}/jawaban", json=jawab).status_code == 200
    r = c.post(f"{URL}/{d['id']}/jawaban", json=jawab)
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_TIDAK_TERBUKA"
    # jawaban wajib lengkap
    assert c.post(f"{URL}/{d['id']}/jawaban", json={"response_ref": "x"}).status_code == 422
    # terjawab tidak bisa dibatalkan
    assert c.post(f"{URL}/{d['id']}/batalkan", json={"catatan": "terlambat"}).status_code == 409


def test_validasi_422_dan_kasus_asing_404(client_as):
    nid = _kasus(client_as)
    c = _tim(client_as, "pembuat")
    assert c.post(URL, json=_body(nid, question_text="A? B?")).status_code == 422
    assert c.post(URL, json=_body(nid, source_ids_checked=[])).status_code == 422
    assert c.post(URL, json=_body(nid, source_ids_checked=[" "])).status_code == 422
    assert c.post(URL, json=_body(nid, exposure="ASING")).status_code == 422
    assert c.post(URL, json=_body(nid, claim_id="  ")).status_code == 422
    body = _body(nid)
    del body["due_trigger"]
    assert c.post(URL, json=body).status_code == 422
    assert c.post(URL, json={**_body(nid), "ekstra": 1}).status_code == 422
    assert c.post(URL, json=_body("tidak-ada")).status_code == 404
    assert c.get(f"{URL}/tidak-ada").status_code == 404
    assert c.post(f"{URL}/tidak-ada/batalkan", json={"catatan": "halo ya"}).status_code == 404


def test_list_filter_dan_otorisasi(client_as):
    n1, n2 = _kasus(client_as), _kasus(client_as)
    a = _buat(client_as, n1)
    _buat(client_as, n2)
    c = _tim(client_as, "pembuat")
    c.post(f"{URL}/{a['id']}/batalkan", json={"catatan": "dibatalkan"})
    r = c.get(URL, params={"narasi_id": n1})
    assert r.status_code == 200 and r.json()["total"] == 1
    assert "riwayat" not in r.json()["items"][0]
    assert c.get(URL, params={"narasi_id": n1, "disposition": "TERBUKA"}).json()["total"] == 0
    assert c.get(URL, params={"narasi_id": n1, "disposition": "DIBATALKAN"}).json()["total"] == 1
    assert c.get(URL, params={"disposition": "ASING"}).status_code == 422

    luar = client_as("orang-luar", groups=["partisipan"])
    assert luar.get(URL).status_code == 403
    assert luar.post(URL, json=_body(n1)).status_code == 403
    assert luar.get(f"{URL}/{a['id']}").status_code == 403
    assert luar.post(f"{URL}/{a['id']}/batalkan", json={"catatan": "halo ya"}).status_code == 403


def test_update_dan_delete_event_ditolak_basis_data(client_as, db_session):
    d = _buat(client_as, _kasus(client_as))
    eid = d["riwayat"][0]["id"]
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE narasi_klarifikasi_event SET catatan = 'ubah' WHERE id = :i"), {"i": eid}
        )
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM narasi_klarifikasi_event WHERE id = :i"), {"i": eid})
