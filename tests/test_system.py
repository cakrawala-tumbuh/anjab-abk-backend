"""Test endpoint sistem: health, readiness, version, me, OpenAPI."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_ready(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_version(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/version")
    assert r.status_code == 200
    assert "version" in r.json()


def test_version_commit_default_unknown(anon_client: TestClient) -> None:
    from anjab_abk_backend import __version__

    r = anon_client.get("/api/v1/version")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__, "commit": "unknown"}


def test_version_commit_dari_settings(app, anon_client: TestClient) -> None:
    from anjab_abk_backend import __version__
    from anjab_abk_backend.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, app_build_commit="abc123"
    )
    r = anon_client.get("/api/v1/version")
    assert r.json()["commit"] == "abc123"
    assert r.json()["version"] == __version__


def test_health_dan_ready_tanpa_commit(anon_client: TestClient) -> None:
    assert "commit" not in anon_client.get("/api/v1/health").json()
    assert "commit" not in anon_client.get("/api/v1/ready").json()


def test_openapi_version_memakai_versirread(anon_client: TestClient) -> None:
    schema = anon_client.get("/openapi.json").json()
    ref = schema["paths"]["/api/v1/version"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert ref.endswith("/VersiRead")


def test_me_unauthorized(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_me_authorized(client: TestClient) -> None:
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    data = r.json()
    assert data["subject"] == "test-user"


def test_openapi_json(anon_client: TestClient) -> None:
    r = anon_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    assert schema["info"]["title"]


def test_swagger_docs(anon_client: TestClient) -> None:
    r = anon_client.get("/docs")
    assert r.status_code == 200


def test_redoc(anon_client: TestClient) -> None:
    r = anon_client.get("/redoc")
    assert r.status_code == 200


def test_request_id_header_present(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/health")
    assert "x-request-id" in r.headers


# --- Feature flag (backlog #68) ---

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402

from anjab_abk_backend.config import Settings, get_settings  # noqa: E402
from anjab_abk_backend.errors import install_exception_handlers  # noqa: E402
from anjab_abk_backend.fitur import FiturKode, fitur_aktif, require_fitur  # noqa: E402


def test_fitur_default_semua_mati() -> None:
    s = Settings(_env_file=None)
    assert [fitur_aktif(k, s) for k in FiturKode] == [False] * 6


def test_fitur_env_menghidupkan_satu_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_RESEARCH_EXPORT", "true")
    s = Settings(_env_file=None)
    assert fitur_aktif(FiturKode.RESEARCH_EXPORT, s) is True
    assert [k for k in FiturKode if fitur_aktif(k, s)] == [FiturKode.RESEARCH_EXPORT]


def test_fitur_endpoint_default(client: TestClient) -> None:
    r = client.get("/api/v1/system/fitur")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["kode"] for i in items] == [k.value for k in FiturKode]
    assert all(i["aktif"] is False for i in items)
    assert all(i["keterangan"] for i in items)


def test_fitur_endpoint_satu_flag_hidup(client: TestClient, app) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, feature_wcp_dcs_scoring=True
    )
    items = client.get("/api/v1/system/fitur").json()["items"]
    aktif = {i["kode"]: i["aktif"] for i in items}
    assert aktif["WCP_DCS_SCORING"] is True
    assert sum(aktif.values()) == 1


def test_fitur_endpoint_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get("/api/v1/system/fitur").status_code == 401


def _mini_app(settings: Settings) -> TestClient:
    a = FastAPI()
    install_exception_handlers(a)
    a.dependency_overrides[get_settings] = lambda: settings

    @a.get("/x", dependencies=[Depends(require_fitur(FiturKode.WCP_DCS_SCORING))])
    def x() -> dict:
        return {"ok": True}

    return TestClient(a)


def test_require_fitur_mati_409() -> None:
    r = _mini_app(Settings(_env_file=None)).get("/x")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "feature_disabled"
    assert "WCP_DCS_SCORING" in body["message"]


def test_require_fitur_hidup_lolos() -> None:
    r = _mini_app(Settings(_env_file=None, feature_wcp_dcs_scoring=True)).get("/x")
    assert r.status_code == 200


def _metode_operasi(methods: dict) -> dict:
    return {m: op for m, op in methods.items() if m in {"get", "post", "put", "patch", "delete"}}


def _punya_if_match(op: dict) -> bool:
    return any(
        p.get("in") == "header" and p.get("name", "").lower() == "if-match"
        for p in op.get("parameters", [])
    )


def _periksa_kontrak_etag(paths: dict) -> int:
    """Tegakkan aturan ETag pada skema; kembalikan jumlah path ber-If-Match."""
    n = 0
    for path, methods in paths.items():
        ops = _metode_operasi(methods)
        if not any(_punya_if_match(op) for op in ops.values()):
            continue
        n += 1
        assert "get" in ops, f"{path} ber-If-Match tetapi tidak punya GET"
        for m, op in ops.items():
            dua_xx = [r for k, r in op["responses"].items() if str(k).startswith("2")]
            if m == "get" or (m in {"patch", "put"} and _punya_if_match(op)):
                assert dua_xx, f"{m} {path} tanpa respons 2xx"
                for r in dua_xx:
                    assert "ETag" in r.get("headers", {}), f"{m} {path} tanpa header ETag"
            if m == "delete":
                for r in dua_xx:
                    assert "ETag" not in r.get("headers", {}), f"delete {path} memuat ETag"
    return n


def test_openapi_mendeklarasikan_etag_untuk_rute_if_match(anon_client: TestClient) -> None:
    paths = anon_client.get("/openapi.json").json()["paths"]
    assert _periksa_kontrak_etag(paths) > 0


def test_pemindai_etag_gagal_bila_path_if_match_tanpa_get() -> None:
    paths = {
        "/x/{id}": {
            "patch": {
                "parameters": [{"in": "header", "name": "If-Match"}],
                "responses": {"200": {"headers": {"ETag": {}}}},
            }
        }
    }
    with pytest.raises(AssertionError, match="tidak punya GET"):
        _periksa_kontrak_etag(paths)


def test_etag_wcp_instrumen_terkirim_sesuai_deklarasi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    resp = schema["paths"]["/api/v1/wcp/instrumen"]["get"]["responses"]["200"]
    assert "ETag" in resp["headers"]
    assert client.get("/api/v1/wcp/instrumen").headers.get("ETag")


def test_skema_db_di_head(client: TestClient) -> None:
    r = client.get("/api/v1/system/skema")
    assert r.status_code == 200
    b = r.json()
    assert b["selaras"] is True and b["selisih_model"] == [] and b["selisih_terbaca"] is True
    assert b["revisi_db"] == b["head_kode"] and len(b["head_kode"]) == 1


def test_skema_db_revisi_beda(client: TestClient, db_session) -> None:
    from sqlalchemy import text

    db_session.execute(text("UPDATE alembic_version SET version_num = 'revisi_lain'"))
    b = client.get("/api/v1/system/skema").json()
    assert b["selaras"] is False and b["revisi_db"] == ["revisi_lain"]


def test_skema_db_tabel_liar(client: TestClient, db_session) -> None:
    from sqlalchemy import text

    db_session.execute(text("CREATE TABLE tabel_liar_uji (id int)"))
    b = client.get("/api/v1/system/skema").json()
    assert "remove_table:tabel_liar_uji" in b["selisih_model"]


def test_skema_db_alembic_version_absen(client: TestClient, db_session) -> None:
    from sqlalchemy import text

    db_session.execute(text("DROP TABLE alembic_version"))
    r = client.get("/api/v1/system/skema")
    assert r.status_code == 200
    assert r.json()["revisi_db"] == [] and r.json()["selaras"] is False


def test_skema_db_otorisasi(anon_client: TestClient, client_as) -> None:
    assert anon_client.get("/api/v1/system/skema").status_code == 401
    assert client_as("biasa", groups=["partisipan"]).get("/api/v1/system/skema").status_code == 403


def test_skema_db_banding_gagal_bukan_500(client: TestClient, monkeypatch) -> None:
    from anjab_abk_backend.services import skema_db_sql

    def _rusak(_conn):
        raise RuntimeError("boom")

    monkeypatch.setattr(skema_db_sql, "_hitung_selisih", _rusak)
    r = client.get("/api/v1/system/skema")
    assert r.status_code == 200
    b = r.json()
    assert b["selisih_terbaca"] is False and b["selisih_model"] == []
