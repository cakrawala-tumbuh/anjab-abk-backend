"""Test analisis OPM: transisi CLOSED→ANALYZED, agregasi mean/SD/flag, dan
fungsi murni `compute_hasil_sesi`."""

from __future__ import annotations

from _opm_common import _setup_jabatan_panel_ti, _uniq_periode
from fastapi.testclient import TestClient

from anjab_abk_backend.opm.schemas.sesi import OpmSesiRead, OpmSesiTaskRead
from anjab_abk_backend.opm.services.analisis import compute_hasil_sesi

SESI_BASE = "/api/v1/opm/sesi"


def _build_sesi(client: TestClient, jabatan_id: str, **over) -> tuple[dict, dict]:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id)
    payload = {
        "jabatan_id": ctx["jabatan_id"],
        "ti_sesi_id": ctx["ti_sesi_id"],
        "periode": _uniq_periode(),
        "min_responden": 2,
        "max_responden": 10,
    }
    payload.update(over)
    r = client.post(SESI_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json(), ctx


def _submit(
    client: TestClient,
    responden_id: str,
    kodes: list[str],
    imp: int,
    freq: int,
    crit: int,
) -> None:
    jawaban = [
        {"task_kode": k, "importance": imp, "frequency": freq, "criticality": crit} for k in kodes
    ]
    r = client.put(f"{SESI_BASE}/responden/{responden_id}/jawaban", json={"jawaban": jawaban})
    assert r.status_code == 200, r.text
    r2 = client.post(f"{SESI_BASE}/responden/{responden_id}/jawaban/submit")
    assert r2.status_code == 201, r2.text


def test_analisis_butuh_closed_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, _ctx = _build_sesi(client, jabatan_id_tk)
    r = client.post(f"{SESI_BASE}/{sesi['id']}/analisis")
    assert r.status_code == 422, r.text


def test_analisis_kurang_min_responden_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk, min_responden=2)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    _submit(client, responden[0]["id"], ctx["kodes"], 4, 3, 5)
    client.post(f"{SESI_BASE}/{sesi['id']}/tutup")
    r = client.post(f"{SESI_BASE}/{sesi['id']}/analisis")
    assert r.status_code == 422, r.text


def test_analisis_ok_dan_mean_sd_flag(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk, min_responden=2)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    assert len(responden) == 2
    _submit(client, responden[0]["id"], ctx["kodes"], 4, 3, 5)
    _submit(client, responden[1]["id"], ctx["kodes"], 4, 3, 5)
    client.post(f"{SESI_BASE}/{sesi['id']}/tutup")

    r = client.post(f"{SESI_BASE}/{sesi['id']}/analisis")
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["n_responden_submit"] == 2
    for task in hasil["tasks"]:
        assert task["mean_importance"] == 4.0
        assert task["mean_frequency"] == 3.0
        assert task["mean_criticality"] == 5.0
        assert task["sd_importance"] == 0.0
        assert task["selection_essential"] is True
        assert task["workload_essential"] is True
        assert task["prop_selection_essential"] == 1.0
        assert task["prop_workload_essential"] == 1.0

    r_status = client.get(f"{SESI_BASE}/{sesi['id']}")
    assert r_status.json()["status"] == "ANALYZED"


def test_hasil_sebelum_analyzed_422(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, _ctx = _build_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI_BASE}/{sesi['id']}/hasil")
    assert r.status_code == 422, r.text


def test_hasil_ok_setelah_analyzed(client: TestClient, jabatan_id_tk: str) -> None:
    sesi, ctx = _build_sesi(client, jabatan_id_tk, min_responden=2)
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    responden = client.get(f"{SESI_BASE}/{sesi['id']}/responden").json()
    _submit(client, responden[0]["id"], ctx["kodes"], 4, 3, 5)
    _submit(client, responden[1]["id"], ctx["kodes"], 2, 1, 1)
    client.post(f"{SESI_BASE}/{sesi['id']}/tutup")
    client.post(f"{SESI_BASE}/{sesi['id']}/analisis")

    r = client.get(f"{SESI_BASE}/{sesi['id']}/hasil")
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["n_responden_submit"] == 2
    for task in hasil["tasks"]:
        assert task["mean_importance"] == 3.0
        assert task["mean_frequency"] == 2.0
        assert task["mean_criticality"] == 3.0
        assert task["prop_selection_essential"] == 0.5
        assert task["prop_workload_essential"] == 0.5


# --- Fungsi murni compute_hasil_sesi ---


def _sesi_read(**over) -> OpmSesiRead:
    base = {
        "id": "opses_test",
        "jabatan_id": "jbt_test",
        "jabatan_nama": "Guru",
        "ti_sesi_id": "tises_test",
        "periode": "2026-06",
        "status": "ANALYZED",
        "min_responden": 1,
        "max_responden": 10,
        "jumlah_task": 1,
        "catatan": None,
        "created_at": "2026-06-01T00:00:00Z",
    }
    base.update(over)
    return OpmSesiRead.model_validate(base)


def _task_read(**over) -> OpmSesiTaskRead:
    base = {
        "task_kode": "K001",
        "uraian_tugas": "Mengajar",
        "tugas_pokok": "Pembelajaran",
        "detil_tugas": None,
        "urutan": 1,
    }
    base.update(over)
    return OpmSesiTaskRead.model_validate(base)


def test_compute_hasil_sesi_boundary_mean_importance_4_true() -> None:
    sesi = _sesi_read()
    tasks = [_task_read()]
    # mean_importance persis 4.0, mean_criticality rendah → selection_essential True.
    responden_raw = [
        ("r1", {"K001": (4, 1, 1)}),
        ("r2", {"K001": (4, 1, 1)}),
    ]
    hasil = compute_hasil_sesi(sesi, tasks, responden_raw)
    assert hasil.tasks[0].mean_importance == 4.0
    assert hasil.tasks[0].selection_essential is True


def test_compute_hasil_sesi_boundary_mean_criticality_399_false() -> None:
    sesi = _sesi_read()
    tasks = [_task_read()]
    # mean_criticality 3.99 (bukan 4.0 tepat) dan mean_importance < 4 → False.
    responden_raw = [
        ("r1", {"K001": (1, 1, 4)}),
        ("r2", {"K001": (1, 1, 4)}),
        ("r3", {"K001": (1, 1, 3.97)}),  # type: ignore[dict-item]
    ]
    hasil = compute_hasil_sesi(sesi, tasks, responden_raw)
    assert hasil.tasks[0].mean_criticality < 4.0
    assert hasil.tasks[0].selection_essential is False


# --------------------------------------------------------------------------- #
# Otorisasi (item 015): lapis 1 (admin murni) — `/analisis` dan `/hasil`.
#
# Guard berjalan sebagai dependency FastAPI sebelum badan endpoint dieksekusi,
# jadi ID sesi dummy cukup untuk menguji 401/403 (lihat pola serupa di
# `test_opm_sesi.py`).
# --------------------------------------------------------------------------- #

_DUMMY_SESI_ID = "opses_dummy"


def test_opm_analisis_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.post(f"{SESI_BASE}/{_DUMMY_SESI_ID}/analisis").status_code == 401


def test_opm_analisis_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-analisis")
    assert as_partisipan.post(f"{SESI_BASE}/{_DUMMY_SESI_ID}/analisis").status_code == 403


def test_opm_hasil_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(f"{SESI_BASE}/{_DUMMY_SESI_ID}/hasil").status_code == 401


def test_opm_hasil_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-hasil")
    assert as_partisipan.get(f"{SESI_BASE}/{_DUMMY_SESI_ID}/hasil").status_code == 403


def test_opm_admin_semua_endpoint_boleh(client: TestClient, jabatan_id_tk: str) -> None:
    """Admin tidak terhalang guard baru (item 015) di endpoint sesi/hasil OPM manapun."""
    sesi, ctx = _build_sesi(client, jabatan_id_tk, min_responden=1)
    sid = sesi["id"]

    assert client.get(SESI_BASE).status_code == 200
    r_search = client.post(f"{SESI_BASE}/search", json={"domain": [], "limit": 10, "offset": 0})
    assert r_search.status_code == 200
    assert client.get(f"{SESI_BASE}/{sid}").status_code == 200
    assert client.patch(f"{SESI_BASE}/{sid}", json={"catatan": "ok"}).status_code == 200
    assert client.get(f"{SESI_BASE}/{sid}/task").status_code == 200

    assert client.post(f"{SESI_BASE}/{sid}/buka").status_code == 200
    responden = client.get(f"{SESI_BASE}/{sid}/responden").json()
    _submit(client, responden[0]["id"], ctx["kodes"], 4, 3, 5)
    assert client.post(f"{SESI_BASE}/{sid}/tutup").status_code == 200
    assert client.post(f"{SESI_BASE}/{sid}/analisis").status_code == 200
    assert client.get(f"{SESI_BASE}/{sid}/hasil").status_code == 200
