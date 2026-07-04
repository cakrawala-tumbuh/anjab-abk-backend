"""Test endpoint DCS: responden, jawaban, dan hasil (endpoint yang belum tercakup)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.dcs.seed import ITEM

SESI_BASE = "/api/v1/dcs/sesi"
RSP_BASE = "/api/v1/dcs/sesi"
WCP_SESI_BASE = "/api/v1/wcp/sesi"

ALL_ITEM_IDS = [item[0] for item in ITEM]


def _all_jawaban(skor: int = 3) -> list[dict]:
    return [{"item_id": iid, "skor_raw": skor} for iid in ALL_ITEM_IDS]


def _build_sesi(client: TestClient, min_responden: int = 2, max_responden: int = 4) -> dict:
    sesi = client.post(
        SESI_BASE,
        json={
            "periode": "2025-09",
            "min_responden": min_responden,
            "max_responden": max_responden,
        },
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    return client.get(f"{SESI_BASE}/{sesi['id']}").json()


def _add_responden(client: TestClient, sesi_id: str, partisipan_id: str | None = None) -> dict:
    body: dict = {"jabatan_label": "Guru Test"}
    if partisipan_id:
        body["partisipan_id"] = partisipan_id
    return client.post(f"{RSP_BASE}/{sesi_id}/responden", json=body).json()


def _submit(client: TestClient, responden_id: str, skor: int = 3) -> None:
    r = client.post(
        f"{RSP_BASE}/responden/{responden_id}/jawaban",
        json={"jawaban": _all_jawaban(skor)},
    )
    assert r.status_code == 201


@pytest.fixture
def open_sesi(client: TestClient) -> dict:
    return _build_sesi(client)


@pytest.fixture
def analyzed_sesi(client: TestClient) -> dict:
    sesi = _build_sesi(client)
    sesi_id = sesi["id"]
    for _ in range(2):
        rsp = _add_responden(client, sesi_id)
        _submit(client, rsp["id"])
    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    client.post(f"{SESI_BASE}/{sesi_id}/analisis")
    return client.get(f"{SESI_BASE}/{sesi_id}").json()


DCS_KUESIONER_BASE = "/api/v1/dcs/kuesioner"


# --- GET /{sesi_id}/responden ---


def test_list_responden_empty(client: TestClient, open_sesi: dict) -> None:
    r = client.get(f"{RSP_BASE}/{open_sesi['id']}/responden")
    assert r.status_code == 200
    assert r.json() == []


def test_list_responden_after_create(client: TestClient, open_sesi: dict) -> None:
    sesi_id = open_sesi["id"]
    _add_responden(client, sesi_id)
    _add_responden(client, sesi_id)
    r = client.get(f"{RSP_BASE}/{sesi_id}/responden")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(d["sesi_id"] == sesi_id for d in data)


def test_list_responden_sesi_not_found(client: TestClient) -> None:
    r = client.get(f"{RSP_BASE}/dses_tidakada/responden")
    assert r.status_code == 404


def test_list_responden_requires_admin(anon_client: TestClient) -> None:
    r = anon_client.get(f"{RSP_BASE}/dses_tidakada/responden")
    assert r.status_code == 401


# --- GET /responden/{responden_id} ---


def test_get_responden_ok(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.get(f"{RSP_BASE}/responden/{rsp['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == rsp["id"]
    assert data["sudah_submit"] is False


def test_get_responden_not_found(client: TestClient) -> None:
    r = client.get(f"{RSP_BASE}/responden/drsp_tidakada")
    assert r.status_code == 404


def test_get_responden_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{RSP_BASE}/responden/drsp_tidakada")
    assert r.status_code == 401


# --- DELETE /responden/{responden_id} ---


def test_delete_responden_not_submitted(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.delete(f"{RSP_BASE}/responden/{rsp['id']}")
    assert r.status_code == 204
    assert client.get(f"{RSP_BASE}/responden/{rsp['id']}").status_code == 404


def test_delete_responden_after_submit_rejected(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.delete(f"{RSP_BASE}/responden/{rsp['id']}")
    assert r.status_code in (400, 422)


def test_delete_responden_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    r = anon_client.delete(f"{RSP_BASE}/responden/{rsp['id']}")
    assert r.status_code == 401


def test_delete_responden_not_found(client: TestClient) -> None:
    r = client.delete(f"{RSP_BASE}/responden/drsp_tidakada")
    assert r.status_code == 404


# --- GET /responden/{responden_id}/jawaban ---


def test_list_jawaban_before_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.get(f"{RSP_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert r.json() == []


def test_list_jawaban_after_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.get(f"{RSP_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 42
    assert all(j["responden_id"] == rsp["id"] for j in data)
    item_ids = {j["item_id"] for j in data}
    assert item_ids == set(ALL_ITEM_IDS)


def test_list_jawaban_responden_not_found(client: TestClient) -> None:
    r = client.get(f"{RSP_BASE}/responden/drsp_tidakada/jawaban")
    assert r.status_code == 404


def test_list_jawaban_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{RSP_BASE}/responden/drsp_tidakada/jawaban")
    assert r.status_code == 401


# --- GET /{sesi_id}/hasil (sukses) ---


def test_get_hasil_sesi_success(client: TestClient, analyzed_sesi: dict) -> None:
    sesi_id = analyzed_sesi["id"]
    r = client.get(f"{SESI_BASE}/{sesi_id}/hasil")
    assert r.status_code == 200
    data = r.json()
    assert data["sesi_id"] == sesi_id
    assert data["n_responden"] == 2
    assert len(data["sub_skala"]) == 3
    assert data["risk_flag"] in ("HIGH", "MODERATE", "LOW")
    kode_list = {s["subskala_kode"] for s in data["sub_skala"]}
    assert kode_list == {"DEMAND", "CONTROL", "SUPPORT"}


def test_get_hasil_sesi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/dses_tidakada/hasil")
    assert r.status_code == 404


# --- POST /{sesi_id}/analisis?wcp_sesi_id=... (K-Index) ---


def test_analisis_dengan_wcp_sesi_k_index(client: TestClient) -> None:
    wcp_sesi = client.post(
        WCP_SESI_BASE,
        json={
            "periode": "2025-09",
            "min_responden": 2,
            "max_responden": 4,
        },
    ).json()
    wcp_sesi_id = wcp_sesi["id"]
    client.post(f"{WCP_SESI_BASE}/{wcp_sesi_id}/buka")

    all_wcp_item_ids: list[str] = []
    r = client.get("/api/v1/wcp/dimensi")
    for dim in r.json():
        r2 = client.get(f"/api/v1/wcp/dimensi/{dim['kode']}/items")
        all_wcp_item_ids.extend(i["item_id"] for i in r2.json())

    for _ in range(2):
        wcp_rsp = client.post(
            f"{WCP_SESI_BASE}/{wcp_sesi_id}/responden",
            json={"jabatan_label": "Guru WCP"},
        ).json()
        client.post(
            f"{WCP_SESI_BASE}/responden/{wcp_rsp['id']}/jawaban",
            json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in all_wcp_item_ids]},
        )

    client.post(f"{WCP_SESI_BASE}/{wcp_sesi_id}/tutup")
    client.post(f"{WCP_SESI_BASE}/{wcp_sesi_id}/analisis")

    dcs_sesi = _build_sesi(client)
    dcs_sesi_id = dcs_sesi["id"]
    for _ in range(2):
        rsp = _add_responden(client, dcs_sesi_id)
        _submit(client, rsp["id"])
    client.post(f"{SESI_BASE}/{dcs_sesi_id}/tutup")

    r = client.post(
        f"{SESI_BASE}/{dcs_sesi_id}/analisis",
        params={"wcp_sesi_id": wcp_sesi_id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["sesi_id"] == dcs_sesi_id
    assert data["k_index"] is not None
    assert 0.0 <= data["k_index"] <= 1.0


# --- partisipan_id pada responden ---


def test_create_responden_with_partisipan_id(client: TestClient, open_sesi: dict) -> None:
    par_id = f"par_{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru Sains", "partisipan_id": par_id},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["partisipan_id"] == par_id


def test_create_responden_without_partisipan_id(client: TestClient, open_sesi: dict) -> None:
    r = client.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru Seni"},
    )
    assert r.status_code == 201
    assert r.json()["partisipan_id"] is None


# --- constraint: 1 partisipan_id maksimal 1 responden DCS ---


def test_create_responden_partisipan_id_duplikat_ditolak(client: TestClient) -> None:
    par_id = f"par_{uuid.uuid4().hex[:8]}"
    sesi1 = _build_sesi(client)
    sesi2 = _build_sesi(client)

    # Daftarkan ke sesi pertama — harus berhasil.
    r1 = client.post(
        f"{RSP_BASE}/{sesi1['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_id},
    )
    assert r1.status_code == 201

    # Daftarkan ke sesi kedua dengan partisipan_id yang sama — harus ditolak (409).
    r2 = client.post(
        f"{RSP_BASE}/{sesi2['id']}/responden",
        json={"jabatan_label": "Guru B", "partisipan_id": par_id},
    )
    assert r2.status_code == 409


def test_create_responden_tanpa_partisipan_id_boleh_duplikat(client: TestClient) -> None:
    """Responden tanpa partisipan_id (anonim) boleh didaftarkan ke beberapa sesi."""
    sesi1 = _build_sesi(client)
    sesi2 = _build_sesi(client)

    r1 = client.post(
        f"{RSP_BASE}/{sesi1['id']}/responden",
        json={"jabatan_label": "Anonim A"},
    )
    assert r1.status_code == 201

    r2 = client.post(
        f"{RSP_BASE}/{sesi2['id']}/responden",
        json={"jabatan_label": "Anonim B"},
    )
    assert r2.status_code == 201


# --- GET /kuesioner/saya (DCS) ---


def test_kuesioner_saya_tanpa_partisipan(client: TestClient) -> None:
    r = client.get(f"{DCS_KUESIONER_BASE}/saya")
    assert r.status_code == 200


def test_kuesioner_saya_dengan_assignment(client: TestClient, db_session) -> None:
    """Assignment-based: kuesioner DCS muncul hanya setelah admin assign responden
    dengan partisipan_id; sesi tanpa assignment tidak muncul."""
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    par_service = SqlPartisipanService(db_session)

    par = par_service.create(
        PartisipanCreate(
            nama="Partisipan Kuesioner DCS",
            email=f"ksr_dcs_{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_dummy",
            jabatan_utama_id=f"jbt_{uuid.uuid4().hex[:8]}",
            masa_kerja_tahun=2,
        ),
        authentik_user_id="test-user",
    )

    # Buat sesi DCS dan buka.
    sesi = client.post(
        SESI_BASE,
        json={
            "periode": "2025-09",
            "min_responden": 2,
            "max_responden": 4,
        },
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    _build_sesi(client)  # sesi jabatan acak — tanpa assignment, tidak boleh muncul

    # Sebelum di-assign: kuesioner kosong.
    r = client.get(f"{DCS_KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []

    # Admin assign partisipan ke sesi (buat responden dengan partisipan_id).
    assign_r = client.post(
        f"{RSP_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru DCS", "partisipan_id": par.id},
    )
    assert assign_r.status_code == 201

    # Setelah di-assign: kuesioner muncul.
    r2 = client.get(f"{DCS_KUESIONER_BASE}/saya")
    assert r2.status_code == 200
    data = r2.json()
    assert len(data) == 1
    item = data[0]
    assert item["sesi_id"] == sesi["id"]
    assert item["sesi_status"] == "OPEN"
    assert item["sudah_submit"] is False

    # Idempoten: pemanggilan ulang tidak menggandakan entri.
    r3 = client.get(f"{DCS_KUESIONER_BASE}/saya")
    assert [i["id"] for i in r3.json()] == [item["id"]]


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses responden
# DCS milik partisipan lain lewat penebakan responden_id.
# --------------------------------------------------------------------------- #


def test_get_responden_forbidden_for_non_owner(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("dcs-bola-a")
    partisipan_factory("dcs-bola-b")
    rsp = client.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()

    as_b = client_as("dcs-bola-b")
    assert as_b.get(f"{RSP_BASE}/responden/{rsp['id']}").status_code == 403

    as_a = client_as("dcs-bola-a")
    r = as_a.get(f"{RSP_BASE}/responden/{rsp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp["id"]


def test_submit_jawaban_forbidden_for_non_owner(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("dcs-bola-c")
    partisipan_factory("dcs-bola-d")
    rsp = client.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()

    as_d = client_as("dcs-bola-d")
    r = as_d.post(
        f"{RSP_BASE}/responden/{rsp['id']}/jawaban",
        json={"jawaban": _all_jawaban()},
    )
    assert r.status_code == 403


def test_list_jawaban_forbidden_for_non_owner_allowed_for_owner_and_admin(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("dcs-bola-e")
    partisipan_factory("dcs-bola-f")
    rsp = client.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()
    _submit(client, rsp["id"])

    as_f = client_as("dcs-bola-f")
    assert as_f.get(f"{RSP_BASE}/responden/{rsp['id']}/jawaban").status_code == 403

    as_a = client_as("dcs-bola-e")
    r = as_a.get(f"{RSP_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert len(r.json()) == 42

    as_admin = client_as("dcs-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{RSP_BASE}/responden/{rsp['id']}/jawaban").status_code == 200


def test_list_responden_forbidden_for_non_admin(open_sesi: dict, client_as) -> None:
    as_partisipan = client_as("dcs-bola-g")
    r = as_partisipan.get(f"{RSP_BASE}/{open_sesi['id']}/responden")
    assert r.status_code == 403


def test_create_responden_forbidden_for_non_admin(open_sesi: dict, client_as) -> None:
    as_partisipan = client_as("dcs-bola-h")
    r = as_partisipan.post(
        f"{RSP_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru"},
    )
    assert r.status_code == 403
