"""Test endpoint DCS: responden (penugasan langsung), jawaban, dan kuesioner saya."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.dcs.seed import ITEM

RSP_BASE = "/api/v1/dcs/responden"
INSTRUMEN_BASE = "/api/v1/dcs/instrumen"
DCS_KUESIONER_BASE = "/api/v1/dcs/kuesioner"

ALL_ITEM_IDS = [item[0] for item in ITEM]


def _all_jawaban(skor: int = 3) -> list[dict]:
    return [{"item_id": iid, "skor_raw": skor} for iid in ALL_ITEM_IDS]


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


def _submit(client: TestClient, responden_id: str, skor: int = 3) -> None:
    _save_draft(client, responden_id, _all_jawaban(skor))
    r = client.post(f"{RSP_BASE}/{responden_id}/jawaban/submit")
    assert r.status_code == 201


@pytest.fixture
def par_a(partisipan_factory) -> str:
    return partisipan_factory("dcs-rsp-a")


@pytest.fixture
def par_b(partisipan_factory) -> str:
    return partisipan_factory("dcs-rsp-b")


# --- GET/POST /dcs/responden ---


def test_list_responden_empty(client: TestClient) -> None:
    r = client.get(RSP_BASE)
    assert r.status_code == 200
    assert r.json() == []


def test_create_responden_bulk_5_dalam_satu_request(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory(f"dcs-bulk-{i}") for i in range(5)]
    data = _assign_raw(client, ids)
    assert len(data["created"]) == 5
    assert {c["partisipan_id"] for c in data["created"]} == set(ids)
    assert data["skipped"] == []

    r = client.get(RSP_BASE)
    assert len(r.json()) == 5


def test_create_responden_derives_nama_dan_jabatan_label(client: TestClient, par_a: str) -> None:
    created = _assign(client, [par_a])[0]
    assert created["partisipan_id"] == par_a
    assert created["nama"]
    assert created["jabatan_label"]
    assert created["sudah_submit"] is False


def test_list_responden_requires_admin(client_as) -> None:
    as_partisipan = client_as("dcs-rsp-nonadmin")
    r = as_partisipan.get(RSP_BASE)
    assert r.status_code == 403


def test_create_responden_forbidden_for_non_admin(client_as) -> None:
    as_partisipan = client_as("dcs-rsp-nonadmin2")
    r = as_partisipan.post(RSP_BASE, json={"partisipan_ids": ["par_x"]})
    assert r.status_code == 403


def test_create_responden_partisipan_duplikat_dalam_satu_request_di_skip(
    client: TestClient, par_a: str
) -> None:
    data = _assign_raw(client, [par_a, par_a])
    assert len(data["created"]) == 1
    assert data["created"][0]["partisipan_id"] == par_a
    assert data["skipped"] == [{"partisipan_id": par_a, "alasan": "duplikat_input"}]


def test_create_responden_partisipan_sudah_terdaftar_di_skip(
    client: TestClient, par_a: str
) -> None:
    _assign(client, [par_a])
    data = _assign_raw(client, [par_a])
    assert data["created"] == []
    assert data["skipped"] == [{"partisipan_id": par_a, "alasan": "sudah_terdaftar"}]


def test_create_responden_bulk_sebagian_sudah_terdaftar(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory(f"dcs-partial-{i}") for i in range(3)]
    _assign(client, ids[:2])
    data = _assign_raw(client, ids)
    assert {c["partisipan_id"] for c in data["created"]} == {ids[2]}
    assert {s["partisipan_id"] for s in data["skipped"]} == set(ids[:2])
    assert all(s["alasan"] == "sudah_terdaftar" for s in data["skipped"])


def test_create_responden_bulk_semua_sudah_terdaftar_tetap_201(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory(f"dcs-allskip-{i}") for i in range(2)]
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
    ids = [partisipan_factory(f"dcs-nomax-{i}") for i in range(12)]
    created = _assign(client, ids)
    assert len(created) == 12
    assert {c["partisipan_id"] for c in created} == set(ids)


# --- GET /dcs/responden/{id} ---


def test_get_responden_ok(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    r = client.get(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp["id"]


def test_get_responden_not_found(client: TestClient) -> None:
    r = client.get(f"{RSP_BASE}/drsp_tidakada")
    assert r.status_code == 404


def test_get_responden_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{RSP_BASE}/drsp_tidakada")
    assert r.status_code == 401


# --- DELETE /dcs/responden/{id} ---


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


def test_delete_responden_not_found(client: TestClient) -> None:
    r = client.delete(f"{RSP_BASE}/drsp_tidakada")
    assert r.status_code == 404


# --- Jawaban ---


def test_list_jawaban_before_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    r = client.get(f"{RSP_BASE}/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert r.json() == []


def test_save_draft_lalu_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    sebagian = _all_jawaban()[:10]
    r = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": sebagian})
    assert r.status_code == 200
    assert len(r.json()) == 10

    sisanya = _all_jawaban()[10:]
    r2 = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": sisanya})
    assert r2.status_code == 200

    r_submit = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r_submit.status_code == 201
    assert len(r_submit.json()) == 42

    responden = client.get(f"{RSP_BASE}/{rsp['id']}").json()
    assert responden["sudah_submit"] is True


def test_submit_incomplete_rejected(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _save_draft(client, rsp["id"], _all_jawaban()[:5])
    r = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r.status_code == 422


def test_save_draft_item_tidak_dikenal_ditolak(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    r = client.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": "TIDAK_ADA", "skor_raw": 3}]},
    )
    assert r.status_code == 409


def test_save_draft_rejected_after_submit(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _submit(client, rsp["id"])
    r = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": _all_jawaban()})
    assert r.status_code == 422


def test_save_draft_rejected_saat_instrumen_closed(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": _all_jawaban()})
    assert r.status_code == 422


def test_submit_rejected_saat_instrumen_closed(client: TestClient, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]
    _save_draft(client, rsp["id"], _all_jawaban())
    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.post(f"{RSP_BASE}/{rsp['id']}/jawaban/submit")
    assert r.status_code == 422


# --- GET /dcs/kuesioner/saya ---


def test_kuesioner_saya_tanpa_partisipan(client: TestClient) -> None:
    r = client.get(f"{DCS_KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_dengan_assignment(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_id = partisipan_factory("dcs-ksr-b")
    # `client_as` mengoverride verifier pada `app` bersama (lihat conftest.py) — jalankan
    # SEMUA aksi admin lewat `client` DULU, baru pindah identitas via `client_as`.
    _assign(client, [par_id])
    as_p = client_as("dcs-ksr-b")

    data = as_p.get(f"{DCS_KUESIONER_BASE}/saya").json()
    assert len(data) == 1
    assert data[0]["instrumen_status"] == "OPEN"
    assert data[0]["sudah_submit"] is False


def test_kuesioner_saya_kosong_saat_instrumen_closed(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_id = partisipan_factory("dcs-ksr-c")
    _assign(client, [par_id])
    client.post(f"{INSTRUMEN_BASE}/tutup")
    as_p = client_as("dcs-ksr-c")

    assert as_p.get(f"{DCS_KUESIONER_BASE}/saya").json() == []


# --- Otorisasi object-level (BOLA/IDOR) ---


def test_get_responden_forbidden_for_non_owner(client: TestClient, client_as, par_a: str) -> None:
    rsp = _assign(client, [par_a])[0]

    as_owner = client_as("dcs-rsp-a")
    r = as_owner.get(f"{RSP_BASE}/{rsp['id']}")
    assert r.status_code == 200

    as_other = client_as("dcs-bola-other", groups=["partisipan"])
    r2 = as_other.get(f"{RSP_BASE}/{rsp['id']}")
    assert r2.status_code == 403


def test_save_draft_jawaban_forbidden_for_non_owner(
    client: TestClient, client_as, par_a: str
) -> None:
    rsp = _assign(client, [par_a])[0]

    as_other = client_as("dcs-bola-other2", groups=["partisipan"])
    r = as_other.put(f"{RSP_BASE}/{rsp['id']}/jawaban", json={"jawaban": _all_jawaban()})
    assert r.status_code == 403
