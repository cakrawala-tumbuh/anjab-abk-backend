"""Test endpoint WCP: responden (penugasan langsung), jawaban, dan kuesioner saya."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

RSP_BASE = "/api/v1/wcp/responden"
INSTRUMEN_BASE = "/api/v1/wcp/instrumen"
DIM_BASE = "/api/v1/wcp/dimensi"
WCP_KUESIONER_BASE = "/api/v1/wcp/kuesioner"

_ALL_ITEM_IDS: list[str] = []


def _get_all_item_ids(client: TestClient) -> list[str]:
    global _ALL_ITEM_IDS
    if _ALL_ITEM_IDS:
        return _ALL_ITEM_IDS
    for dim in client.get(DIM_BASE).json():
        r = client.get(f"{DIM_BASE}/{dim['kode']}/items")
        _ALL_ITEM_IDS.extend(i["item_id"] for i in r.json())
    return _ALL_ITEM_IDS


def _assign_raw(client: TestClient, partisipan_ids: list[str]) -> dict:
    r = client.post(RSP_BASE, json={"partisipan_ids": partisipan_ids})
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client: TestClient, partisipan_ids: list[str]) -> list[dict]:
    """Assign dan kembalikan hanya daftar `created` (kasus umum: semua sukses)."""
    return _assign_raw(client, partisipan_ids)["created"]


def _save_draft(client: TestClient, responden_id: str, jawaban: list[dict]) -> None:
    r = client.put(f"{RSP_BASE}/{responden_id}/jawaban", json={"jawaban": jawaban})
    assert r.status_code == 200


def _submit(client: TestClient, responden_id: str, skor: int = 4) -> None:
    item_ids = _get_all_item_ids(client)
    _save_draft(client, responden_id, [{"item_id": iid, "skor_raw": skor} for iid in item_ids])
    r = client.post(f"{RSP_BASE}/{responden_id}/jawaban/submit")
    assert r.status_code == 201


@pytest.fixture
def par_a(partisipan_factory) -> str:
    return partisipan_factory("wcp-rsp-a")


# --- GET/POST /wcp/responden ---


def test_list_responden_empty(client: TestClient) -> None:
    r = client.get(RSP_BASE)
    assert r.status_code == 200
    assert r.json() == []


def test_list_responden_after_create(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory("wcp-rsp-la"), partisipan_factory("wcp-rsp-lb")]
    _assign(client, ids)
    r = client.get(RSP_BASE)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_responden_requires_admin(anon_client: TestClient) -> None:
    r = anon_client.get(RSP_BASE)
    assert r.status_code == 401


def test_create_responden_bulk_5_dalam_satu_request(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory(f"wcp-bulk-{i}") for i in range(5)]
    data = _assign_raw(client, ids)
    assert len(data["created"]) == 5
    assert {c["partisipan_id"] for c in data["created"]} == set(ids)
    assert data["skipped"] == []


def test_create_responden_partisipan_sudah_terdaftar_di_skip(
    client: TestClient, par_a: str
) -> None:
    """Partisipan yang sama tidak boleh menjadi responden WCP lebih dari satu kali —
    dilaporkan lewat `skipped`, bukan hilang/409."""
    _assign(client, [par_a])
    data = _assign_raw(client, [par_a])
    assert data["created"] == []
    assert data["skipped"] == [{"partisipan_id": par_a, "alasan": "sudah_terdaftar"}]


def test_create_responden_partisipan_duplikat_dalam_satu_request_di_skip(
    client: TestClient, par_a: str
) -> None:
    data = _assign_raw(client, [par_a, par_a])
    assert len(data["created"]) == 1
    assert data["created"][0]["partisipan_id"] == par_a
    assert data["skipped"] == [{"partisipan_id": par_a, "alasan": "duplikat_input"}]


def test_create_responden_bulk_sebagian_sudah_terdaftar(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory(f"wcp-partial-{i}") for i in range(3)]
    _assign(client, ids[:2])
    data = _assign_raw(client, ids)
    assert {c["partisipan_id"] for c in data["created"]} == {ids[2]}
    assert {s["partisipan_id"] for s in data["skipped"]} == set(ids[:2])
    assert all(s["alasan"] == "sudah_terdaftar" for s in data["skipped"])


def test_create_responden_bulk_semua_sudah_terdaftar_tetap_201(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory(f"wcp-allskip-{i}") for i in range(2)]
    _assign(client, ids)
    data = _assign_raw(client, ids)
    assert data["created"] == []
    assert len(data["skipped"]) == 2
    assert {s["partisipan_id"] for s in data["skipped"]} == set(ids)
    assert all(s["alasan"] == "sudah_terdaftar" for s in data["skipped"])


def test_create_responden_saat_closed_ditolak(client: TestClient, par_a: str) -> None:
    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.post(RSP_BASE, json={"partisipan_ids": [par_a]})
    assert r.status_code == 409


def test_tidak_ada_lagi_batas_atas_jumlah_responden(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory(f"wcp-nomax-{i}") for i in range(12)]
    created = _assign(client, ids)
    assert len(created) == 12
    assert {c["partisipan_id"] for c in created} == set(ids)


# --- DELETE /wcp/responden/{id} ---


def test_delete_responden_not_submitted(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    r = client.delete(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 204
    assert client.get(f"{RSP_BASE}/{rsp['id']}").status_code == 404


def test_delete_responden_after_submit_rejected(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _submit(client, rsp["id"])
    r = client.delete(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 422


def test_delete_responden_requires_auth(
    anon_client: TestClient, client: TestClient, par_a: str
) -> None:
    rsp = _assign(client, [par_a])[0]
    r = anon_client.delete(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 401


def test_delete_responden_not_found(client: TestClient) -> None:
    r = client.delete(f"{RSP_BASE}/wrsp_tidakada")
    assert r.status_code == 404


# --- GET /wcp/responden/{id}/jawaban ---


def test_list_jawaban_before_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    r = client.get(f"{RSP_BASE}/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert r.json() == []


def test_list_jawaban_after_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _submit(client, rsp["id"])
    r = client.get(f"{RSP_BASE}/{rsp['id']}/jawaban")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 72
    assert all(j["responden_id"] == rsp["id"] for j in data)


def test_list_jawaban_responden_not_found(client: TestClient) -> None:
    r = client.get(f"{RSP_BASE}/wrsp_tidakada/jawaban")
    assert r.status_code == 404


def test_list_jawaban_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{RSP_BASE}/wrsp_tidakada/jawaban")
    assert r.status_code == 401


# --- PUT .../jawaban (draft-save) & POST .../jawaban/submit ---


def test_save_draft_jawaban_parsial_lalu_lengkap(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    item_ids = _get_all_item_ids(client)
    sebagian = [{"item_id": iid, "skor_raw": 4} for iid in item_ids[:10]]
    r = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": sebagian})
    assert r.status_code == 200
    assert len(r.json()) == 10

    sisanya = [{"item_id": iid, "skor_raw": 4} for iid in item_ids[10:]]
    r2 = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": sisanya})
    assert r2.status_code == 200

    r_submit = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r_submit.status_code == 201
    assert len(r_submit.json()) == 72

    responden = client.get(f"{RSP_BASE}/{rsp['id']}").json()
    assert responden["sudah_submit"] is True


def test_save_draft_jawaban_rejected_after_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _submit(client, rsp["id"])
    item_ids = _get_all_item_ids(client)
    r = client.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r.status_code == 422


def test_save_draft_rejected_saat_instrumen_closed(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    client.post(f"{INSTRUMEN_BASE}/tutup")
    item_ids = _get_all_item_ids(client)
    r = client.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r.status_code == 422


def test_submit_jawaban_rejected_when_incomplete(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    item_ids = _get_all_item_ids(client)
    _save_draft(client, rsp["id"], [{"item_id": iid, "skor_raw": 4} for iid in item_ids[:5]])
    r = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r.status_code == 422


def test_submit_rejected_saat_instrumen_closed(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    item_ids = _get_all_item_ids(client)
    _save_draft(client, rsp["id"], [{"item_id": iid, "skor_raw": 4} for iid in item_ids])
    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r.status_code == 422


def test_submit_jawaban_succeeds_without_body(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    item_ids = _get_all_item_ids(client)
    _save_draft(client, rsp["id"], [{"item_id": iid, "skor_raw": 4} for iid in item_ids])
    r = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r.status_code == 201
    assert len(r.json()) == 72


# --- GET /wcp/kuesioner/saya ---


def test_kuesioner_saya_tanpa_partisipan_wcp(client: TestClient) -> None:
    r = client.get(f"{WCP_KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_dengan_assignment_wcp(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_id = partisipan_factory("wcp-ksr-b")
    # `client_as` mengoverride verifier pada `app` bersama (lihat conftest.py) — jalankan
    # SEMUA aksi admin lewat `client` DULU, baru pindah identitas via `client_as`.
    _assign(client, [par_id])
    as_p = client_as("wcp-ksr-b")

    data = as_p.get(f"{WCP_KUESIONER_BASE}/saya").json()
    assert len(data) == 1
    assert data[0]["instrumen_status"] == "OPEN"
    assert data[0]["sudah_submit"] is False


def test_kuesioner_saya_kosong_saat_instrumen_closed(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_id = partisipan_factory("wcp-ksr-c")
    _assign(client, [par_id])
    client.post(f"{INSTRUMEN_BASE}/tutup")
    as_p = client_as("wcp-ksr-c")

    assert as_p.get(f"{WCP_KUESIONER_BASE}/saya").json() == []


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses responden
# WCP milik partisipan lain lewat penebakan responden_id.
# --------------------------------------------------------------------------- #


def test_get_responden_forbidden_for_non_owner(client: TestClient, client_as, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]

    as_other = client_as("wcp-bola-other", groups=["partisipan"])
    assert as_other.get(f"{RSP_BASE}/{rsp['id']}").status_code == 403

    as_owner = client_as("wcp-rsp-a")
    r = as_owner.get(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp["id"]


def test_save_draft_jawaban_forbidden_for_non_owner(
    client: TestClient, client_as, par_a: str
) -> None:
    rsp = _assign(client, [par_a])[0]
    item_ids = _get_all_item_ids(client)

    as_other = client_as("wcp-bola-other2", groups=["partisipan"])
    r = as_other.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r.status_code == 403


def test_list_responden_forbidden_for_non_admin(client_as) -> None:
    as_partisipan = client_as("wcp-bola-e")
    r = as_partisipan.get(RSP_BASE)
    assert r.status_code == 403


def test_admin_can_access_any_responden(client: TestClient, client_as, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]

    as_admin = client_as("wcp-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{RSP_BASE}/{rsp['id']}").status_code == 200
