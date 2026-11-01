"""Tes fondasi domain redesain (backlog `#48`): guard peran, riwayat append-only."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService
from anjab_abk_backend.dependencies import authorize_sekolah_scope
from anjab_abk_backend.errors import ForbiddenError
from anjab_abk_backend.redesain.services.riwayat_sql import SqlRiwayatService
from anjab_abk_backend.security import Principal

URL = "/api/v1/redesain/riwayat"


def _catat(db: Session, entitas_id: str = "msl_1", **kw):
    return SqlRiwayatService(db).catat(
        kw.get("entitas", "masalah"),
        entitas_id,
        kw.get("aksi", "create"),
        None,
        {"nama": "x", "status": "Hipotesis"},
        None,
    )


def test_catat_lalu_get_mengembalikan_nilai_sesudah_utuh(client_as, db_session):
    rec = _catat(db_session)
    c = client_as("tk-1", groups=["tim-kajian"])
    r = c.get(URL, params={"entitas_id": "msl_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == rec.id
    assert body["items"][0]["nilai_sesudah"] == {"nama": "x", "status": "Hipotesis"}
    assert body["items"][0]["nilai_sebelum"] is None
    assert body["items"][0]["pelaku_kode_orang"] is None


def test_filter_entitas_dan_entitas_id(client_as, db_session):
    _catat(db_session, "a1")
    _catat(db_session, "b1", entitas="alur")
    c = client_as("tk-1", groups=["tim-kajian"])
    assert c.get(URL, params={"entitas": "alur"}).json()["total"] == 1
    assert c.get(URL, params={"entitas_id": "zzz"}).json()["total"] == 0


def test_search_domain_odoo(client_as, db_session):
    _catat(db_session, "a1", entitas="x")
    _catat(db_session, "a2", entitas="y")
    c = client_as("tk-1", groups=["tim-kajian"])
    r = c.post(f"{URL}/search", json={"domain": [["entitas", "=", "x"]]})
    assert r.status_code == 200
    assert [i["entitas_id"] for i in r.json()["items"]] == ["a1"]


def test_search_field_tak_dikenal_422(client_as):
    c = client_as("tk-1", groups=["tim-kajian"])
    r = c.post(f"{URL}/search", json={"domain": [["nilai_sesudah", "=", "x"]]})
    assert r.status_code == 422


@pytest.mark.parametrize("groups", [["admin"], ["sekolah-pengisi"], []])
def test_bukan_tim_kajian_403(client_as, groups):
    c = client_as("a", groups=groups)
    assert c.get(URL).status_code == 403
    assert c.post(f"{URL}/search", json={}).status_code == 403


def test_tanpa_token_401(anon_client):
    assert anon_client.get(URL).status_code == 401
    assert anon_client.post(f"{URL}/search", json={}).status_code == 401


def test_tidak_ada_operasi_tulis_di_openapi(app):
    paths = app.openapi()["paths"]
    ops = {(m.upper(), p) for p, v in paths.items() if p.startswith(URL) for m in v}
    assert ops == {("GET", URL), ("POST", f"{URL}/search")}


def _par(db: Session, subject: str, sekolah_id: str) -> str:
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate

    return (
        SqlPartisipanService(db)
        .create(
            PartisipanCreate(
                nama=f"P {subject}",
                email=f"{subject}@test.id",
                sekolah_id=sekolah_id,
                jabatan_utama_id="jbt_x",
                masa_kerja_tahun=1,
            ),
            authentik_user_id=subject,
        )
        .id
    )


def test_scope_sekolah(db_session):
    svc = SqlPartisipanService(db_session)
    _par(db_session, "pengisi-a", "skl_A")
    pe = Principal(subject="pengisi-a", username="u", groups=["sekolah-pengisi"])
    authorize_sekolah_scope(pe, "skl_A", svc)  # lolos
    with pytest.raises(ForbiddenError):
        authorize_sekolah_scope(pe, "skl_B", svc)
    # tim-kajian selalu lolos
    tk = Principal(subject="x", username="u", groups=["tim-kajian"])
    authorize_sekolah_scope(tk, "skl_B", svc)
    # tanpa partisipan tertaut
    tanpa = Principal(subject="tak-ada", username="u", groups=["sekolah-pengisi"])
    with pytest.raises(ForbiddenError):
        authorize_sekolah_scope(tanpa, "skl_A", svc)
    # grup lain (admin saja)
    adm = Principal(subject="pengisi-a", username="u", groups=["admin"])
    with pytest.raises(ForbiddenError):
        authorize_sekolah_scope(adm, "skl_A", svc)
