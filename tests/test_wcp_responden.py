"""Test endpoint WCP: responden, jawaban, dan hasil (endpoint yang belum tercakup)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

SESI_BASE = "/api/v1/wcp/sesi"
DIM_BASE = "/api/v1/wcp/dimensi"

_ALL_ITEM_IDS: list[str] = []


def _get_all_item_ids(client: TestClient) -> list[str]:
    global _ALL_ITEM_IDS
    if _ALL_ITEM_IDS:
        return _ALL_ITEM_IDS
    for dim in client.get(DIM_BASE).json():
        r = client.get(f"{DIM_BASE}/{dim['kode']}/items")
        _ALL_ITEM_IDS.extend(i["item_id"] for i in r.json())
    return _ALL_ITEM_IDS


def _build_sesi(client: TestClient, min_responden: int = 2, max_responden: int = 4) -> dict:
    sesi = client.post(
        SESI_BASE,
        json={
            "periode": "2025-10",
            "min_responden": min_responden,
            "max_responden": max_responden,
        },
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    return client.get(f"{SESI_BASE}/{sesi['id']}").json()


def _add_responden(client: TestClient, sesi_id: str, label: str = "Guru") -> dict:
    return client.post(
        f"{SESI_BASE}/{sesi_id}/responden",
        json={"jabatan_label": label},
    ).json()


def _save_draft(client: TestClient, responden_id: str, jawaban: list[dict]) -> None:
    r = client.put(
        f"{SESI_BASE}/responden/{responden_id}/jawaban",
        json={"jawaban": jawaban},
    )
    assert r.status_code == 200


def _submit(client: TestClient, responden_id: str, skor: int = 4) -> None:
    item_ids = _get_all_item_ids(client)
    _save_draft(client, responden_id, [{"item_id": iid, "skor_raw": skor} for iid in item_ids])
    r = client.post(f"{SESI_BASE}/responden/{responden_id}/jawaban/submit")
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


# --- GET /{sesi_id}/responden ---


def test_list_responden_empty(client: TestClient, open_sesi: dict) -> None:
    r = client.get(f"{SESI_BASE}/{open_sesi['id']}/responden")
    assert r.status_code == 200
    assert r.json() == []


def test_list_responden_after_create(client: TestClient, open_sesi: dict) -> None:
    sesi_id = open_sesi["id"]
    _add_responden(client, sesi_id, "Guru A")
    _add_responden(client, sesi_id, "Guru B")
    r = client.get(f"{SESI_BASE}/{sesi_id}/responden")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(d["sesi_id"] == sesi_id for d in data)


def test_list_responden_sesi_not_found(client: TestClient) -> None:
    r = client.get(f"{SESI_BASE}/wses_tidakada/responden")
    assert r.status_code == 404


def test_list_responden_requires_admin(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/wses_tidakada/responden")
    assert r.status_code == 401


def test_create_responden_duplicate_partisipan_rejected(
    client: TestClient, open_sesi: dict
) -> None:
    """Partisipan yang sama tidak boleh menjadi responden WCP lebih dari satu kali."""
    par_id = f"par_{uuid.uuid4().hex[:8]}"
    r1 = client.post(
        f"{SESI_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_id},
    )
    assert r1.status_code == 201

    sesi2 = _build_sesi(client)
    r2 = client.post(
        f"{SESI_BASE}/{sesi2['id']}/responden",
        json={"jabatan_label": "Guru B", "partisipan_id": par_id},
    )
    assert r2.status_code == 409


# --- DELETE /responden/{responden_id} ---


def test_delete_responden_not_submitted(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code == 204
    assert client.get(f"{SESI_BASE}/responden/{rsp['id']}").status_code == 404


def test_delete_responden_after_submit_rejected(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code in (400, 422)


def test_delete_responden_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    r = anon_client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code == 401


def test_delete_responden_not_found(client: TestClient) -> None:
    r = client.delete(f"{SESI_BASE}/responden/wrsp_tidakada")
    assert r.status_code == 404


# --- GET /responden/{responden_id}/jawaban ---


def test_list_jawaban_before_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.get(f"{SESI_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert r.json() == []


def test_list_jawaban_after_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.get(f"{SESI_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 72
    assert all(j["responden_id"] == rsp["id"] for j in data)
    item_ids = {j["item_id"] for j in data}
    assert item_ids == set(_get_all_item_ids(client))


def test_list_jawaban_responden_not_found(client: TestClient) -> None:
    r = client.get(f"{SESI_BASE}/responden/wrsp_tidakada/jawaban")
    assert r.status_code == 404


def test_list_jawaban_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/responden/wrsp_tidakada/jawaban")
    assert r.status_code == 401


# --- PUT /responden/{responden_id}/jawaban (draft-save) & POST .../jawaban/submit ---


def test_save_draft_jawaban_parsial_lalu_lengkap(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    item_ids = _get_all_item_ids(client)
    sebagian = [{"item_id": iid, "skor_raw": 4} for iid in item_ids[:10]]
    r = client.put(f"{SESI_BASE}/responden/{rsp['id']}/jawaban", json={"jawaban": sebagian})
    assert r.status_code == 200
    assert len(r.json()) == 10

    sisanya = [{"item_id": iid, "skor_raw": 4} for iid in item_ids[10:]]
    r2 = client.put(f"{SESI_BASE}/responden/{rsp['id']}/jawaban", json={"jawaban": sisanya})
    assert r2.status_code == 200

    r_submit = client.post(f"{SESI_BASE}/responden/{rsp['id']}/jawaban/submit")
    assert r_submit.status_code == 201
    assert len(r_submit.json()) == 72

    responden = client.get(f"{SESI_BASE}/responden/{rsp['id']}").json()
    assert responden["sudah_submit"] is True


def test_save_draft_jawaban_rejected_after_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    item_ids = _get_all_item_ids(client)
    r = client.put(
        f"{SESI_BASE}/responden/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r.status_code == 422


def test_submit_jawaban_rejected_when_incomplete(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    item_ids = _get_all_item_ids(client)
    _save_draft(client, rsp["id"], [{"item_id": iid, "skor_raw": 4} for iid in item_ids[:5]])
    r = client.post(f"{SESI_BASE}/responden/{rsp['id']}/jawaban/submit")
    assert r.status_code == 422


def test_submit_jawaban_succeeds_without_body(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    item_ids = _get_all_item_ids(client)
    _save_draft(client, rsp["id"], [{"item_id": iid, "skor_raw": 4} for iid in item_ids])
    r = client.post(f"{SESI_BASE}/responden/{rsp['id']}/jawaban/submit")
    assert r.status_code == 201
    assert len(r.json()) == 72


# --- GET /{sesi_id}/hasil (sukses) ---


def test_get_hasil_sesi_success(client: TestClient, analyzed_sesi: dict) -> None:
    sesi_id = analyzed_sesi["id"]
    r = client.get(f"{SESI_BASE}/{sesi_id}/hasil")
    assert r.status_code == 200
    data = r.json()
    assert data["sesi_id"] == sesi_id
    assert data["n_responden"] == 2
    assert len(data["dimensi"]) == 12
    assert all(0.0 <= d["skor_mean"] <= 5.0 for d in data["dimensi"])


def test_get_hasil_sesi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/wses_tidakada/hasil")
    assert r.status_code == 404


def test_get_hasil_sesi_not_analyzed(client: TestClient) -> None:
    sesi = _build_sesi(client)
    r = client.get(f"{SESI_BASE}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)


# --- GET /kuesioner/saya (WCP) ---

WCP_KUESIONER_BASE = "/api/v1/wcp/kuesioner"


def test_kuesioner_saya_tanpa_partisipan_wcp(client: TestClient) -> None:
    r = client.get(f"{WCP_KUESIONER_BASE}/saya")
    assert r.status_code == 200


def test_kuesioner_saya_dengan_assignment_wcp(client: TestClient, db_session) -> None:
    """Assignment-based WCP: kuesioner muncul hanya setelah admin assign responden
    dengan partisipan_id; sesi tanpa assignment tidak muncul."""
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    par_service = SqlPartisipanService(db_session)

    par = par_service.create(
        PartisipanCreate(
            nama="Partisipan Kuesioner WCP",
            email=f"ksr_wcp_{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_dummy",
            jabatan_utama_id=f"jbt_{uuid.uuid4().hex[:8]}",
            masa_kerja_tahun=2,
        ),
        authentik_user_id="test-user",
    )

    sesi = client.post(
        SESI_BASE,
        json={
            "periode": "2025-10",
            "min_responden": 2,
            "max_responden": 4,
        },
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    _build_sesi(client)  # sesi jabatan acak — tanpa assignment, tidak boleh muncul

    # Sebelum di-assign: kuesioner kosong.
    r = client.get(f"{WCP_KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []

    # Admin assign partisipan ke sesi (buat responden dengan partisipan_id).
    assign_r = client.post(
        f"{SESI_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru WCP", "partisipan_id": par.id},
    )
    assert assign_r.status_code == 201

    # Setelah di-assign: kuesioner muncul.
    r2 = client.get(f"{WCP_KUESIONER_BASE}/saya")
    assert r2.status_code == 200
    data = r2.json()
    assert len(data) == 1
    item = data[0]
    assert item["sesi_id"] == sesi["id"]
    assert item["sesi_status"] == "OPEN"
    assert item["sudah_submit"] is False

    # Idempoten: pemanggilan ulang tidak menggandakan entri.
    r3 = client.get(f"{WCP_KUESIONER_BASE}/saya")
    assert [i["id"] for i in r3.json()] == [item["id"]]


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses responden
# WCP milik partisipan lain lewat penebakan responden_id.
# --------------------------------------------------------------------------- #


def test_get_responden_forbidden_for_non_owner(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("wcp-bola-a")
    partisipan_factory("wcp-bola-b")
    rsp = client.post(
        f"{SESI_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()

    as_b = client_as("wcp-bola-b")
    assert as_b.get(f"{SESI_BASE}/responden/{rsp['id']}").status_code == 403

    as_a = client_as("wcp-bola-a")
    r = as_a.get(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp["id"]


def test_save_draft_jawaban_forbidden_for_non_owner(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("wcp-bola-c")
    partisipan_factory("wcp-bola-d")
    rsp = client.post(
        f"{SESI_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()
    item_ids = _get_all_item_ids(client)

    as_d = client_as("wcp-bola-d")
    r = as_d.put(
        f"{SESI_BASE}/responden/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r.status_code == 403


def test_list_responden_forbidden_for_non_admin(open_sesi: dict, client_as) -> None:
    as_partisipan = client_as("wcp-bola-e")
    r = as_partisipan.get(f"{SESI_BASE}/{open_sesi['id']}/responden")
    assert r.status_code == 403


def test_admin_can_access_any_responden(
    client: TestClient, open_sesi: dict, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("wcp-bola-f")
    rsp = client.post(
        f"{SESI_BASE}/{open_sesi['id']}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_a},
    ).json()

    as_admin = client_as("wcp-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{SESI_BASE}/responden/{rsp['id']}").status_code == 200
