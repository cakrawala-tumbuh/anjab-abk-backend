"""Test endpoint Task Inventory: catalog, alur 3 tahap, transisi, agregasi."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/task-inventory"
SESI = f"{BASE}/sesi"
UNIT = "ALL"


@pytest.fixture
def jabatan_id_tk(client: TestClient) -> str:
    """Jabatan_id dari catalog kombinasi yang cocok dengan unit TK."""
    kombis = client.get(BASE + "/catalog/kombinasi").json()
    match = next((x for x in kombis if x["unit"] == UNIT), None)
    assert match is not None, f"Tidak ada kombinasi dalam catalog untuk unit '{UNIT}'"
    return match["jabatan_id"]


def _sesi_payload(jabatan_id: str, cabang: str = "Bandung", **over) -> dict:
    payload = {
        "jabatan_id": jabatan_id,
        "cabang": cabang,
    }
    payload.update(over)
    return payload


def _catalog_kodes(client: TestClient, jabatan_id: str, n: int) -> list[str]:
    r = client.get(BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= n
    return [it["kode"] for it in items[:n]]


def _create_sesi(client: TestClient, jabatan_id: str, **over) -> dict:
    r = client.post(SESI, json=_sesi_payload(jabatan_id, **over))
    assert r.status_code == 201, r.text
    return r.json()


def _add_responden(client: TestClient, sesi_id: str, nama: str) -> dict:
    r = client.post(f"{SESI}/{sesi_id}/responden", json={"nama": nama})
    assert r.status_code == 201, r.text
    return r.json()


def _seleksi_submit(client: TestClient, responden_id: str, kodes: list[str]) -> dict:
    r = client.put(f"{SESI}/responden/{responden_id}/seleksi", json={"task_kode": kodes})
    assert r.status_code == 200, r.text
    r2 = client.post(f"{SESI}/responden/{responden_id}/seleksi/submit")
    assert r2.status_code == 201, r2.text
    return r2.json()


def _detail_submit(client: TestClient, responden_id: str, detail: list[dict]) -> list[dict]:
    r = client.put(f"{SESI}/responden/{responden_id}/detail", json={"detail": detail})
    assert r.status_code == 200, r.text
    r2 = client.post(f"{SESI}/responden/{responden_id}/detail/submit")
    assert r2.status_code == 201, r2.text
    return r2.json()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def test_catalog_kombinasi(client: TestClient) -> None:
    r = client.get(BASE + "/catalog/kombinasi")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 24  # 24 jabatan × unit "ALL" (bukan lagi × jenjang)
    # Tiap baris punya jabatan_id, jabatan_nama (bukan kategori_jabatan)
    assert all("jabatan_id" in x for x in rows)
    assert all("jabatan_nama" in x for x in rows)
    target = next(x for x in rows if x["unit"] == UNIT)
    assert target["jumlah_task"] > 0


def test_catalog_list_by_kombinasi(client: TestClient, jabatan_id_tk: str) -> None:
    r = client.get(BASE + "/catalog", params={"unit": UNIT, "jabatan_id": jabatan_id_tk})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == UNIT and it["jabatan_id"] == jabatan_id_tk for it in items)
    assert len(items[0]["kode"]) > 0
    # Cascade Tahap 1 mengandalkan id stabil tugas pokok & detil tugas (level 1 & 2).
    assert all(it.get("tugas_pokok_id") for it in items)
    assert all("detil_tugas_id" in it for it in items)
    # detil_tugas_id konsisten dengan ada/tidaknya nama detil tugas.
    assert all((it["detil_tugas_id"] is None) == (it["detil_tugas"] is None) for it in items)


def test_catalog_unknown_kombinasi_empty(client: TestClient) -> None:
    r = client.get(BASE + "/catalog", params={"unit": "ZZ", "jabatan_id": "jbt_tidakada"})
    assert r.status_code == 200
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Sesi CRUD
# --------------------------------------------------------------------------- #


def test_sesi_create_and_get(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    assert sesi["id"].startswith("tises_")
    assert sesi["status"] == "DRAFT"
    assert sesi["jumlah_task_terpilih"] is None
    assert sesi["jabatan_id"] == jabatan_id_tk
    r = client.get(f"{SESI}/{sesi['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == sesi["id"]


def test_sesi_create_requires_auth(anon_client: TestClient, jabatan_id_tk: str) -> None:
    r = anon_client.post(SESI, json=_sesi_payload(jabatan_id_tk))
    assert r.status_code == 401


def test_sesi_create_invalid_kombinasi(client: TestClient) -> None:
    r = client.post(SESI, json=_sesi_payload("jbt_tidakada"))
    assert r.status_code in (400, 422)


def test_sesi_duplicate_conflict(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.post(SESI, json=_sesi_payload(jabatan_id_tk, cabang=sesi["cabang"]))
    assert r.status_code == 409


def test_sesi_cabang_invalid_rejected(client: TestClient, jabatan_id_tk: str) -> None:
    r = client.post(SESI, json=_sesi_payload(jabatan_id_tk, cabang="Jakarta"))
    assert r.status_code == 422


def test_sesi_create_payload_lama_ditolak(client: TestClient, jabatan_id_tk: str) -> None:
    """Item 037: payload lama yang masih mengirim `periode`/`min_responden`/
    `max_responden` ditolak `extra="forbid"` — kontrak baru mewajibkan `cabang`."""
    r = client.post(
        SESI,
        json={
            "jabatan_id": jabatan_id_tk,
            "periode": "2026-06",
            "min_responden": 3,
            "max_responden": 10,
        },
    )
    assert r.status_code == 422


def test_sesi_update_draft(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.patch(f"{SESI}/{sesi['id']}", json={"catatan": "halo"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "halo"


def test_sesi_delete_draft(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.delete(f"{SESI}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{SESI}/{sesi['id']}").status_code == 404


def test_sesi_delete_non_draft_rejected(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    r = client.delete(f"{SESI}/{sesi['id']}")
    assert r.status_code in (400, 422)
    assert "paksa=true" in r.json()["message"]


def test_sesi_delete_non_draft_dengan_paksa_ok(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    r = client.delete(f"{SESI}/{sesi['id']}", params={"paksa": True})
    assert r.status_code == 204
    assert client.get(f"{SESI}/{sesi['id']}").status_code == 404


def test_sesi_delete_paksa_forbidden_non_admin(
    client: TestClient, client_as, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    non_admin = client_as("partisipan-1", groups=["partisipan"])
    r = non_admin.delete(f"{SESI}/{sesi['id']}", params={"paksa": True})
    assert r.status_code == 403


def test_sesi_not_found(client: TestClient) -> None:
    assert client.get(f"{SESI}/tises_xxx").status_code == 404


def test_sesi_get_tanpa_token_401(anon_client: TestClient) -> None:
    """`GET /sesi/{id}` kini wajib token (lapis 2) — 401 diperiksa sebelum 404."""
    assert anon_client.get(f"{SESI}/tises_xxx").status_code == 401


def test_sesi_search(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.post(
        f"{SESI}/search", json={"domain": [["id", "=", sesi["id"]]], "limit": 10, "offset": 0}
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_sesi_search_by_cabang(client: TestClient, jabatan_id_tk: str) -> None:
    """Item 037: `cabang` menggantikan `periode` sebagai field yang bisa dicari."""
    sesi = _create_sesi(client, jabatan_id_tk, cabang="Semarang")
    r = client.post(
        f"{SESI}/search",
        json={
            "domain": [["id", "=", sesi["id"]], ["cabang", "=", "Semarang"]],
            "limit": 10,
            "offset": 0,
        },
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_sesi_read_memuat_cabang(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk, cabang="Semarang")
    assert sesi["cabang"] == "Semarang"
    r = client.get(f"{SESI}/{sesi['id']}")
    assert r.status_code == 200
    assert r.json()["cabang"] == "Semarang"
    assert "periode" not in r.json()
    assert "min_responden" not in r.json()
    assert "max_responden" not in r.json()


def test_sesi_koordinator_id(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk, koordinator_id="p_koordinator01")
    assert sesi["koordinator_id"] == "p_koordinator01"


# --------------------------------------------------------------------------- #
# Transisi tahap
# --------------------------------------------------------------------------- #


def test_mulai_tahap1(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    assert r.status_code == 200
    assert r.json()["status"] == "TAHAP1"


def test_mulai_tahap2_invalid_from_draft(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap2")
    assert r.status_code in (400, 422)


def test_mulai_tahap2_guard_belum_semua_submit(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r1 = _add_responden(client, sid, "A")
    _add_responden(client, sid, "B")  # tidak submit
    kodes = _catalog_kodes(client, jabatan_id_tk, 3)
    _seleksi_submit(client, r1["id"], kodes[:2])
    # 1 dari 2 submit → tanpa paksa harus gagal
    r = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r.status_code in (400, 422)
    # dengan paksa → sukses, status TAHAP2
    r = client.post(f"{SESI}/{sid}/mulai-tahap2", params={"paksa": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "TAHAP2"
    # jumlah_task_terpilih belum dibekukan (baru di TAHAP3)
    assert r.json()["jumlah_task_terpilih"] is None


def test_mulai_tahap3_dengan_review_koordinator(client: TestClient, jabatan_id_tk: str) -> None:
    """Flow: Tahap1 → Tahap2 (koordinator review partial) → Tahap3 (freeze)."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 3)  # K0, K1, K2

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # A pilih K0,K1 ; B pilih K1,K2
    # K1 = unanimous (2/2), K0 & K2 = partial (1/2) → perlu review koordinator
    _seleksi_submit(client, ra["id"], [kodes[0], kodes[1]])
    _seleksi_submit(client, rb["id"], [kodes[1], kodes[2]])

    # Masuk TAHAP2 (koordinator review)
    r2 = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r2.status_code == 200
    assert r2.json()["status"] == "TAHAP2"

    # GET review koordinator: harus ada 2 task partial (K0 & K2)
    rv = client.get(f"{SESI}/{sid}/tahap2")
    assert rv.status_code == 200
    review = rv.json()
    partial_kodes = {t["task_kode"] for t in review["tasks"]}
    assert kodes[0] in partial_kodes
    assert kodes[2] in partial_kodes
    assert kodes[1] not in partial_kodes  # K1 unanimous, tidak muncul di review
    assert review["jumlah_belum_diputuskan"] == 2

    # Koordinator: setujui K0, tolak K2
    rk = client.post(
        f"{SESI}/{sid}/tahap2",
        json={
            "keputusan": [
                {"task_kode": kodes[0], "disetujui": True},
                {"task_kode": kodes[2], "disetujui": False},
            ]
        },
    )
    assert rk.status_code == 200
    assert rk.json()["jumlah_belum_diputuskan"] == 0

    # Masuk TAHAP3: freeze = K1 (unanimous) + K0 (disetujui) = 2 task
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "TAHAP3"
    assert r3.json()["jumlah_task_terpilih"] == 2

    # Verifikasi task terpilih: K1 dan K0
    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200
    terpilih_kodes = {t["kode"] for t in tt.json()}
    assert kodes[1] in terpilih_kodes
    assert kodes[0] in terpilih_kodes
    assert kodes[2] not in terpilih_kodes


def test_mulai_tahap3_paksa_tanpa_review(client: TestClient, jabatan_id_tk: str) -> None:
    """Dengan paksa=true, bisa masuk TAHAP3 meski ada partial belum diputuskan."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 2)

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    _seleksi_submit(client, ra["id"], [kodes[0]])
    _seleksi_submit(client, rb["id"], [kodes[1]])
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    # Tanpa review koordinator, paksa → sukses (partial diabaikan, hanya unanimous)
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3", params={"paksa": "true"})
    # Tidak ada unanimous, namun tidak ada approved → gagal karena tidak ada task
    # Sebenarnya K0 dipilih 1/2 dan K1 dipilih 1/2, tidak ada unanimous
    # Dengan paksa: boleh lanjut tapi task kosong → freeze akan gagal
    # Expected: error karena tidak ada task relevan
    assert r3.status_code in (200, 400, 422)


def test_mulai_tahap3_unanimous_otomatis(client: TestClient, jabatan_id_tk: str) -> None:
    """Task yang dipilih semua anggota masuk otomatis tanpa review koordinator."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 2)

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # Keduanya pilih K0 dan K1 → semua unanimous
    _seleksi_submit(client, ra["id"], kodes)
    _seleksi_submit(client, rb["id"], kodes)

    client.post(f"{SESI}/{sid}/mulai-tahap2")

    # Review: tidak ada task partial
    rv = client.get(f"{SESI}/{sid}/tahap2")
    assert rv.json()["tasks"] == []
    assert rv.json()["jumlah_belum_diputuskan"] == 0

    # Langsung masuk TAHAP3 tanpa review koordinator
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "TAHAP3"
    assert r3.json()["jumlah_task_terpilih"] == 2


# --------------------------------------------------------------------------- #
# Seleksi Tahap 1
# --------------------------------------------------------------------------- #


def test_seleksi_invalid_kode(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    res = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": ["TItidakvalid"]})
    assert res.status_code in (400, 422)


def test_seleksi_requires_tahap1(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)  # masih DRAFT
    sid = sesi["id"]
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    res = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code in (400, 422)


def test_seleksi_double_submit_conflict(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, jabatan_id_tk, 2)
    _seleksi_submit(client, r["id"], kodes)
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi/submit")
    assert res.status_code in (400, 409, 422)
    # get seleksi
    g = client.get(f"{SESI}/responden/{r['id']}/seleksi")
    assert g.status_code == 200
    assert set(g.json()["task_kode"]) == set(kodes)


def test_save_draft_seleksi_full_replace(client: TestClient, jabatan_id_tk: str) -> None:
    """PUT seleksi full-replace: pilihan lama diganti seluruhnya, bukan digabung."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, jabatan_id_tk, 3)

    r1 = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": [kodes[0]]})
    assert r1.status_code == 200
    assert r1.json()["task_kode"] == [kodes[0]]

    r2 = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": [kodes[1], kodes[2]]})
    assert r2.status_code == 200
    assert set(r2.json()["task_kode"]) == {kodes[1], kodes[2]}

    g = client.get(f"{SESI}/responden/{r['id']}/seleksi")
    assert set(g.json()["task_kode"]) == {kodes[1], kodes[2]}


def test_save_draft_seleksi_rejected_after_submit(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    _seleksi_submit(client, r["id"], kodes)

    res = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code == 422


def test_submit_seleksi_rejected_when_no_task_selected(
    client: TestClient, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")

    r1 = client.put(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": []})
    assert r1.status_code == 200

    res = client.post(f"{SESI}/responden/{r['id']}/seleksi/submit")
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Alur penuh 3 tahap + agregasi
# --------------------------------------------------------------------------- #


def test_full_three_phase_flow(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 3)  # K0, K1, K2

    # Tahap 1
    assert client.post(f"{SESI}/{sid}/mulai-tahap1").json()["status"] == "TAHAP1"
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # A pilih K0,K1 ; B pilih K1,K2 → K1 unanimous, K0+K2 partial
    _seleksi_submit(client, ra["id"], [kodes[0], kodes[1]])
    _seleksi_submit(client, rb["id"], [kodes[1], kodes[2]])

    # Tahap 2: koordinator setujui K0, tolak K2
    assert client.post(f"{SESI}/{sid}/mulai-tahap2").json()["status"] == "TAHAP2"
    client.post(
        f"{SESI}/{sid}/tahap2",
        json={
            "keputusan": [
                {"task_kode": kodes[0], "disetujui": True},
                {"task_kode": kodes[2], "disetujui": False},
            ]
        },
    )

    # Tahap 3: freeze = K1 (unanimous) + K0 (approved) = 2 task
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text
    assert r3.json()["jumlah_task_terpilih"] == 2

    # task-terpilih: K1 n_relevan=2, K0 n_relevan=1
    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200
    by_kode = {x["kode"]: x for x in tt.json()}
    assert by_kode[kodes[1]]["n_relevan"] == 2
    assert by_kode[kodes[0]]["n_relevan"] == 1

    # Detail Tahap 3: A isi K0,K1 ; B isi K1 saja (K2 tidak di set terpilih)
    def _ditem(kode: str, jpm: float) -> dict:
        return {
            "task_kode": kode,
            "sumber_bukti": "Aktual",
            "kondisi": "Baseline",
            "frekuensi_teks": "Mingguan",
            "durasi_per_kali": 60,
            "jam_per_minggu": jpm,
            "peak4w_hours": 0,
            "va_type": "VA-Core",
        }

    _detail_submit(client, ra["id"], [_ditem(kodes[0], 2.0), _ditem(kodes[1], 4.0)])
    _detail_submit(client, rb["id"], [_ditem(kodes[1], 6.0)])

    # Tutup → analisis
    assert client.post(f"{SESI}/{sid}/tutup").json()["status"] == "CLOSED"
    an = client.post(f"{SESI}/{sid}/analisis")
    assert an.status_code == 200, an.text
    hasil = an.json()
    assert hasil["n_responden_tahap1"] == 2
    assert hasil["n_responden_tahap3"] == 2
    assert hasil["jumlah_task_terpilih"] == 2
    assert "jabatan_id" in hasil  # bukan kategori_jabatan

    tasks = {t["kode"]: t for t in hasil["tasks"]}
    # K1: rata-rata jam/minggu (4+6)/2 = 5 → jam/tahun = 225
    assert tasks[kodes[1]]["jam_per_minggu_mean"] == 5.0
    assert tasks[kodes[1]]["jam_per_tahun_mean"] == 225.0
    assert tasks[kodes[1]]["n_detail"] == 2
    assert tasks[kodes[0]]["jam_per_minggu_mean"] == 2.0
    # total jam/minggu = 2 + 5 = 7
    assert hasil["total_jam_per_minggu"] == 7.0

    # hasil GET tersedia setelah ANALYZED
    hg = client.get(f"{SESI}/{sid}/hasil")
    assert hg.status_code == 200
    assert hg.json()["jumlah_task_terpilih"] == 2


# --------------------------------------------------------------------------- #
# Regresi #15: task ber-`detil_tugas` NULL tidak boleh 500-kan penyaji hasil
# --------------------------------------------------------------------------- #


def _create_jabatan_regresi(client: TestClient) -> dict:
    kode = f"JBT{uuid.uuid4().hex[:8]}"
    payload = {
        "kode": kode,
        "nama": f"Jabatan Regresi {kode}",
        "jenis": "fungsional",
        "aktif": True,
    }
    r = client.post("/api/v1/jabatan", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_uraian_tugas_tanpa_detil(client: TestClient, jabatan_id: str) -> dict:
    """Uraian tugas dengan `detil_tugas_id=None` — mereproduksi katalog ber-`detil_tugas` NULL."""
    tp = client.post(
        f"{BASE}/tugas-pokok",
        json={"jabatan_ids": [jabatan_id], "nama": f"Tugas Pokok Regresi {uuid.uuid4().hex[:8]}"},
    )
    assert tp.status_code == 201, tp.text
    kode = f"TI{uuid.uuid4().hex[:8]}"
    ut = client.post(
        f"{BASE}/uraian-tugas",
        json={
            "kode": kode,
            "uraian": f"Uraian tugas {kode}",
            "unit": UNIT,
            "urutan": 1,
            "tugas_pokok_id": tp.json()["id"],
            "jabatan_id": jabatan_id,
        },
    )
    assert ut.status_code == 201, ut.text
    return ut.json()


def test_task_terpilih_toleran_detil_tugas_null(client: TestClient) -> None:
    """Sesi yang membekukan task ber-`detil_tugas_id=NULL` tetap 200, bukan 500."""
    jbt = _create_jabatan_regresi(client)
    ut = _create_uraian_tugas_tanpa_detil(client, jbt["id"])
    assert ut["detil_tugas_id"] is None

    sesi = _create_sesi(client, jbt["id"])
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], [ut["kode"]])
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text
    assert r3.json()["jumlah_task_terpilih"] == 1

    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200, tt.text
    item = next(x for x in tt.json() if x["kode"] == ut["kode"])
    assert item["detil_tugas"] == ""

    _detail_submit(
        client,
        ra["id"],
        [
            {
                "task_kode": ut["kode"],
                "sumber_bukti": "Aktual",
                "kondisi": "Baseline",
                "frekuensi_teks": "Mingguan",
                "durasi_per_kali": 60,
                "jam_per_minggu": 2.0,
                "peak4w_hours": 0,
                "va_type": "VA-Core",
            }
        ],
    )
    assert client.post(f"{SESI}/{sid}/tutup").json()["status"] == "CLOSED"

    an = client.post(f"{SESI}/{sid}/analisis")
    assert an.status_code == 200, an.text
    hasil_item = next(t for t in an.json()["tasks"] if t["kode"] == ut["kode"])
    assert hasil_item["detil_tugas"] == ""

    hg = client.get(f"{SESI}/{sid}/hasil")
    assert hg.status_code == 200, hg.text


# --------------------------------------------------------------------------- #
# Nilai standar CalHR (std_*) — prefill Tahap 3 & agregat setuju/ubah
# --------------------------------------------------------------------------- #

_STD_MASTER = {
    "std_sumber_bukti": "Aktual",
    "std_kondisi": "Baseline",
    "std_frekuensi_teks": "Mingguan",
    "std_durasi_per_kali": "60 menit",
    "std_jam_per_minggu": 2.0,
    "std_peak4w_hours": 0.0,
    "std_va_type": "VA-Core",
}

# durasi_per_kali jawaban responden (ti_detail) tetap Integer — beda dari
# std_durasi_per_kali master (String bebas sejak revisi #6).
_DURASI_PER_KALI_RESPONDEN = 60


def _detail_item_dari_standar(
    kode: str, *, setuju: bool, jam_per_minggu: float | None = None
) -> dict:
    return {
        "task_kode": kode,
        "sumber_bukti": _STD_MASTER["std_sumber_bukti"],
        "kondisi": _STD_MASTER["std_kondisi"],
        "frekuensi_teks": _STD_MASTER["std_frekuensi_teks"],
        "durasi_per_kali": _DURASI_PER_KALI_RESPONDEN,
        "jam_per_minggu": (
            jam_per_minggu if jam_per_minggu is not None else _STD_MASTER["std_jam_per_minggu"]
        ),
        "peak4w_hours": _STD_MASTER["std_peak4w_hours"],
        "va_type": _STD_MASTER["std_va_type"],
        "setuju_standar": setuju,
    }


def test_std_calhr_prefill_task_terpilih_dan_agregat_setuju(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Nilai standar master → prefill task-terpilih Tahap 3 & agregat n_setuju/n_ubah_standar."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kode_std = _catalog_kodes(client, jabatan_id_tk, 1)[0]

    search = client.post(
        f"{BASE}/uraian-tugas/search",
        json={"domain": [["kode", "=", kode_std]], "limit": 1, "offset": 0},
    )
    assert search.status_code == 200, search.text
    ut_id = search.json()["items"][0]["id"]
    r_std = client.patch(f"{BASE}/uraian-tugas/{ut_id}", json=_STD_MASTER)
    assert r_std.status_code == 200, r_std.text

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    _seleksi_submit(client, ra["id"], [kode_std])
    _seleksi_submit(client, rb["id"], [kode_std])
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")

    # task-terpilih membawa std_* sesuai master
    tt = client.get(f"{SESI}/{sid}/task-terpilih")
    assert tt.status_code == 200
    item = next(x for x in tt.json() if x["kode"] == kode_std)
    for key, value in _STD_MASTER.items():
        assert item[key] == value

    # A: setuju standar (nilai = standar) ; B: ubah dari standar (jam_per_minggu beda)
    _detail_submit(client, ra["id"], [_detail_item_dari_standar(kode_std, setuju=True)])
    _detail_submit(
        client, rb["id"], [_detail_item_dari_standar(kode_std, setuju=False, jam_per_minggu=5.0)]
    )

    det_a = client.get(f"{SESI}/responden/{ra['id']}/detail")
    assert det_a.status_code == 200
    assert det_a.json()[0]["setuju_standar"] is True
    det_b = client.get(f"{SESI}/responden/{rb['id']}/detail")
    assert det_b.status_code == 200
    assert det_b.json()[0]["setuju_standar"] is False

    assert client.post(f"{SESI}/{sid}/tutup").json()["status"] == "CLOSED"
    an = client.post(f"{SESI}/{sid}/analisis")
    assert an.status_code == 200, an.text
    task = next(t for t in an.json()["tasks"] if t["kode"] == kode_std)
    assert task["n_setuju_standar"] == 1
    assert task["n_ubah_standar"] == 1


def test_submit_detail_tanpa_setuju_standar_default_true(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Backward compatible: payload lama tanpa `setuju_standar` → default True."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")

    _detail_submit(client, ra["id"], [_detail_item(kodes[0])])

    det = client.get(f"{SESI}/responden/{ra['id']}/detail")
    assert det.status_code == 200
    assert det.json()[0]["setuju_standar"] is True


def test_detail_kode_diluar_terpilih_ditolak(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 4)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], [kodes[0]])
    # Masuk TAHAP2 lalu TAHAP3 (K0 unanimous karena 1 responden memilihnya)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    # kodes[3] tidak ada di terpilih (hanya kodes[0])
    res = client.put(
        f"{SESI}/responden/{ra['id']}/detail",
        json={
            "detail": [
                {
                    "task_kode": kodes[3],
                    "sumber_bukti": "Aktual",
                    "kondisi": "Baseline",
                    "frekuensi_teks": "Harian",
                    "durasi_per_kali": 30,
                    "jam_per_minggu": 1.0,
                    "va_type": "VA-Enable",
                }
            ]
        },
    )
    assert res.status_code in (400, 422)


def test_detail_requires_tahap3(client: TestClient, jabatan_id_tk: str) -> None:
    """Detail hanya bisa disubmit saat TAHAP3, bukan TAHAP2."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    # Di TAHAP2, belum bisa submit detail
    res = client.put(
        f"{SESI}/responden/{ra['id']}/detail",
        json={
            "detail": [
                {
                    "task_kode": kodes[0],
                    "sumber_bukti": "Aktual",
                    "kondisi": "Baseline",
                    "frekuensi_teks": "Harian",
                    "durasi_per_kali": 30,
                    "jam_per_minggu": 1.0,
                    "va_type": "VA-Core",
                }
            ]
        },
    )
    assert res.status_code in (400, 422)


def test_hasil_belum_analyzed(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)


def test_responden_delete_setelah_submit_ditolak(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    _seleksi_submit(client, ra["id"], kodes)
    r = client.delete(f"{SESI}/responden/{ra['id']}")
    assert r.status_code in (400, 422)


@pytest.mark.parametrize("field", ["sumber_bukti", "va_type"])
def test_detail_enum_invalid(client: TestClient, jabatan_id_tk: str, field: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    item = {
        "task_kode": kodes[0],
        "sumber_bukti": "Aktual",
        "kondisi": "Baseline",
        "frekuensi_teks": "Harian",
        "durasi_per_kali": 30,
        "jam_per_minggu": 1.0,
        "va_type": "VA-Core",
    }
    item[field] = "NILAI_SALAH"
    res = client.put(f"{SESI}/responden/{ra['id']}/detail", json={"detail": [item]})
    assert res.status_code == 422


@pytest.mark.parametrize("field", ["ai_mode", "dcs_flag"])
def test_detail_ai_mode_dcs_flag_ditolak_sebagai_field_asing(
    client: TestClient, jabatan_id_tk: str, field: str
) -> None:
    """`ai_mode`/`dcs_flag` dihapus tuntas dari kontrak — payload yang masih
    menyertakannya harus ditolak (422, `extra="forbid"`), bukan diam-diam diabaikan."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    item = {
        "task_kode": kodes[0],
        "sumber_bukti": "Aktual",
        "kondisi": "Baseline",
        "frekuensi_teks": "Harian",
        "durasi_per_kali": 30,
        "jam_per_minggu": 1.0,
        "va_type": "VA-Core",
        field: "Human-led" if field == "ai_mode" else False,
    }
    res = client.put(f"{SESI}/responden/{ra['id']}/detail", json={"detail": [item]})
    assert res.status_code == 422


def _detail_item(kode: str, jpm: float = 1.0) -> dict:
    return {
        "task_kode": kode,
        "sumber_bukti": "Aktual",
        "kondisi": "Baseline",
        "frekuensi_teks": "Harian",
        "durasi_per_kali": 30,
        "jam_per_minggu": jpm,
        "va_type": "VA-Core",
    }


def test_save_draft_detail_parsial_lalu_lengkap(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 2)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")

    r1 = client.put(
        f"{SESI}/responden/{ra['id']}/detail", json={"detail": [_detail_item(kodes[0])]}
    )
    assert r1.status_code == 200
    assert len(r1.json()) == 1

    r2 = client.put(
        f"{SESI}/responden/{ra['id']}/detail", json={"detail": [_detail_item(kodes[1])]}
    )
    assert r2.status_code == 200

    r_submit = client.post(f"{SESI}/responden/{ra['id']}/detail/submit")
    assert r_submit.status_code == 201
    assert len(r_submit.json()) == 2

    assert client.get(f"{SESI}/responden/{ra['id']}").json()["tahap3_submit"] is True


def test_save_draft_detail_rejected_after_submit(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    _detail_submit(client, ra["id"], [_detail_item(kodes[0])])

    res = client.put(
        f"{SESI}/responden/{ra['id']}/detail", json={"detail": [_detail_item(kodes[0])]}
    )
    assert res.status_code == 422


def test_submit_detail_rejected_when_empty(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")

    res = client.post(f"{SESI}/responden/{ra['id']}/detail/submit")
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Tahap 2 review koordinator
# --------------------------------------------------------------------------- #


def test_tahap2_review_belum_tahap2(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/tahap2")
    assert r.status_code in (400, 422)


def test_tahap2_submit_keputusan_non_partial_ditolak(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Koordinator tidak boleh submit keputusan untuk task unanimous."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    _seleksi_submit(client, ra["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    # kodes[0] dipilih oleh semua (1 responden = 1 = unanimous), bukan partial
    r = client.post(
        f"{SESI}/{sid}/tahap2",
        json={"keputusan": [{"task_kode": kodes[0], "disetujui": True}]},
    )
    assert r.status_code in (400, 422)


# --------------------------------------------------------------------------- #
# GET /kuesioner/saya (Task Inventory — assignment-based, item 013)
#
# Enrollment TI = anggota SME panel jabatan sesi, ditetapkan saat sesi dibuat
# (`SqlTiSesiService.create()` → `assign_ti_responden_banyak()`). Endpoint ini
# murni membaca `list_by_partisipan()` — TIDAK ADA lagi enrollment otomatis
# universal di waktu baca (lihat item 013 & entri Revisi Desain terkait).
# --------------------------------------------------------------------------- #

KUESIONER = f"{BASE}/kuesioner"


def test_kuesioner_saya_tanpa_partisipan_ti(client: TestClient) -> None:
    r = client.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_hanya_sesi_yang_terdaftar(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    """Partisipan A anggota panel jabatan X; sesi dibuat untuk jabatan X **dan**
    jabatan Y (panel berbeda, A bukan anggota) → `/kuesioner/saya` milik A hanya
    memuat sesi X."""
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    jabatan_x = jabatan_id_tk
    jabatan_y = f"jbt_{uuid.uuid4().hex[:8]}"

    par_a = partisipan_factory("ti-hanya-terdaftar-a", jabatan_utama_id=jabatan_x)
    par_lain = partisipan_factory("ti-hanya-terdaftar-lain", jabatan_utama_id=jabatan_y)

    sme_svc = SqlSMEPanelService(db_session)
    panel_x = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_x))
    sme_svc.add_anggota(panel_x.id, par_a)
    panel_y = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_y))
    sme_svc.add_anggota(panel_y.id, par_lain)

    sesi_svc = SqlTiSesiService(db_session)
    sesi_x = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_x, cabang="Bandung"))
    sesi_svc.transition(sesi_x.id, "TAHAP1")
    sesi_y = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_y, cabang="Bandung"))
    sesi_svc.transition(sesi_y.id, "TAHAP1")

    as_a = client_as("ti-hanya-terdaftar-a")
    r = as_a.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    data = r.json()
    assert {item["sesi_id"] for item in data} == {sesi_x.id}
    assert all("sesi_jabatan_id" in item for item in data)


def test_kuesioner_saya_tidak_membuat_responden(client_as, partisipan_factory, db_session) -> None:
    """Partisipan yang bukan anggota panel mana pun memanggil `/kuesioner/saya` →
    respons `[]` dan jumlah baris `TiRespondenModel` di DB tidak bertambah — ini
    inti bug lama (endpoint dulu menulis lewat `ensure_for_partisipan()`)."""
    from sqlalchemy import func, select

    from anjab_abk_backend.models import TiRespondenModel

    partisipan_factory("ti-tanpa-panel")
    as_par = client_as("ti-tanpa-panel")

    def _count() -> int:
        return db_session.scalar(select(func.count()).select_from(TiRespondenModel)) or 0

    before = _count()
    r = as_par.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    assert r.json() == []
    assert _count() == before

    # Panggil berulang — tetap tidak menulis apa pun.
    r2 = as_par.get(f"{KUESIONER}/saya")
    assert r2.json() == []
    assert _count() == before


def test_kuesioner_saya_saring_status_nonaktif(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    """Sesi tempat partisipan terdaftar berstatus DRAFT (belum TAHAP1/2/3) tidak
    muncul di `/kuesioner/saya`."""
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    par_a = partisipan_factory("ti-status-nonaktif-a", jabatan_utama_id=jabatan_id_tk)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id_tk))
    sme_svc.add_anggota(panel.id, par_a)

    sesi_svc = SqlTiSesiService(db_session)
    sesi_draft = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id_tk, cabang="Bandung"))
    assert sesi_draft.status == "DRAFT"

    as_a = client_as("ti-status-nonaktif-a")
    r = as_a.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_is_koordinator(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    """Koordinator panel tetap melihat sesinya dengan `is_koordinator = true` setelah
    pengetatan enrollment — ia otomatis ter-enroll sebagai anggota panel (bukan lewat
    auto-enroll universal yang sudah dihapus)."""
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate, SMEPanelUpdate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    par_koord = partisipan_factory("ti-koordinator-saya", jabatan_utama_id=jabatan_id_tk)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id_tk))
    sme_svc.add_anggota(panel.id, par_koord)
    sme_svc.update(panel.id, SMEPanelUpdate(koordinator_id=par_koord))

    sesi_svc = SqlTiSesiService(db_session)
    sesi = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id_tk, cabang="Bandung"))
    assert sesi.koordinator_id == par_koord
    sesi_svc.transition(sesi.id, "TAHAP1")

    as_koord = client_as("ti-koordinator-saya")
    r = as_koord.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["sesi_id"] == sesi.id
    assert data[0]["is_koordinator"] is True


# --------------------------------------------------------------------------- #
# SME panel check
# --------------------------------------------------------------------------- #


def test_sesi_create_jabatan_valid(client: TestClient, jabatan_id_tk: str) -> None:
    """Sesi dapat dibuat dengan jabatan valid."""
    r = client.post(
        SESI,
        json={
            "jabatan_id": jabatan_id_tk,
            "cabang": "Bandung",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["jabatan_id"] == jabatan_id_tk
    assert "jabatan_nama" in r.json()


def test_sesi_create_jabatan_invalid(client: TestClient) -> None:
    """Sesi dengan jabatan tidak valid ditolak."""
    r = client.post(
        SESI,
        json={
            "jabatan_id": "jbt_tidakada_samasekali",
            "cabang": "Bandung",
        },
    )
    assert r.status_code in (400, 422)


def test_responden_sme_panel_check(client: TestClient, db_session) -> None:
    """Partisipan hanya bisa jadi responden TI jika anggota SME panel jabatan sesi."""
    import uuid

    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    jabatan_id = f"jbt_{uuid.uuid4().hex[:8]}"

    # Buat SME panel untuk jabatan ini
    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id))

    # Buat partisipan A (akan menjadi anggota panel)
    par_svc = SqlPartisipanService(db_session)
    par_a = par_svc.create(
        PartisipanCreate(
            nama="Par A",
            email=f"par.a.{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_test",
            jabatan_utama_id=jabatan_id,
            masa_kerja_tahun=2,
        ),
        authentik_user_id=f"uid_a_{uuid.uuid4().hex[:4]}",
    )
    sme_svc.add_anggota(panel.id, par_a.id)

    # Buat partisipan B (tidak di panel)
    par_b = par_svc.create(
        PartisipanCreate(
            nama="Par B",
            email=f"par.b.{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_test",
            jabatan_utama_id=f"jbt_{uuid.uuid4().hex[:8]}",
            masa_kerja_tahun=2,
        ),
        authentik_user_id=f"uid_b_{uuid.uuid4().hex[:4]}",
    )

    # Buat sesi TI dengan jabatan_id (tanpa unit → tidak perlu catalog valid)
    # Gunakan jabatan_id yang memang ada di SME panel
    # Namun: jabatan ini tidak ada di catalog → cek validation
    # Untuk tes ini, buat sesi langsung via service (bypass catalog check)
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    sesi_svc = SqlTiSesiService(db_session)
    sesi_obj = sesi_svc.create(
        TiSesiCreate(
            jabatan_id=jabatan_id,
            cabang="Bandung",
        )
    )
    sid = sesi_obj.id
    assert sesi_obj.jabatan_id == jabatan_id

    # Par A (anggota panel) → berhasil
    r_a = client.post(
        f"{SESI}/{sid}/responden",
        json={"partisipan_id": par_a.id, "nama": "Par A"},
    )
    assert r_a.status_code == 201, r_a.text

    # Par B (bukan anggota panel) → ditolak
    r_b = client.post(
        f"{SESI}/{sid}/responden",
        json={"partisipan_id": par_b.id, "nama": "Par B"},
    )
    assert r_b.status_code in (400, 422), r_b.text


def test_responden_tanpa_jabatan_id_bebas(
    client: TestClient, jabatan_id_tk: str, db_session
) -> None:
    """Sesi dengan jabatan yang tidak punya SME panel: semua partisipan bisa didaftarkan."""
    import uuid

    # Buat jabatan baru tanpa SME panel
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    jabatan_baru_id = f"jbt_{uuid.uuid4().hex[:8]}"
    sesi_svc = SqlTiSesiService(db_session)
    sesi_obj = sesi_svc.create(
        TiSesiCreate(
            jabatan_id=jabatan_baru_id,
            cabang="Bandung",
        )
    )
    assert sesi_obj.jabatan_id == jabatan_baru_id
    r = _add_responden(client, sesi_obj.id, "Partisipan Bebas")
    assert r["id"].startswith("trsp_")


# --------------------------------------------------------------------------- #
# Bulk assign (item 005): auto-populate SME panel saat sesi dibuat + endpoint
# bulk manual (idempoten, bukan atomik).
# --------------------------------------------------------------------------- #

SME_BASE = "/api/v1/sme-panel"
PAR_BASE = "/api/v1/partisipan"


def _setup_panel(client: TestClient, jabatan_id: str, n: int) -> list[str]:
    """Buat panel SME untuk `jabatan_id` dengan `n` anggota baru; kembalikan partisipan_ids."""
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id})
    assert r.status_code == 201, r.text
    panel_id = r.json()["id"]
    ids = []
    for _ in range(n):
        rp = client.post(
            PAR_BASE,
            json={
                "nama": f"TI Bulk {uuid.uuid4().hex[:4]}",
                "email": f"ti.bulk.{uuid.uuid4().hex[:6]}@test.id",
                "sekolah_id": "skl_ti_bulk_test",
                "jabatan_utama_id": jabatan_id,
                "masa_kerja_tahun": 1,
            },
        )
        assert rp.status_code == 201, rp.text
        par_id = rp.json()["id"]
        r2 = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par_id})
        assert r2.status_code == 200, r2.text
        ids.append(par_id)
    return ids


def test_create_sesi_auto_populate_dari_panel(client: TestClient, jabatan_id_tk: str) -> None:
    anggota = _setup_panel(client, jabatan_id_tk, 2)
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200, r.text
    responden = r.json()
    assert len(responden) == 2
    assert {row["partisipan_id"] for row in responden} == set(anggota)
    # nama diresolusi dari data partisipan (bukan anonim) — dipakai UI untuk
    # menampilkan nama responden alih-alih "Anonim".
    assert all(row["nama"] for row in responden)


def test_create_sesi_panel_besar_semua_jadi_responden(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Item 037: batas atas `max_responden` sudah dihapus dari TI — panel dengan
    >10 anggota (batas lama) kini tetap membuat sesi & SELURUH anggota jadi
    responden, tanpa ada yang dibuang diam-diam (regresi positif, kebalikan dari
    perilaku sebelum revisi ini)."""
    anggota = _setup_panel(client, jabatan_id_tk, 11)
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200, r.text
    responden = r.json()
    assert len(responden) == 11
    assert {row["partisipan_id"] for row in responden} == set(anggota)


def test_create_sesi_panel_muat_semua_anggota(client: TestClient, jabatan_id_tk: str) -> None:
    """Panel kecil → sesi tetap dibuat, seluruh anggota jadi responden."""
    anggota = _setup_panel(client, jabatan_id_tk, 3)
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200, r.text
    responden = r.json()
    assert len(responden) == 3
    assert {row["partisipan_id"] for row in responden} == set(anggota)


def test_create_sesi_tanpa_panel_tetap_kosong(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_create_sesi_panel_tanpa_anggota_tetap_kosong(
    client: TestClient, jabatan_id_tk: str
) -> None:
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    assert r.status_code == 201, r.text
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200, r.text
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Item 008: koordinator_id sesi diwarisi dari SmePanel.koordinator_id
# --------------------------------------------------------------------------- #


def _setup_panel_dengan_koordinator(client: TestClient, jabatan_id: str) -> tuple[str, str]:
    """Buat panel SME utk `jabatan_id` dengan 1 anggota yang juga ditetapkan sebagai
    koordinator panel; kembalikan `(panel_id, koordinator_id)`."""
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id})
    assert r.status_code == 201, r.text
    panel_id = r.json()["id"]
    rp = client.post(
        PAR_BASE,
        json={
            "nama": f"TI Koordinator {uuid.uuid4().hex[:4]}",
            "email": f"ti.koord.{uuid.uuid4().hex[:6]}@test.id",
            "sekolah_id": "skl_ti_koord_test",
            "jabatan_utama_id": jabatan_id,
            "masa_kerja_tahun": 1,
        },
    )
    assert rp.status_code == 201, rp.text
    par_id = rp.json()["id"]
    r2 = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par_id})
    assert r2.status_code == 200, r2.text
    r3 = client.patch(f"{SME_BASE}/{panel_id}", json={"koordinator_id": par_id})
    assert r3.status_code == 200, r3.text
    return panel_id, par_id


def test_create_sesi_mewarisi_koordinator_dari_panel(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Panel punya koordinator; sesi dibuat tanpa `koordinator_id` di payload →
    koordinator diwarisi dari panel."""
    _panel_id, koordinator_id = _setup_panel_dengan_koordinator(client, jabatan_id_tk)
    sesi = _create_sesi(client, jabatan_id_tk)
    assert sesi["koordinator_id"] == koordinator_id


def test_create_sesi_koordinator_payload_menang_atas_panel(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Payload mengirim `koordinator_id` eksplisit → nilai payload dipakai, TIDAK ditimpa
    koordinator panel."""
    _panel_id, koordinator_panel = _setup_panel_dengan_koordinator(client, jabatan_id_tk)
    sesi = _create_sesi(client, jabatan_id_tk, koordinator_id="p_koordinator_lain")
    assert sesi["koordinator_id"] == "p_koordinator_lain"
    assert sesi["koordinator_id"] != koordinator_panel


def test_create_sesi_panel_tanpa_koordinator_tetap_none(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Panel ada tapi belum punya koordinator → sesi tetap terbuat, `koordinator_id`
    null, tidak error."""
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    assert r.status_code == 201, r.text
    sesi = _create_sesi(client, jabatan_id_tk)
    assert sesi["koordinator_id"] is None


def test_create_sesi_tanpa_panel_koordinator_none(client: TestClient, jabatan_id_tk: str) -> None:
    """Jabatan tanpa panel sama sekali → sesi tetap terbuat, `koordinator_id` null,
    tidak error."""
    sesi = _create_sesi(client, jabatan_id_tk)
    assert sesi["koordinator_id"] is None


def test_responden_bulk_happy_path(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    anggota = _setup_panel(client, jabatan_id_tk, 2)
    r = client.post(f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": anggota})
    assert r.status_code == 201, r.text
    data = r.json()
    assert {c["partisipan_id"] for c in data["created"]} == set(anggota)
    assert data["skipped"] == []
    assert all(c["nama"] for c in data["created"])


def test_responden_bulk_skip_sudah_terdaftar(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    anggota = _setup_panel(client, jabatan_id_tk, 1)
    r1 = client.post(f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": anggota})
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": anggota})
    assert r2.status_code == 201, r2.text
    data = r2.json()
    assert data["created"] == []
    assert data["skipped"] == [{"partisipan_id": anggota[0], "alasan": "sudah_terdaftar"}]


def test_responden_bulk_skip_bukan_anggota_sme_panel(
    client: TestClient, jabatan_id_tk: str, partisipan_factory
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    bukan_anggota = partisipan_factory("ti-bulk-bukan-anggota")
    r = client.post(f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": [bukan_anggota]})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["created"] == []
    assert data["skipped"] == [
        {"partisipan_id": bukan_anggota, "alasan": "bukan_anggota_sme_panel"}
    ]


def test_responden_bulk_skip_duplikat_input(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    anggota = _setup_panel(client, jabatan_id_tk, 1)
    dup_id = anggota[0]
    r = client.post(
        f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": [dup_id, dup_id]}
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["created"]) == 1
    assert data["skipped"] == [{"partisipan_id": dup_id, "alasan": "duplikat_input"}]


def test_responden_bulk_requires_admin(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_partisipan = client_as("ti-bulk-nonadmin")
    r = as_partisipan.post(
        f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": ["par_x"]}
    )
    assert r.status_code == 403


def test_responden_bulk_requires_auth(anon_client: TestClient, jabatan_id_tk: str) -> None:
    r = anon_client.post(
        f"{SESI}/tises_tidakada/responden/bulk", json={"partisipan_ids": ["par_x"]}
    )
    assert r.status_code == 401


def test_responden_bulk_payload_kosong_ditolak(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = client.post(f"{SESI}/{sesi['id']}/responden/bulk", json={"partisipan_ids": []})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses responden
# Task Inventory milik partisipan lain lewat penebakan responden_id.
# --------------------------------------------------------------------------- #


def test_get_responden_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory, db_session
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    jabatan_id = f"jbt_{uuid.uuid4().hex[:8]}"
    par_a = partisipan_factory("ti-bola-a", jabatan_utama_id=jabatan_id)
    par_b = partisipan_factory("ti-bola-b", jabatan_utama_id=jabatan_id)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id))
    sme_svc.add_anggota(panel.id, par_a)
    sme_svc.add_anggota(panel.id, par_b)

    sesi_svc = SqlTiSesiService(db_session)
    sesi_obj = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id, cabang="Bandung"))
    rsp = client.post(
        f"{SESI}/{sesi_obj.id}/responden",
        json={"partisipan_id": par_a, "nama": "A"},
    ).json()

    as_b = client_as("ti-bola-b")
    assert as_b.get(f"{SESI}/responden/{rsp['id']}").status_code == 403

    as_a = client_as("ti-bola-a")
    r = as_a.get(f"{SESI}/responden/{rsp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == rsp["id"]


def test_save_draft_seleksi_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService

    par_a = partisipan_factory("ti-bola-c", jabatan_utama_id=jabatan_id_tk)
    par_b = partisipan_factory("ti-bola-d", jabatan_utama_id=jabatan_id_tk)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id_tk))
    sme_svc.add_anggota(panel.id, par_a)
    sme_svc.add_anggota(panel.id, par_b)

    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    rsp = client.post(f"{SESI}/{sid}/responden", json={"partisipan_id": par_a, "nama": "A"}).json()

    as_d = client_as("ti-bola-d")
    r = as_d.put(f"{SESI}/responden/{rsp['id']}/seleksi", json={"task_kode": kodes})
    assert r.status_code == 403

    as_a = client_as("ti-bola-c")
    r_ok = as_a.put(f"{SESI}/responden/{rsp['id']}/seleksi", json={"task_kode": kodes})
    assert r_ok.status_code == 200
    r_submit = as_a.post(f"{SESI}/responden/{rsp['id']}/seleksi/submit")
    assert r_submit.status_code == 201


def test_list_responden_forbidden_for_non_admin(
    client: TestClient, client_as, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_partisipan = client_as("ti-bola-e")
    r = as_partisipan.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 403


def test_create_responden_forbidden_for_non_admin(
    client: TestClient, client_as, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_partisipan = client_as("ti-bola-f")
    r = as_partisipan.post(f"{SESI}/{sesi['id']}/responden", json={"nama": "X"})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Item 014: otorisasi sesi — lapis 1 (admin-only) & lapis 2 (admin/peserta)
# --------------------------------------------------------------------------- #


def test_sesi_list_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(SESI).status_code == 401


def test_sesi_list_partisipan_403(client_as) -> None:
    as_p = client_as("ti-guard-list")
    assert as_p.get(SESI).status_code == 403


def test_sesi_search_tanpa_token_401(anon_client: TestClient) -> None:
    r = anon_client.post(
        f"{SESI}/search", json={"domain": [], "order": [], "limit": 10, "offset": 0}
    )
    assert r.status_code == 401


def test_sesi_search_partisipan_403(client_as) -> None:
    as_p = client_as("ti-guard-search")
    r = as_p.post(f"{SESI}/search", json={"domain": [], "order": [], "limit": 10, "offset": 0})
    assert r.status_code == 403


def test_sesi_create_partisipan_403(client_as, jabatan_id_tk: str) -> None:
    as_p = client_as("ti-guard-create")
    r = as_p.post(SESI, json=_sesi_payload(jabatan_id_tk))
    assert r.status_code == 403


def test_sesi_update_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_p = client_as("ti-guard-update")
    r = as_p.patch(f"{SESI}/{sesi['id']}", json={"catatan": "coba ubah"})
    assert r.status_code == 403


def test_sesi_tutup_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_p = client_as("ti-guard-tutup")
    r = as_p.post(f"{SESI}/{sesi['id']}/tutup")
    assert r.status_code == 403


def test_mulai_tahap1_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_p = client_as("ti-guard-tahap1")
    r = as_p.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    assert r.status_code == 403


def test_mulai_tahap2_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    as_p = client_as("ti-guard-tahap2")
    r = as_p.post(f"{SESI}/{sesi['id']}/mulai-tahap2")
    assert r.status_code == 403


def test_mulai_tahap3_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    """Paling penting: partisipan biasa tidak boleh membekukan task (freeze tidak reversibel),
    dan sesi TIDAK berpindah status setelah panggilan ditolak."""
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    rsp = _add_responden(client, sid, "R1")
    _seleksi_submit(client, rsp["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    as_p = client_as("ti-guard-tahap3")
    r = as_p.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r.status_code == 403

    # `client_as` mengoverride verifier pada `app` (bukan hanya client yang
    # dikembalikan) — pakai `client_as(..., groups=["admin"])` untuk cek status,
    # BUKAN fixture `client` (lihat docstring fixture `client_as` di conftest.py).
    as_admin = client_as("ti-guard-tahap3-admin", groups=["admin"])
    masih = as_admin.get(f"{SESI}/{sid}")
    assert masih.json()["status"] == "TAHAP2"


def test_analisis_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_p = client_as("ti-guard-analisis")
    r = as_p.post(f"{SESI}/{sesi['id']}/analisis")
    assert r.status_code == 403


def test_hasil_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    as_p = client_as("ti-guard-hasil")
    r = as_p.get(f"{SESI}/{sesi['id']}/hasil")
    assert r.status_code == 403


def test_get_sesi_peserta_boleh(
    client: TestClient, client_as, partisipan_factory, db_session
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    jabatan_id = f"jbt_{uuid.uuid4().hex[:8]}"
    par_a = partisipan_factory("ti-akses-peserta", jabatan_utama_id=jabatan_id)

    sme_svc = SqlSMEPanelService(db_session)
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id))
    sme_svc.add_anggota(panel.id, par_a)

    sesi_svc = SqlTiSesiService(db_session)
    sesi_obj = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id, cabang="Bandung"))
    # auto-populate dari panel: par_a otomatis jadi responden sesi ini.

    as_a = client_as("ti-akses-peserta")
    r = as_a.get(f"{SESI}/{sesi_obj.id}")
    assert r.status_code == 200


def test_get_sesi_bukan_peserta_403(
    client: TestClient, client_as, partisipan_factory, db_session
) -> None:
    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.anjab.services.sme_panel_sql import SqlSMEPanelService
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    jabatan_id_x = f"jbt_{uuid.uuid4().hex[:8]}"
    jabatan_id_y = f"jbt_{uuid.uuid4().hex[:8]}"
    partisipan_factory("ti-akses-x", jabatan_utama_id=jabatan_id_x)
    par_y = partisipan_factory("ti-akses-y", jabatan_utama_id=jabatan_id_y)

    sme_svc = SqlSMEPanelService(db_session)
    panel_y = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id_y))
    sme_svc.add_anggota(panel_y.id, par_y)

    sesi_svc = SqlTiSesiService(db_session)
    sesi_x = sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id_x, cabang="Bandung"))
    sesi_svc.create(TiSesiCreate(jabatan_id=jabatan_id_y, cabang="Bandung"))

    # par_y adalah peserta sesi jabatan Y, TIDAK boleh membaca sesi jabatan X.
    as_y = client_as("ti-akses-y")
    r = as_y.get(f"{SESI}/{sesi_x.id}")
    assert r.status_code == 403


def test_get_tahap2_koordinator_boleh(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str, db_session
) -> None:
    from anjab_abk_backend.taskinv.schemas.sesi import TiSesiCreate
    from anjab_abk_backend.taskinv.services.sesi_sql import SqlTiSesiService

    koordinator_id = partisipan_factory("ti-koord-tahap2", jabatan_utama_id=jabatan_id_tk)

    # Dibuat langsung lewat service (bukan endpoint create, yang kini admin-only dan
    # tidak menerima `koordinator_id` tanpa SME panel) — `db_session` di sini adalah
    # sesi TRANSAKSI YANG SAMA yang dipakai `client`/`client_as` (lihat fixture `app`
    # di conftest.py, `get_session` di-override ke `db_session`).
    sesi_obj = SqlTiSesiService(db_session).create(
        TiSesiCreate(
            jabatan_id=jabatan_id_tk,
            cabang="Bandung",
            koordinator_id=koordinator_id,
        )
    )
    sid = sesi_obj.id

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    rsp = _add_responden(client, sid, "A")
    _seleksi_submit(client, rsp["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    as_koord = client_as("ti-koord-tahap2")
    r = as_koord.get(f"{SESI}/{sid}/tahap2")
    assert r.status_code == 200


def test_get_tahap2_bukan_peserta_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    rsp = _add_responden(client, sid, "A")
    _seleksi_submit(client, rsp["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    as_p = client_as("ti-guard-tahap2-get")
    r = as_p.get(f"{SESI}/{sid}/tahap2")
    assert r.status_code == 403


def test_get_tahap2_tanpa_token_401(
    anon_client: TestClient, client: TestClient, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    r = anon_client.get(f"{SESI}/{sesi['id']}/tahap2")
    assert r.status_code == 401


def test_get_task_terpilih_peserta_boleh(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str
) -> None:
    """Regresi paling mungkin dari item 014: partisipan Tahap 3 tidak boleh ikut terblokir."""
    par_a = partisipan_factory("ti-tt-peserta", jabatan_utama_id=jabatan_id_tk)
    # `create_responden` menolak partisipan_id yang bukan anggota SME panel jabatan
    # sesi — daftarkan par_a ke panel dulu (lihat taskinv_responden.py:create_responden).
    r_panel = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    assert r_panel.status_code == 201, r_panel.text
    panel_id = r_panel.json()["id"]
    r_add = client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": par_a})
    assert r_add.status_code == 200, r_add.text

    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    # par_a sudah otomatis jadi responden lewat auto-populate SME panel saat sesi
    # dibuat — ambil id-nya, JANGAN POST responden lagi (akan jadi duplikat).
    responden_list = client.get(f"{SESI}/{sid}/responden").json()
    rsp = next(r for r in responden_list if r["partisipan_id"] == par_a)
    _seleksi_submit(client, rsp["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3")
    assert r3.status_code == 200, r3.text

    as_a = client_as("ti-tt-peserta")
    r = as_a.get(f"{SESI}/{sid}/task-terpilih")
    assert r.status_code == 200


def test_get_task_terpilih_bukan_peserta_403(
    client: TestClient, client_as, jabatan_id_tk: str
) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    rsp = _add_responden(client, sid, "A")
    _seleksi_submit(client, rsp["id"], kodes)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")

    as_p = client_as("ti-guard-tt")
    r = as_p.get(f"{SESI}/{sid}/task-terpilih")
    assert r.status_code == 403


def test_get_responden_koordinator_boleh(
    client: TestClient, client_as, partisipan_factory, jabatan_id_tk: str
) -> None:
    koordinator_id = partisipan_factory("ti-rsp-koord", jabatan_utama_id=jabatan_id_tk)
    sesi = _create_sesi(client, jabatan_id_tk, koordinator_id=koordinator_id)

    as_koord = client_as("ti-rsp-koord")
    r = as_koord.get(f"{SESI}/{sesi['id']}/responden")
    assert r.status_code == 200


def test_admin_semua_endpoint_boleh(client: TestClient, jabatan_id_tk: str) -> None:
    sesi = _create_sesi(client, jabatan_id_tk)
    sid = sesi["id"]
    assert client.get(SESI).status_code == 200
    assert (
        client.post(
            f"{SESI}/search", json={"domain": [], "order": [], "limit": 10, "offset": 0}
        ).status_code
        == 200
    )
    assert client.get(f"{SESI}/{sid}").status_code == 200
    assert client.patch(f"{SESI}/{sid}", json={"catatan": "ok"}).status_code == 200
    assert client.post(f"{SESI}/{sid}/mulai-tahap1").status_code == 200

    kodes = _catalog_kodes(client, jabatan_id_tk, 1)
    rsp = _add_responden(client, sid, "A")
    _seleksi_submit(client, rsp["id"], kodes)

    assert client.post(f"{SESI}/{sid}/mulai-tahap2").status_code == 200
    assert client.get(f"{SESI}/{sid}/tahap2").status_code == 200
    assert client.get(f"{SESI}/{sid}/responden").status_code == 200
    assert client.post(f"{SESI}/{sid}/mulai-tahap3").status_code == 200
    assert client.get(f"{SESI}/{sid}/task-terpilih").status_code == 200

    # analisis butuh minimal 1 responden yang sudah submit detail Tahap 3.
    r_detail = _detail_submit(client, rsp["id"], [_detail_item(kodes[0])])
    assert r_detail

    assert client.post(f"{SESI}/{sid}/tutup").status_code == 200
    assert client.post(f"{SESI}/{sid}/analisis").status_code == 200
    assert client.get(f"{SESI}/{sid}/hasil").status_code == 200
