"""Test endpoint `OpmSesi`: create (snapshot + auto-responden), CRUD, transisi, search."""

from __future__ import annotations

import uuid

from _opm_common import (
    SME_BASE,
    TI_SESI,
    _buat_partisipan,
    _setup_jabatan_panel_ti,
    _uniq_periode,
)
from fastapi.testclient import TestClient

BASE = "/api/v1/opm/sesi"


def _payload(jabatan_id: str, ti_sesi_id: str, **over) -> dict:
    payload = {
        "jabatan_id": jabatan_id,
        "ti_sesi_id": ti_sesi_id,
        "periode": _uniq_periode(),
        "min_responden": 1,
        "max_responden": 10,
    }
    payload.update(over)
    return payload


def test_create_sesi_ok(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r.status_code == 201, r.text
    sesi = r.json()
    assert sesi["id"].startswith("opses_")
    assert sesi["jabatan_id"] == ctx["jabatan_id"]
    assert sesi["ti_sesi_id"] == ctx["ti_sesi_id"]
    assert sesi["status"] == "DRAFT"
    assert sesi["jumlah_task"] == 2

    # Snapshot task = task_terpilih TI.
    rt = client.get(f"{BASE}/{sesi['id']}/task")
    assert rt.status_code == 200, rt.text
    task_kodes = {t["task_kode"] for t in rt.json()}
    assert task_kodes == set(ctx["kodes"])

    # Auto-responden = anggota panel.
    rr = client.get(f"{BASE}/{sesi['id']}/responden")
    assert rr.status_code == 200, rr.text
    responden = rr.json()
    assert len(responden) == 2
    assert {r["partisipan_id"] for r in responden} == set(ctx["partisipan_ids"])
    assert all(r["sudah_submit"] is False for r in responden)


def test_create_sesi_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_x"))
    assert r.status_code == 401


def test_create_sesi_tanpa_sme_panel(client: TestClient, jabatan_id_tk: str) -> None:
    # jabatan_id_tk belum tentu punya panel di transaksi test ini (rollback per-test).
    r = client.post(BASE, json=_payload(jabatan_id_tk, "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_panel_tanpa_anggota(client: TestClient, jabatan_id_tk: str) -> None:
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    assert r.status_code == 201, r.text
    r2 = client.post(BASE, json=_payload(jabatan_id_tk, "tises_tidakada"))
    assert r2.status_code == 422, r2.text


def test_create_sesi_jabatan_tidak_ada(client: TestClient) -> None:
    r = client.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_tidak_ada(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_jabatan_beda(client: TestClient, jabatan_id_tk: str, db_session) -> None:
    from anjab_abk_backend.models import TiSesiModel

    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    # Sesi TI untuk jabatan lain — disisipkan langsung (bukan via API) karena
    # create sesi TI mensyaratkan katalog task untuk jabatan tsb, yang tak relevan
    # di sini; cukup baris TiSesiModel dengan jabatan_id berbeda.
    other = TiSesiModel(
        id=f"tises_{uuid.uuid4().hex[:8]}",
        jabatan_id=f"jbt_{uuid.uuid4().hex[:8]}",
        periode=_uniq_periode(),
        status="DRAFT",
        min_responden=1,
        max_responden=10,
    )
    db_session.add(other)
    db_session.flush()
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], other.id))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_belum_frozen(client: TestClient, jabatan_id_tk: str) -> None:
    par_ctx_jabatan = jabatan_id_tk
    par1 = _buat_partisipan(client, par_ctx_jabatan, "C")
    par2 = _buat_partisipan(client, par_ctx_jabatan, "D")
    r = client.post(SME_BASE, json={"jabatan_id": par_ctx_jabatan})
    panel_id = r.json()["id"]
    for pid in (par1, par2):
        client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": pid})

    r_ti = client.post(
        TI_SESI,
        json={"jabatan_id": par_ctx_jabatan, "periode": _uniq_periode(), "min_responden": 1},
    )
    assert r_ti.status_code == 201, r_ti.text
    # Belum mulai-tahap1 sama sekali → task_frozen masih False.
    r = client.post(BASE, json=_payload(par_ctx_jabatan, r_ti.json()["id"]))
    assert r.status_code == 422, r.text


def test_create_sesi_conflict_jabatan_sudah_punya_sesi(
    client: TestClient, jabatan_id_tk: str
) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r1 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r1.status_code == 201, r1.text
    r2 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r2.status_code == 409, r2.text


def test_create_sesi_idempotency_replay(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    key = f"idem-{uuid.uuid4().hex[:8]}"
    payload = _payload(ctx["jabatan_id"], ctx["ti_sesi_id"])
    r1 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    r2 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == r1.json()["id"]


def test_update_delete_hanya_draft(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]

    r = client.patch(f"{BASE}/{sid}", json={"catatan": "revisi"})
    assert r.status_code == 200, r.text
    assert r.json()["catatan"] == "revisi"

    r_buka = client.post(f"{BASE}/{sid}/buka")
    assert r_buka.status_code == 200
    assert r_buka.json()["status"] == "OPEN"

    r_upd = client.patch(f"{BASE}/{sid}", json={"catatan": "gagal"})
    assert r_upd.status_code == 422

    r_del = client.delete(f"{BASE}/{sid}")
    assert r_del.status_code == 422


def test_delete_draft_ok(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    r = client.delete(f"{BASE}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{BASE}/{sesi['id']}").status_code == 404


def test_transisi_lengkap_dan_invalid(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]

    # Tutup sebelum buka → invalid.
    r_invalid = client.post(f"{BASE}/{sid}/tutup")
    assert r_invalid.status_code == 422

    r1 = client.post(f"{BASE}/{sid}/buka")
    assert r1.status_code == 200
    assert r1.json()["status"] == "OPEN"

    r2 = client.post(f"{BASE}/{sid}/tutup")
    assert r2.status_code == 200
    assert r2.json()["status"] == "CLOSED"

    # Buka lagi dari CLOSED → invalid.
    r3 = client.post(f"{BASE}/{sid}/buka")
    assert r3.status_code == 422


def test_search_domain(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["jabatan_id", "=", ctx["jabatan_id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert any(item["id"] == sesi["id"] for item in data["items"])


def test_get_sesi_not_found(client: TestClient) -> None:
    assert client.get(f"{BASE}/opses_tidakada").status_code == 404
