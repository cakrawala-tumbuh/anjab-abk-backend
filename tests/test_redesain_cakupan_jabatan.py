"""Tes cakupan jabatan redesain: seed 19 x 2 cabang, CRUD+search Tim, pemetaan jabatan (#61)."""

from __future__ import annotations

from sqlalchemy import func, select

from anjab_abk_backend.models import RedesainCakupanJabatanModel, RedesainRiwayatModel
from anjab_abk_backend.redesain.seed import seed_cakupan_jabatan

URL = "/api/v1/redesain/cakupan-jabatan"


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _satu(c, role: str, cabang: str) -> dict:
    r = c.post(
        f"{URL}/search", json={"domain": [["role_kode", "=", role], ["cabang", "=", cabang]]}
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    return items[0]


def test_seed_idempoten_38_baris_dan_j19(db_session):
    seed_cakupan_jabatan(db_session)
    assert seed_cakupan_jabatan(db_session) == 0
    m = RedesainCakupanJabatanModel
    assert db_session.scalar(select(func.count()).select_from(m)) == 38
    j19 = db_session.scalars(select(m).where(m.role_kode == "J-19")).all()
    assert {r.nama_jabatan for r in j19} == {"Operator Dapodik"}
    assert all(r.jabatan_id is None and r.status_unit == "Belum diperiksa" for r in j19)


def test_search_cabang_semarang_19_baris(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "cj-1")
    s = c.post(f"{URL}/search", json={"domain": [["cabang", "=", "Semarang"]], "limit": 100})
    assert s.status_code == 200, s.text
    assert s.json()["total"] == 19
    assert c.get(URL).json()["total"] == 38


def test_patch_status_dan_jabatan_riwayat(client_as, partisipan_factory, db_session, jabatan_id_tk):
    c = _tim(client_as, partisipan_factory, "cj-2")
    a = _satu(c, "J-01", "Bandung")
    r = c.patch(f"{URL}/{a['id']}", json={"status_unit": "Ada", "jabatan_id": jabatan_id_tk})
    assert r.status_code == 200, r.text
    assert r.json()["status_unit"] == "Ada"
    assert r.json()["jabatan_id"] == jabatan_id_tk
    assert c.get(f"{URL}/{a['id']}").json()["jabatan_id"] == jabatan_id_tk
    n = db_session.scalar(
        select(func.count())
        .select_from(RedesainRiwayatModel)
        .where(
            RedesainRiwayatModel.entitas == "cakupan_jabatan",
            RedesainRiwayatModel.entitas_id == a["id"],
            RedesainRiwayatModel.aksi == "update",
        )
    )
    assert n == 1
    # nullable boleh dikosongkan
    r2 = c.patch(f"{URL}/{a['id']}", json={"jabatan_id": None})
    assert r2.status_code == 200 and r2.json()["jabatan_id"] is None


def test_patch_jabatan_tak_dikenal_422(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "cj-3")
    a = _satu(c, "J-02", "Bandung")
    assert c.patch(f"{URL}/{a['id']}", json={"jabatan_id": "jbt_tidak_ada"}).status_code == 422


def test_status_di_luar_kosakata_422(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "cj-4")
    a = _satu(c, "J-03", "Bandung")
    assert c.patch(f"{URL}/{a['id']}", json={"status_unit": "Mungkin"}).status_code == 422
    assert c.patch(f"{URL}/{a['id']}", json={"peta_diperkuat": "Ada"}).status_code == 422


def test_create_ganda_409_cabang_salah_422(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "cj-5")
    body = {"role_kode": "J-01", "nama_jabatan": "Kepala Sekolah", "cabang": "Bandung"}
    assert c.post(URL, json=body).status_code == 409
    assert c.post(URL, json={**body, "cabang": "Jakarta"}).status_code == 422
    assert c.post(URL, json={**body, "role_kode": "X-1"}).status_code == 422
    baru = c.post(URL, json={**body, "role_kode": "J-20", "nama_jabatan": "Baru"})
    assert baru.status_code == 201, baru.text


def test_get_tak_ada_404_dan_sekolah_pengisi_403(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "cj-6")
    assert c.get(f"{URL}/tidak-ada").status_code == 404
    partisipan_factory("cj-sp")
    sp = client_as("cj-sp", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(f"{URL}/search", json={"domain": []}).status_code == 403
