"""Test endpoint `OpmResponden` + submit jawaban + kuesioner/saya (OPM)."""

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

SESI_BASE = "/api/v1/opm/sesi"
KUESIONER_BASE = "/api/v1/opm"


def _build_sesi(client: TestClient, jabatan_id: str, **over) -> tuple[dict, dict]:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id)
    payload = {
        "jabatan_id": ctx["jabatan_id"],
        "ti_sesi_id": ctx["ti_sesi_id"],
        "periode": _uniq_periode(),
        "min_responden": 1,
        "max_responden": 10,
    }
    payload.update(over)
    r = client.post(SESI_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json(), ctx


def _bulk_payload(kodes: list[str], **override_item) -> dict:
    jawaban = []
    for kode in kodes:
        item = {"task_kode": kode, "importance": 4, "frequency": 3, "criticality": 5}
        item.update(override_item.get(kode, {}))
        jawaban.append(item)
    return {"jawaban": jawaban}


def _save_draft(client: TestClient, responden_id: str, payload: dict):
    return client.put(f"{SESI_BASE}/responden/{responden_id}/jawaban", json=payload)


def _submit(client: TestClient, responden_id: str, kodes: list[str] | None = None) -> None:
    if kodes is not None:
        r = _save_draft(client, responden_id, _bulk_payload(kodes))
        assert r.status_code == 200, r.text
    r2 = client.post(f"{SESI_BASE}/responden/{responden_id}/jawaban/submit")
    assert r2.status_code == 201, r2.text


def test_auto_responden_terisi(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI_BASE}/{sesi['id']}/responden")
    assert r.status_code == 200
    assert {x["partisipan_id"] for x in r.json()} == set(ctx["partisipan_ids"])


def test_tambah_manual_anggota_panel_ok(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    par3 = _buat_partisipan(client, ctx["jabatan_id"], "E")
    client.post(f"{SME_BASE}/{ctx['panel_id']}/anggota", json={"partisipan_id": par3})
    r = client.post(
        f"{SESI_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru", "partisipan_id": par3},
    )
    assert r.status_code == 201, r.text
    assert r.json()["partisipan_id"] == par3


def test_tambah_bukan_anggota_panel_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    luar = _buat_partisipan(client, ctx["jabatan_id"], "F")
    r = client.post(
        f"{SESI_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru", "partisipan_id": luar},
    )
    assert r.status_code == 422, r.text


def test_tambah_duplikat_409(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    r = client.post(
        f"{SESI_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru", "partisipan_id": ctx["partisipan_ids"][0]},
    )
    assert r.status_code == 409, r.text


def test_tambah_melebihi_max_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk, max_responden=2)
    par3 = _buat_partisipan(client, ctx["jabatan_id"], "G")
    client.post(f"{SME_BASE}/{ctx['panel_id']}/anggota", json={"partisipan_id": par3})
    r = client.post(
        f"{SESI_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru", "partisipan_id": par3},
    )
    assert r.status_code == 422, r.text


def test_hapus_belum_submit_204(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    r = client.delete(f"{SESI_BASE}/responden/{rid}")
    assert r.status_code == 204
    assert client.get(f"{SESI_BASE}/responden/{rid}").status_code == 404


def test_hapus_sudah_submit_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    _submit(client, rid, ctx["kodes"])
    r = client.delete(f"{SESI_BASE}/responden/{rid}")
    assert r.status_code == 422


def test_submit_jawaban_ok_dan_tandai_submit(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    r_draft = _save_draft(client, rid, _bulk_payload(ctx["kodes"]))
    assert r_draft.status_code == 200, r_draft.text
    r = client.post(f"{SESI_BASE}/responden/{rid}/jawaban/submit")
    assert r.status_code == 201, r.text
    jawaban = r.json()
    assert len(jawaban) == 2
    assert all(
        j["importance"] == 4 and j["frequency"] == 3 and j["criticality"] == 5 for j in jawaban
    )

    r_get = client.get(f"{SESI_BASE}/responden/{rid}")
    assert r_get.json()["sudah_submit"] is True
    assert r_get.json()["submitted_at"] is not None


def test_save_draft_sesi_bukan_open_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)  # masih DRAFT
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    r = _save_draft(client, rid, _bulk_payload(ctx["kodes"]))
    assert r.status_code == 422, r.text


def test_submit_dua_kali_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    _submit(client, rid, ctx["kodes"])
    r2 = client.post(f"{SESI_BASE}/responden/{rid}/jawaban/submit")
    assert r2.status_code == 422, r2.text


def test_submit_task_kurang_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    r_draft = _save_draft(client, rid, _bulk_payload(ctx["kodes"][:1]))
    assert r_draft.status_code == 200, r_draft.text
    r = client.post(f"{SESI_BASE}/responden/{rid}/jawaban/submit")
    assert r.status_code == 422, r.text


def test_submit_task_asing_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    payload = _bulk_payload(ctx["kodes"])
    payload["jawaban"].append(
        {"task_kode": "K_ASING", "importance": 1, "frequency": 1, "criticality": 1}
    )
    r = _save_draft(client, rid, payload)
    assert r.status_code == 422, r.text


def test_submit_skor_di_luar_rentang_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    payload = _bulk_payload(ctx["kodes"])
    payload["jawaban"][0]["importance"] = 6
    r = _save_draft(client, rid, payload)
    assert r.status_code == 422, r.text


def test_save_draft_jawaban_parsial_lalu_lengkap(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]

    r1 = _save_draft(client, rid, _bulk_payload(ctx["kodes"][:1]))
    assert r1.status_code == 200
    assert len(r1.json()) == 1

    r2 = _save_draft(client, rid, _bulk_payload(ctx["kodes"][1:]))
    assert r2.status_code == 200

    r_submit = client.post(f"{SESI_BASE}/responden/{rid}/jawaban/submit")
    assert r_submit.status_code == 201
    assert len(r_submit.json()) == 2

    assert client.get(f"{SESI_BASE}/responden/{rid}").json()["sudah_submit"] is True


def test_save_draft_jawaban_rejected_after_submit(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rid = responden[0]["id"]
    _submit(client, rid, ctx["kodes"])

    r = _save_draft(client, rid, _bulk_payload(ctx["kodes"]))
    assert r.status_code == 422


def test_kuesioner_saya_tanpa_partisipan(client: TestClient) -> None:
    r = client.get(f"{KUESIONER_BASE}/kuesioner/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_hanya_open(client: TestClient, jabatan_id_tk: str, db_session) -> None:
    """Assignment-based: kuesioner OPM hanya muncul untuk partisipan yang terhubung
    dan hanya saat sesi berstatus OPEN."""
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    par_service = SqlPartisipanService(db_session)
    par = par_service.create(
        PartisipanCreate(
            nama="Partisipan Kuesioner OPM",
            email=f"ksr_opm_{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_opm_dummy",
            jabatan_utama_id=jabatan_id_tk,
            masa_kerja_tahun=2,
        ),
        authentik_user_id="test-user",
    )

    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    panel_id = r.json()["id"]
    client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par.id})

    r_catalog = client.get(
        "/api/v1/task-inventory/catalog", params={"unit": "TK", "jabatan_id": jabatan_id_tk}
    )
    kodes = [it["kode"] for it in r_catalog.json()[:2]]

    r_ti = client.post(
        TI_SESI,
        json={"jabatan_id": jabatan_id_tk, "periode": _uniq_periode(), "min_responden": 1},
    )
    ti_sesi_id = r_ti.json()["id"]
    r_rsp = client.post(f"{TI_SESI}/{ti_sesi_id}/responden", json={"nama": "R1"})
    client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap1")
    r_rsp_id = r_rsp.json()["id"]
    client.put(f"{TI_SESI}/responden/{r_rsp_id}/seleksi", json={"task_kode": kodes})
    client.post(f"{TI_SESI}/responden/{r_rsp_id}/seleksi/submit")
    client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap2")
    client.post(f"{TI_SESI}/{ti_sesi_id}/mulai-tahap3")

    r_sesi = client.post(
        SESI_BASE,
        json={
            "jabatan_id": jabatan_id_tk,
            "ti_sesi_id": ti_sesi_id,
            "periode": _uniq_periode(),
            "min_responden": 1,
            "max_responden": 10,
        },
    )
    assert r_sesi.status_code == 201, r_sesi.text
    sesi_id = r_sesi.json()["id"]

    # Sesi masih DRAFT → kuesioner belum muncul meski responden sudah ada.
    r0 = client.get(f"{KUESIONER_BASE}/kuesioner/saya")
    assert r0.json() == []

    client.post(f"{SESI_BASE}/{sesi_id}/buka")
    r1 = client.get(f"{KUESIONER_BASE}/kuesioner/saya")
    assert r1.status_code == 200
    data = r1.json()
    assert len(data) == 1
    assert data[0]["sesi_id"] == sesi_id
    assert data[0]["sesi_status"] == "OPEN"
    assert data[0]["sudah_submit"] is False


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses responden
# OPM milik partisipan lain lewat penebakan responden_id.
# --------------------------------------------------------------------------- #


def _link_authentik_user(db_session, partisipan_id: str, subject: str) -> None:
    """Tautkan partisipan yang sudah ada ke `subject` login (untuk test kepemilikan)."""
    from anjab_abk_backend.models import PartisipanModel

    obj = db_session.get(PartisipanModel, partisipan_id)
    obj.authentik_user_id = subject
    db_session.flush()


def test_get_responden_forbidden_for_non_owner(
    client: TestClient, jabatan_id_tk: str, client_as, db_session
) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    par_a, par_b = ctx["partisipan_ids"]
    _link_authentik_user(db_session, par_a, "opm-bola-a")
    _link_authentik_user(db_session, par_b, "opm-bola-b")

    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rsp_a = next(r for r in responden if r["partisipan_id"] == par_a)

    as_b = client_as("opm-bola-b")
    assert as_b.get(f"{SESI_BASE}/responden/{rsp_a['id']}").status_code == 403

    as_a = client_as("opm-bola-a")
    r = as_a.get(f"{SESI_BASE}/responden/{rsp_a['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp_a["id"]


def test_save_draft_jawaban_forbidden_for_non_owner(
    client: TestClient, jabatan_id_tk: str, client_as, db_session
) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    par_a, par_b = ctx["partisipan_ids"]
    _link_authentik_user(db_session, par_a, "opm-bola-c")
    _link_authentik_user(db_session, par_b, "opm-bola-d")
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")

    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rsp_a = next(r for r in responden if r["partisipan_id"] == par_a)

    as_d = client_as("opm-bola-d")
    r = as_d.put(f"{SESI_BASE}/responden/{rsp_a['id']}/jawaban", json=_bulk_payload(ctx["kodes"]))
    assert r.status_code == 403


def test_list_responden_forbidden_for_non_admin(
    client: TestClient, jabatan_id_tk: str, client_as
) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    as_partisipan = client_as("opm-bola-e")
    r = as_partisipan.get(f"{SESI_BASE}/{sesi['id']}/responden")
    assert r.status_code == 403


def test_admin_can_access_any_responden(
    client: TestClient, jabatan_id_tk: str, client_as, db_session
) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk)
    par_a, _ = ctx["partisipan_ids"]
    _link_authentik_user(db_session, par_a, "opm-bola-f")

    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    rsp_a = next(r for r in responden if r["partisipan_id"] == par_a)

    as_admin = client_as("opm-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{SESI_BASE}/responden/{rsp_a['id']}").status_code == 200
