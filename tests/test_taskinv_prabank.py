"""Test cerita pra-bank dan log paparan Task Inventory (backlog #131)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.taskinv.schemas.prabank import ExposureState
from anjab_abk_backend.taskinv.services.prabank_sql import SqlTiPrabankService

SESI = "/api/v1/task-inventory/sesi"


def _hidup(app, aktif: bool = True) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, feature_prebank_freeze=aktif
    )


def _responden(client: TestClient, jabatan_id: str) -> tuple[str, str]:
    r = client.post(SESI, json={"jabatan_id": jabatan_id, "cabang": "Bandung"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post(f"{SESI}/{sid}/mulai-tahap1").status_code == 200
    r = client.post(f"{SESI}/{sid}/responden", json={"nama": "Responden"})
    assert r.status_code == 201, r.text
    return sid, r.json()["id"]


@pytest.fixture
def rsp(client: TestClient, app, jabatan_id_tk: str) -> str:
    _hidup(app)
    return _responden(client, jabatan_id_tk)[1]


def _u(rid: str, bagian: str) -> str:
    return f"{SESI}/responden/{rid}/{bagian}"


def test_cerita_beku_lalu_paparan_locked(client: TestClient, rsp: str) -> None:
    assert client.put(_u(rsp, "cerita-prabank"), json={"teks": "Saya mengajar."}).status_code == 200
    r = client.post(_u(rsp, "cerita-prabank/bekukan"))
    assert r.status_code == 200 and r.json()["frozen_at"]
    p = client.post(_u(rsp, "paparan"), json={"jenis": "BANK_TUGAS"})
    assert p.status_code == 201
    assert p.json()["status_saat_paparan"] == "LOCKED_PRE_EXPOSURE"
    g = client.get(_u(rsp, "prabank")).json()
    assert g["exposure_state"] == "LOCKED_PRE_EXPOSURE"
    assert g["first_exposed_at"] > g["frozen_at"]
    assert g["cerita"]["teks"] == "Saya mengajar."


def test_bekukan_idempoten_waktu_tetap(client: TestClient, rsp: str) -> None:
    client.put(_u(rsp, "cerita-prabank"), json={"teks": "x"})
    a = client.post(_u(rsp, "cerita-prabank/bekukan")).json()["frozen_at"]
    b = client.post(_u(rsp, "cerita-prabank/bekukan")).json()["frozen_at"]
    assert a == b


def test_paparan_tanpa_cerita_exposed_dan_seleksi_lolos(client: TestClient, rsp: str) -> None:
    p = client.post(_u(rsp, "paparan"), json={"jenis": "CONTOH_TUGAS"})
    assert p.status_code == 201 and p.json()["status_saat_paparan"] == "EXPOSED"
    assert client.get(_u(rsp, "prabank")).json()["exposure_state"] == "EXPOSED"
    r = client.put(_u(rsp, "seleksi"), json={"task_kode": []})
    assert r.status_code == 200, r.text


def test_prabank_awal_belum_terpapar(client: TestClient, rsp: str) -> None:
    g = client.get(_u(rsp, "prabank")).json()
    assert g == {
        "cerita": None,
        "frozen_at": None,
        "first_exposed_at": None,
        "exposure_state": "BELUM_TERPAPAR",
    }


def test_saklar_mati_409_dan_seleksi_tanpa_gerbang(
    client: TestClient, app, jabatan_id_tk: str
) -> None:
    _hidup(app, False)
    _, rid = _responden(client, jabatan_id_tk)
    for aksi in (
        client.put(_u(rid, "cerita-prabank"), json={"teks": "x"}),
        client.post(_u(rid, "cerita-prabank/bekukan")),
        client.post(_u(rid, "paparan"), json={"jenis": "BANK_TUGAS"}),
        client.get(_u(rid, "prabank")),
    ):
        assert aksi.status_code == 409
        assert aksi.json()["error"] == "feature_disabled"
    assert client.put(_u(rid, "seleksi"), json={"task_kode": []}).status_code == 200


def test_paparan_body_terjadi_pada_422(client: TestClient, rsp: str) -> None:
    r = client.post(
        _u(rsp, "paparan"),
        json={"jenis": "BANK_TUGAS", "terjadi_pada": "2020-01-01T00:00:00Z"},
    )
    assert r.status_code == 422


def test_responden_partisipan_lain_403(
    client: TestClient, client_as, app, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService

    _hidup(app)
    par_a = partisipan_factory("prabank-a", jabatan_utama_id=jabatan_id_tk)
    par_b = partisipan_factory("prabank-b", jabatan_utama_id=jabatan_id_tk)
    svc = SqlSMEPanelService(db_session)
    panel = svc.create(SMEPanelCreate(jabatan_id=jabatan_id_tk))
    svc.add_anggota(panel.id, par_a)
    svc.add_anggota(panel.id, par_b)
    r = client.post(SESI, json={"jabatan_id": jabatan_id_tk, "cabang": "Bandung"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    items = client.get(f"{SESI}/{sid}/responden").json()["items"]
    rid = next(x["id"] for x in items if x["partisipan_id"] == par_a)
    as_b = client_as("prabank-b")
    assert as_b.put(_u(rid, "cerita-prabank"), json={"teks": "x"}).status_code == 403
    assert as_b.get(_u(rid, "prabank")).status_code == 403
    as_a = client_as("prabank-a")
    assert as_a.put(_u(rid, "cerita-prabank"), json={"teks": "x"}).status_code == 200


def test_ubah_cerita_beku_409(client: TestClient, rsp: str) -> None:
    client.put(_u(rsp, "cerita-prabank"), json={"teks": "satu"})
    client.post(_u(rsp, "cerita-prabank/bekukan"))
    r = client.put(_u(rsp, "cerita-prabank"), json={"teks": "dua"})
    assert r.status_code == 409 and r.json()["error"] == "CERITA_SUDAH_DIKUNCI"


def test_bekukan_kosong_422(client: TestClient, rsp: str) -> None:
    r = client.post(_u(rsp, "cerita-prabank/bekukan"))
    assert r.status_code == 422 and r.json()["error"] == "CERITA_KOSONG"


def test_seleksi_sebelum_paparan_409(client: TestClient, rsp: str) -> None:
    r = client.put(_u(rsp, "seleksi"), json={"task_kode": []})
    assert r.status_code == 409 and r.json()["error"] == "PAPARAN_BELUM_TERCATAT"


def test_update_paparan_ditolak_basis_data(client: TestClient, rsp: str, db_session) -> None:
    pid = client.post(_u(rsp, "paparan"), json={"jenis": "BANK_TUGAS"}).json()["id"]
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE ti_paparan_event SET jenis = 'CONTOH_TUGAS' WHERE id = :i"), {"i": pid}
        )


def test_status_paparan_seam(client: TestClient, rsp: str, db_session) -> None:
    svc = SqlTiPrabankService(db_session)
    assert svc.status_paparan(rsp) == ExposureState.BELUM_TERPAPAR
    assert svc.status_paparan(str(uuid.uuid4())) is None
    client.post(_u(rsp, "paparan"), json={"jenis": "BANK_TUGAS"})
    assert svc.status_paparan(rsp) == ExposureState.EXPOSED
