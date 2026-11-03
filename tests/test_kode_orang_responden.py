"""Kode orang pseudonim menggantikan nama responden di respons API TI/OPM/WCP/DCS (#70)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.models import RedesainKodeOrangModel
from anjab_abk_backend.redesain.services.kode_orang_sql import SqlKodeOrangService
from anjab_abk_backend.redesain.services.riwayat_sql import SqlRiwayatService
from anjab_abk_backend.seed_db import seed_kode_orang_responden

POLA = re.compile(r"^O-\d{4,}$")


def _assign(client: TestClient, modul: str, ids: list[str]) -> list[dict]:
    r = client.post(f"/api/v1/{modul}/responden", json={"partisipan_ids": ids})
    assert r.status_code == 201, r.text
    return r.json()["created"]


def _svc(db: Session) -> SqlKodeOrangService:
    return SqlKodeOrangService(db, SqlRiwayatService(db))


def test_wcp_assign_dua_partisipan_kode_beda_tanpa_nama(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory("ko70-wcp-a"), partisipan_factory("ko70-wcp-b")]
    created = _assign(client, "wcp", ids)
    kodes = [c["kode_orang"] for c in created]
    assert all(POLA.match(k) for k in kodes)
    assert len(set(kodes)) == 2
    assert all("nama" not in c for c in created)
    items = client.get("/api/v1/wcp/responden").json()["items"]
    assert all("nama" not in i for i in items)
    assert {i["kode_orang"] for i in items} == set(kodes)


def test_partisipan_sama_di_wcp_dan_dcs_kode_sama_dan_sama_dengan_register(
    client: TestClient, partisipan_factory, db_session: Session
) -> None:
    pid = partisipan_factory("ko70-lintas")
    kode_wcp = _assign(client, "wcp", [pid])[0]["kode_orang"]
    kode_dcs = _assign(client, "dcs", [pid])[0]["kode_orang"]
    assert kode_wcp == kode_dcs
    assert _svc(db_session).peta_partisipan([pid]) == {pid: kode_wcp}
    rid = client.get("/api/v1/dcs/responden").json()["items"][0]["id"]
    assert client.get(f"/api/v1/dcs/responden/{rid}").json()["kode_orang"] == kode_wcp


def test_peta_partisipan_kosong_dan_id_tak_dikenal(db_session: Session) -> None:
    svc = _svc(db_session)
    assert svc.peta_partisipan([]) == {}
    assert svc.peta_partisipan(["par_tidak_ada"]) == {}


def test_peta_partisipan_tanpa_efek_tulis(db_session: Session, partisipan_factory) -> None:
    pid = partisipan_factory("ko70-readonly")
    svc = _svc(db_session)
    assert svc.peta_partisipan([pid]) == {}
    assert svc.peta_partisipan([pid, pid]) == {}
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(RedesainKodeOrangModel)
            .where(RedesainKodeOrangModel.partisipan_id == pid)
        )
        == 0
    )


def test_seed_backfill_idempoten(
    client: TestClient, partisipan_factory, db_session: Session
) -> None:
    from anjab_abk_backend.models import WcpRespondenModel

    pid = partisipan_factory("ko70-backfill")
    # Responden lama (sebelum fitur ini): baris ada, kode orang belum.
    db_session.add(WcpRespondenModel(id="wrsp_ko70bf", jabatan_label="X", partisipan_id=pid))
    db_session.flush()
    assert _svc(db_session).peta_partisipan([pid]) == {}
    seed_kode_orang_responden(db_session)
    kode = _svc(db_session).peta_partisipan([pid])[pid]
    jumlah = db_session.scalar(select(func.count()).select_from(RedesainKodeOrangModel))
    assert seed_kode_orang_responden(db_session) == 0
    assert db_session.scalar(select(func.count()).select_from(RedesainKodeOrangModel)) == jumlah
    assert _svc(db_session).peta_partisipan([pid])[pid] == kode


def test_openapi_tanpa_properti_nama_pada_responden_read(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    ditemui = 0
    for nama_skema, skema in schemas.items():
        if nama_skema.endswith("RespondenRead") and "Hasil" not in nama_skema:
            ditemui += 1
            assert "nama" not in skema["properties"], nama_skema
            assert "kode_orang" in skema["properties"], nama_skema
    assert ditemui >= 4
    assert "responden_nama" not in schemas["TiUsulanReviewRead"]["properties"]
    assert "responden_kode_orang" in schemas["TiUsulanReviewRead"]["properties"]
