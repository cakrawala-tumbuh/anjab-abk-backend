"""Test endpoint usulan uraian tugas tambahan dari partisipan Tahap 1 (backlog #26)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/task-inventory"
SESI = f"{BASE}/sesi"
TP_BASE = f"{BASE}/tugas-pokok"
DT_BASE = f"{BASE}/detil-tugas"
JABATAN_BASE = "/api/v1/jabatan"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _uniq(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _create_jabatan(client: TestClient, nama: str | None = None) -> dict:
    kode = _uniq("JBT")
    payload = {
        "kode": kode,
        "nama": nama or f"Jabatan {_uniq()}",
        "jenis": "fungsional",
        "aktif": True,
    }
    r = client.post(JABATAN_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_tp(client: TestClient, jabatan_ids: list[str], nama: str | None = None) -> dict:
    payload = {"jabatan_ids": jabatan_ids, "nama": nama or f"Tugas Pokok {_uniq()}"}
    r = client.post(TP_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_dt(
    client: TestClient, tugas_pokok_id: str, jabatan_ids: list[str], nama: str | None = None
) -> dict:
    payload = {
        "nama": nama or f"Detil Tugas {_uniq()}",
        "tugas_pokok_id": tugas_pokok_id,
        "jabatan_ids": jabatan_ids,
    }
    r = client.post(DT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_sesi(client: TestClient, jabatan_id: str, **over) -> dict:
    payload = {"jabatan_id": jabatan_id, "cabang": "Bandung"}
    payload.update(over)
    r = client.post(SESI, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _add_responden(client: TestClient, sesi_id: str, **over) -> dict:
    payload = {"nama": "Responden"}
    payload.update(over)
    r = client.post(f"{SESI}/{sesi_id}/responden", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _tp_dt_for_jabatan(client: TestClient, jabatan_id: str) -> tuple[str, str]:
    """Tugas pokok + detil tugas yang valid untuk `jabatan_id` (dibuat dari nol)."""
    tp = _create_tp(client, jabatan_ids=[jabatan_id])
    dt = _create_dt(client, tp["id"], jabatan_ids=[jabatan_id])
    return tp["id"], dt["id"]


@pytest.fixture
def tp_dt(client: TestClient, jabatan_id_tk: str) -> tuple[str, str]:
    return _tp_dt_for_jabatan(client, jabatan_id_tk)


# --------------------------------------------------------------------------- #
# Positif: create, list, delete
# --------------------------------------------------------------------------- #


def test_usulan_create_and_list_ok(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={
            "tugas_pokok_id": tp_id,
            "detil_tugas_id": dt_id,
            "uraian": "Menyiapkan materi ajar tambahan untuk kelas inklusi.",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"].startswith("tius_")
    assert body["sesi_id"] == sesi["id"]
    assert body["responden_id"] == rsp["id"]
    assert body["tugas_pokok_id"] == tp_id
    assert body["tugas_pokok"]  # nama ter-resolve, bukan kosong
    assert body["detil_tugas_id"] == dt_id
    assert body["detil_tugas"]
    assert body["disetujui"] is None
    assert body["task_kode"] is None

    r_list = client.get(f"{SESI}/responden/{rsp['id']}/usulan")
    assert r_list.status_code == 200
    items = r_list.json()
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_usulan_create_tanpa_detil_tugas_ok(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    """detil_tugas_id opsional — usulan boleh hanya pada level tugas pokok."""
    tp_id, _ = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "uraian": "Tugas tambahan tanpa detil."},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["detil_tugas_id"] is None
    assert body["detil_tugas"] is None


def test_usulan_delete_removes_it(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])
    body = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "detil_tugas_id": dt_id, "uraian": "Usulan dihapus."},
    ).json()

    r_del = client.delete(f"{BASE}/usulan/{body['id']}")
    assert r_del.status_code == 204

    r_list = client.get(f"{SESI}/responden/{rsp['id']}/usulan")
    assert r_list.json() == []


# --------------------------------------------------------------------------- #
# Negatif: 422
# --------------------------------------------------------------------------- #


def test_usulan_rejected_when_sesi_not_tahap1(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)  # tetap DRAFT
    rsp = _add_responden(client, sesi["id"])

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "detil_tugas_id": dt_id, "uraian": "Usulan gagal."},
    )
    assert r.status_code == 422


def test_usulan_rejected_after_tahap1_submit(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])

    kodes_r = client.get(BASE + "/catalog", params={"unit": "ALL", "jabatan_id": jabatan_id_tk})
    kode = kodes_r.json()["items"][0]["kode"]
    client.put(f"{SESI}/responden/{rsp['id']}/seleksi", json={"task_kode": [kode]})
    r_submit = client.post(f"{SESI}/responden/{rsp['id']}/seleksi/submit")
    assert r_submit.status_code == 201, r_submit.text

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "detil_tugas_id": dt_id, "uraian": "Usulan gagal."},
    )
    assert r.status_code == 422


def test_usulan_rejected_tugas_pokok_wrong_jabatan(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])

    jbt_lain = _create_jabatan(client)
    tp_lain = _create_tp(client, jabatan_ids=[jbt_lain["id"]])

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_lain["id"], "uraian": "Tugas pokok jabatan lain."},
    )
    assert r.status_code == 422


def test_usulan_rejected_detil_tugas_wrong_parent(
    client: TestClient, jabatan_id_tk: str, tp_dt: tuple[str, str]
) -> None:
    tp_id, _dt_id = tp_dt
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = _add_responden(client, sesi["id"])

    tp_lain = _create_tp(client, jabatan_ids=[jabatan_id_tk])
    dt_lain = _create_dt(client, tp_lain["id"], jabatan_ids=[jabatan_id_tk])

    r = client.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={
            "tugas_pokok_id": tp_id,
            "detil_tugas_id": dt_lain["id"],
            "uraian": "Detil tugas bukan turunan tugas pokok ini.",
        },
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Otorisasi & not found
# --------------------------------------------------------------------------- #


def test_usulan_requires_auth(anon_client: TestClient, jabatan_id_tk: str) -> None:
    r = anon_client.post(
        f"{SESI}/responden/trsp_tidakada/usulan",
        json={"tugas_pokok_id": "titp_x", "uraian": "x"},
    )
    assert r.status_code == 401


def test_usulan_forbidden_for_non_owner(
    client: TestClient,
    client_as,
    partisipan_factory,
    jabatan_id_tk: str,
    tp_dt: tuple[str, str],
    db_session,
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService

    tp_id, dt_id = tp_dt
    par_a = partisipan_factory("usulan-bola-a", jabatan_utama_id=jabatan_id_tk)
    par_b = partisipan_factory("usulan-bola-b", jabatan_utama_id=jabatan_id_tk)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id_tk))
    sme_svc.add_anggota(panel.id, par_a)
    sme_svc.add_anggota(panel.id, par_b)

    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    rsp = client.post(
        f"{SESI}/{sesi['id']}/responden", json={"partisipan_id": par_a, "nama": "A"}
    ).json()

    as_b = client_as("usulan-bola-b")
    r_forbidden = as_b.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "detil_tugas_id": dt_id, "uraian": "Bukan milik saya."},
    )
    assert r_forbidden.status_code == 403

    as_a = client_as("usulan-bola-a")
    r_ok = as_a.post(
        f"{SESI}/responden/{rsp['id']}/usulan",
        json={"tugas_pokok_id": tp_id, "detil_tugas_id": dt_id, "uraian": "Milik saya sendiri."},
    )
    assert r_ok.status_code == 201, r_ok.text
    usulan_id = r_ok.json()["id"]

    # `client_as` mengoverride verifier token pada `app` itu sendiri (bukan hanya
    # client yang dikembalikan) — panggil ulang untuk memastikan identitas terkini
    # sebelum tiap request, alih-alih mengandalkan client_as lama.
    as_b_lagi = client_as("usulan-bola-b")
    r_del_forbidden = as_b_lagi.delete(f"{BASE}/usulan/{usulan_id}")
    assert r_del_forbidden.status_code == 403

    as_a_lagi = client_as("usulan-bola-a")
    r_del_ok = as_a_lagi.delete(f"{BASE}/usulan/{usulan_id}")
    assert r_del_ok.status_code == 204


def test_usulan_responden_not_found(client: TestClient) -> None:
    r = client.post(
        f"{SESI}/responden/trsp_tidakada/usulan",
        json={"tugas_pokok_id": "titp_x", "uraian": "x"},
    )
    assert r.status_code == 404

    r_get = client.get(f"{SESI}/responden/trsp_tidakada/usulan")
    assert r_get.status_code == 404


def test_usulan_not_found_on_delete(client: TestClient) -> None:
    r = client.delete(f"{BASE}/usulan/tius_tidakada")
    assert r.status_code == 404
