"""Test endpoint TsLog (log harian Time Study) — dikaitkan ke penugasan/partisipan."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE_PNG = "/api/v1/time-study/penugasan"


def _build_penugasan(client: TestClient, *, aktif: bool = True) -> dict:
    return client.post(
        BASE_PNG,
        json={"partisipan_id": f"par_{uuid.uuid4().hex[:8]}", "aktif": aktif},
    ).json()


def _log_payload(**overrides) -> dict:
    base = {
        "tanggal": "2025-06-01",
        "waktu_masuk": "07:30",
        "waktu_keluar": "16:00",
        "day_color": "GREEN",
        "menit_core": 200,
        "menit_character": 50,
        "menit_improve": 30,
        "menit_strategic": 20,
        "menit_admin": 20,
        "menit_recovery": 0,
    }
    base.update(overrides)
    return base


@pytest.fixture
def penugasan(client: TestClient) -> dict:
    return _build_penugasan(client)


def test_list_log_empty(client: TestClient, penugasan: dict) -> None:
    r = client.get(f"{BASE_PNG}/{penugasan['id']}/log")
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_create_log(client: TestClient, penugasan: dict) -> None:
    r = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["id"].startswith("tlog_")
    assert data["partisipan_id"] == penugasan["partisipan_id"]
    assert data["tanggal"] == "2025-06-01"
    assert data["day_color"] == "GREEN"


def test_create_log_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    png = _build_penugasan(client)
    r = anon_client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload())
    assert r.status_code == 401


def test_create_log_penugasan_not_found(client: TestClient) -> None:
    r = client.post(f"{BASE_PNG}/tpn_tidakada/log", json=_log_payload())
    assert r.status_code == 404


def test_create_log_penugasan_nonaktif_rejected(client: TestClient) -> None:
    png = _build_penugasan(client, aktif=False)
    r = client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload())
    assert r.status_code == 422


def test_create_log_after_deaktivasi_rejected(client: TestClient, penugasan: dict) -> None:
    """Log ditolak setelah penugasan yang tadinya aktif dinonaktifkan admin."""
    client.patch(f"{BASE_PNG}/{penugasan['id']}", json={"aktif": False})
    r = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload())
    assert r.status_code == 422


def test_create_log_duplicate_tanggal_rejected(client: TestClient, penugasan: dict) -> None:
    r1 = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload())
    assert r1.status_code == 201
    r2 = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload())
    assert r2.status_code == 409


def test_create_log_invalid_time_rejected(client: TestClient, penugasan: dict) -> None:
    """waktu_masuk >= waktu_keluar harus ditolak."""
    r = client.post(
        f"{BASE_PNG}/{penugasan['id']}/log",
        json=_log_payload(tanggal="2025-06-02", waktu_masuk="16:00", waktu_keluar="07:30"),
    )
    assert r.status_code in (400, 422)


def test_create_log_minutes_exceed_tolerance_rejected(client: TestClient, penugasan: dict) -> None:
    """Sum menit > work_minutes + 30 harus ditolak."""
    # waktu_masuk=07:30, waktu_keluar=16:00 → 510 menit; 510 + 30 = 540
    r = client.post(
        f"{BASE_PNG}/{penugasan['id']}/log",
        json=_log_payload(
            tanggal="2025-06-03",
            menit_core=300,
            menit_character=100,
            menit_improve=100,
            menit_strategic=100,
            menit_admin=0,
            menit_recovery=0,
        ),
    )
    assert r.status_code in (400, 422)


def test_get_log(client: TestClient, penugasan: dict) -> None:
    created = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload()).json()
    r = client.get(f"{BASE_PNG}/{penugasan['id']}/log/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_log_not_found(client: TestClient, penugasan: dict) -> None:
    r = client.get(f"{BASE_PNG}/{penugasan['id']}/log/tlog_tidakada")
    assert r.status_code == 404


def test_update_log(client: TestClient, penugasan: dict) -> None:
    created = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload()).json()
    r = client.patch(
        f"{BASE_PNG}/{penugasan['id']}/log/{created['id']}",
        json={"catatan": "Hari yang sibuk"},
    )
    assert r.status_code == 200
    assert r.json()["catatan"] == "Hari yang sibuk"


def test_update_log_after_deaktivasi_rejected(client: TestClient, penugasan: dict) -> None:
    created = client.post(f"{BASE_PNG}/{penugasan['id']}/log", json=_log_payload()).json()
    client.patch(f"{BASE_PNG}/{penugasan['id']}", json={"aktif": False})
    r = client.patch(
        f"{BASE_PNG}/{penugasan['id']}/log/{created['id']}",
        json={"catatan": "Harusnya ditolak"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses log Time
# Study milik partisipan lain lewat penebakan penugasan_id/log_id.
# --------------------------------------------------------------------------- #


def test_get_log_forbidden_for_non_owner(client: TestClient, client_as, partisipan_factory) -> None:
    par_a = partisipan_factory("ts-log-bola-a")
    partisipan_factory("ts-log-bola-b")
    png = client.post(BASE_PNG, json={"partisipan_id": par_a, "aktif": True}).json()
    created = client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload()).json()

    as_b = client_as("ts-log-bola-b")
    assert as_b.get(f"{BASE_PNG}/{png['id']}/log/{created['id']}").status_code == 403

    as_a = client_as("ts-log-bola-a")
    r = as_a.get(f"{BASE_PNG}/{png['id']}/log/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_list_log_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("ts-log-bola-c")
    partisipan_factory("ts-log-bola-d")
    png = client.post(BASE_PNG, json={"partisipan_id": par_a, "aktif": True}).json()
    client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload())

    as_d = client_as("ts-log-bola-d")
    assert as_d.get(f"{BASE_PNG}/{png['id']}/log").status_code == 403


def test_create_log_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("ts-log-bola-e")
    partisipan_factory("ts-log-bola-f")
    png = client.post(BASE_PNG, json={"partisipan_id": par_a, "aktif": True}).json()

    as_f = client_as("ts-log-bola-f")
    r = as_f.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload())
    assert r.status_code == 403


def test_update_log_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("ts-log-bola-g")
    partisipan_factory("ts-log-bola-h")
    png = client.post(BASE_PNG, json={"partisipan_id": par_a, "aktif": True}).json()
    created = client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload()).json()

    as_h = client_as("ts-log-bola-h")
    r = as_h.patch(
        f"{BASE_PNG}/{png['id']}/log/{created['id']}", json={"catatan": "Harusnya ditolak"}
    )
    assert r.status_code == 403


def test_admin_can_access_any_log(client: TestClient, client_as, partisipan_factory) -> None:
    par_a = partisipan_factory("ts-log-bola-i")
    png = client.post(BASE_PNG, json={"partisipan_id": par_a, "aktif": True}).json()
    created = client.post(f"{BASE_PNG}/{png['id']}/log", json=_log_payload()).json()

    as_admin = client_as("ts-log-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{BASE_PNG}/{png['id']}/log/{created['id']}").status_code == 200


def test_get_log_mismatched_penugasan_not_found(client: TestClient) -> None:
    """Log milik penugasan lain tidak boleh terlihat lewat path penugasan_id yang salah."""
    png1 = client.post(BASE_PNG, json={"partisipan_id": f"par_{uuid.uuid4().hex[:8]}"}).json()
    png2 = client.post(BASE_PNG, json={"partisipan_id": f"par_{uuid.uuid4().hex[:8]}"}).json()
    log2 = client.post(f"{BASE_PNG}/{png2['id']}/log", json=_log_payload()).json()

    r = client.get(f"{BASE_PNG}/{png1['id']}/log/{log2['id']}")
    assert r.status_code == 404
