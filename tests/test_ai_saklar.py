"""Test kill switch layanan AI: seam SQL, `ai_boleh_jalan`, dan tiga rute admin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.fitur import ai_boleh_jalan
from anjab_abk_backend.models import AiSaklarEventModel
from anjab_abk_backend.schemas.common import FiturKode

_U = "/api/v1/system/ai/saklar"
_ALASAN = {"alasan": "Insiden keluaran tak wajar"}


def _flag(app, hidup: bool) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, feature_ai_narrative_draft=hidup
    )


@pytest.fixture
def flag_hidup(app) -> None:
    _flag(app, True)


def test_matikan_lalu_hidupkan_dengan_flag_hidup(
    client: TestClient, flag_hidup: None, db_session: Session
) -> None:
    awal = client.get(_U).json()
    assert awal["boleh_jalan"] is True and awal["dimatikan"] is False and awal["flag_aktif"]
    m = client.post(f"{_U}/matikan", json=_ALASAN)
    assert m.status_code == 200
    assert m.json()["boleh_jalan"] is False and m.json()["dimatikan"] is True
    assert client.get(_U).json()["boleh_jalan"] is False
    h = client.post(f"{_U}/hidupkan", json={"alasan": "Insiden sudah ditangani"})
    assert h.json()["boleh_jalan"] is True and h.json()["dimatikan"] is False
    assert db_session.query(AiSaklarEventModel).count() == 2


def test_event_tercatat_aktor_dan_alasan_event_lama_tetap(
    client: TestClient, flag_hidup: None, db_session: Session
) -> None:
    client.post(f"{_U}/matikan", json=_ALASAN)
    pertama = db_session.query(AiSaklarEventModel).one()
    snap = (pertama.id, pertama.aksi, pertama.alasan, pertama.aktor, pertama.created_at)
    client.post(f"{_U}/hidupkan", json={"alasan": "Sudah aman kembali"})
    db_session.expire_all()
    rows = db_session.query(AiSaklarEventModel).order_by(AiSaklarEventModel.created_at).all()
    assert len(rows) == 2
    assert (rows[0].id, rows[0].aksi, rows[0].alasan, rows[0].aktor, rows[0].created_at) == snap
    assert rows[0].alasan == _ALASAN["alasan"] and rows[0].aktor


def test_flag_mati_boleh_jalan_false_di_semua_keadaan(
    client: TestClient, app, db_session: Session
) -> None:
    _flag(app, False)
    assert client.get(_U).json()["boleh_jalan"] is False
    assert client.post(f"{_U}/matikan", json=_ALASAN).json()["boleh_jalan"] is False
    h = client.post(f"{_U}/hidupkan", json=_ALASAN).json()
    assert h["boleh_jalan"] is False and h["dimatikan"] is False and h["flag_aktif"] is False
    assert ai_boleh_jalan(db_session, Settings(_env_file=None)) is False


def test_alasan_pendek_422_dan_aksi_berulang_409(client: TestClient, flag_hidup: None) -> None:
    assert client.post(f"{_U}/matikan", json={"alasan": "abc"}).status_code == 422
    assert client.post(f"{_U}/hidupkan", json=_ALASAN).status_code == 409  # belum dimatikan
    assert client.post(f"{_U}/matikan", json=_ALASAN).status_code == 200
    assert client.post(f"{_U}/matikan", json=_ALASAN).status_code == 409
    assert client.post(f"{_U}/hidupkan", json=_ALASAN).status_code == 200
    assert client.post(f"{_U}/hidupkan", json=_ALASAN).status_code == 409


def test_aktor_dari_token_bukan_body(client_as, flag_hidup: None, db_session: Session) -> None:
    admin = client_as("admin-sah", groups=["admin"])
    r = admin.post(f"{_U}/matikan", json={**_ALASAN, "aktor": "orang-lain"})
    assert r.status_code == 200 and r.json()["aktor"] == "admin-sah"
    assert db_session.query(AiSaklarEventModel).one().aktor == "admin-sah"


def test_non_admin_403_dan_tanpa_token_401(anon_client: TestClient, client_as) -> None:
    for m, path in (("get", ""), ("post", "/matikan"), ("post", "/hidupkan")):
        assert getattr(anon_client, m)(_U + path).status_code == 401
    biasa = client_as("biasa", groups=["partisipan"])
    assert biasa.get(_U).status_code == 403
    assert biasa.post(f"{_U}/matikan", json=_ALASAN).status_code == 403
    assert biasa.post(f"{_U}/hidupkan", json=_ALASAN).status_code == 403


def test_idempotency_key_mengulang_respons_pertama(
    client: TestClient, flag_hidup: None, db_session: Session
) -> None:
    h = {"Idempotency-Key": "k-saklar-1"}
    a = client.post(f"{_U}/matikan", json=_ALASAN, headers=h)
    b = client.post(f"{_U}/matikan", json=_ALASAN, headers=h)
    assert a.status_code == 200 and b.status_code == 200 and a.json() == b.json()
    assert db_session.query(AiSaklarEventModel).count() == 1


def test_saklar_mati_tidak_menggerbang_rute_lain(client: TestClient, flag_hidup: None) -> None:
    client.post(f"{_U}/matikan", json=_ALASAN)
    assert client.get("/api/v1/system/fitur").status_code == 200
    assert client.get("/api/v1/jenjang-pendidikan").status_code == 200


def test_ai_boleh_jalan_mengikuti_event(db_session: Session) -> None:
    from anjab_abk_backend.services.ai_saklar_sql import SqlSaklarAiService

    hidup = Settings(_env_file=None, feature_ai_narrative_draft=True)
    assert ai_boleh_jalan(db_session, hidup) is True
    svc = SqlSaklarAiService(db_session, hidup)
    svc.matikan(FiturKode.AI_NARRATIVE_DRAFT, "alasan uji", "t")
    assert ai_boleh_jalan(db_session, hidup) is False
    svc.hidupkan(FiturKode.AI_NARRATIVE_DRAFT, "alasan uji", "t")
    assert ai_boleh_jalan(db_session, hidup) is True


def test_galat_basis_data_ai_boleh_jalan_false() -> None:
    class SesiRusak:
        def scalars(self, *_a, **_k):
            raise OperationalError("SELECT", {}, Exception("db mati"))

    hidup = Settings(_env_file=None, feature_ai_narrative_draft=True)
    assert ai_boleh_jalan(SesiRusak(), hidup) is False  # type: ignore[arg-type]
