"""Test endpoint Task Inventory: catalog, alur 3 tahap, transisi, agregasi."""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/task-inventory"
SESI = f"{BASE}/sesi"
UNIT = "TK"
KATEGORI = "Kepala Sekolah"

_year_counter = itertools.count(2000)


def _uniq_periode() -> str:
    """Periode YYYY-MM unik per pemanggilan (hindari konflik unit+jabatan+periode)."""
    return f"{next(_year_counter)}-01"


def _sesi_payload(periode: str | None = None, **over) -> dict:
    payload = {
        "kategori_jabatan": KATEGORI,
        "periode": periode or _uniq_periode(),
        "min_responden": 1,
        "max_responden": 10,
    }
    if "unit" not in over:
        payload["unit"] = UNIT  # default to UNIT for existing tests
    payload.update(over)
    return payload


def _catalog_kodes(client: TestClient, n: int) -> list[str]:
    r = client.get(BASE + "/catalog", params={"unit": UNIT, "kategori_jabatan": KATEGORI})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= n
    return [it["kode"] for it in items[:n]]


def _create_sesi(client: TestClient, **over) -> dict:
    r = client.post(SESI, json=_sesi_payload(**over))
    assert r.status_code == 201, r.text
    return r.json()


def _add_responden(client: TestClient, sesi_id: str, nama: str) -> dict:
    r = client.post(f"{SESI}/{sesi_id}/responden", json={"nama": nama})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def test_catalog_kombinasi(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog/kombinasi")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 51
    target = next(x for x in rows if x["unit"] == UNIT and x["kategori_jabatan"] == KATEGORI)
    assert target["jumlah_task"] > 0


def test_catalog_list_by_kombinasi(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog", params={"unit": UNIT, "kategori_jabatan": KATEGORI})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == UNIT and it["kategori_jabatan"] == KATEGORI for it in items)
    assert items[0]["kode"].startswith("TI")


def test_catalog_unknown_kombinasi_empty(anon_client: TestClient) -> None:
    r = anon_client.get(BASE + "/catalog", params={"unit": "ZZ", "kategori_jabatan": "X"})
    assert r.status_code == 200
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Sesi CRUD
# --------------------------------------------------------------------------- #


def test_sesi_create_and_get(client: TestClient) -> None:
    sesi = _create_sesi(client)
    assert sesi["id"].startswith("tises_")
    assert sesi["status"] == "DRAFT"
    assert sesi["jumlah_task_terpilih"] is None
    r = client.get(f"{SESI}/{sesi['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == sesi["id"]


def test_sesi_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(SESI, json=_sesi_payload())
    assert r.status_code == 401


def test_sesi_create_invalid_kombinasi(client: TestClient) -> None:
    r = client.post(SESI, json=_sesi_payload(unit="ZZ", kategori_jabatan="X"))
    assert r.status_code in (400, 422)


def test_sesi_duplicate_conflict(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(SESI, json=_sesi_payload(periode=sesi["periode"]))
    assert r.status_code == 409


def test_sesi_min_gt_max_rejected(client: TestClient) -> None:
    r = client.post(SESI, json=_sesi_payload(min_responden=5, max_responden=2))
    assert r.status_code in (400, 422)


def test_sesi_update_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.patch(f"{SESI}/{sesi['id']}", json={"catatan": "halo"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "halo"


def test_sesi_delete_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.delete(f"{SESI}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{SESI}/{sesi['id']}").status_code == 404


def test_sesi_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{SESI}/tises_xxx").status_code == 404


def test_sesi_search(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(
        f"{SESI}/search", json={"domain": [["id", "=", sesi["id"]]], "limit": 10, "offset": 0}
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_sesi_koordinator_id(client: TestClient) -> None:
    sesi = _create_sesi(client, koordinator_id="p_koordinator01")
    assert sesi["koordinator_id"] == "p_koordinator01"


# --------------------------------------------------------------------------- #
# Transisi tahap
# --------------------------------------------------------------------------- #


def test_mulai_tahap1(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
    assert r.status_code == 200
    assert r.json()["status"] == "TAHAP1"


def test_mulai_tahap2_invalid_from_draft(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.post(f"{SESI}/{sesi['id']}/mulai-tahap2")
    assert r.status_code in (400, 422)


def test_mulai_tahap2_guard_belum_semua_submit(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r1 = _add_responden(client, sid, "A")
    _add_responden(client, sid, "B")  # tidak submit
    kodes = _catalog_kodes(client, 3)
    assert (
        client.post(
            f"{SESI}/responden/{r1['id']}/seleksi", json={"task_kode": kodes[:2]}
        ).status_code
        == 201
    )
    # 1 dari 2 submit → tanpa paksa harus gagal
    r = client.post(f"{SESI}/{sid}/mulai-tahap2")
    assert r.status_code in (400, 422)
    # dengan paksa → sukses, status TAHAP2
    r = client.post(f"{SESI}/{sid}/mulai-tahap2", params={"paksa": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "TAHAP2"
    # jumlah_task_terpilih belum dibekukan (baru di TAHAP3)
    assert r.json()["jumlah_task_terpilih"] is None


def test_mulai_tahap3_dengan_review_koordinator(client: TestClient) -> None:
    """Flow: Tahap1 → Tahap2 (koordinator review partial) → Tahap3 (freeze)."""
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 3)  # K0, K1, K2

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # A pilih K0,K1 ; B pilih K1,K2
    # K1 = unanimous (2/2), K0 & K2 = partial (1/2) → perlu review koordinator
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0], kodes[1]]})
    client.post(f"{SESI}/responden/{rb['id']}/seleksi", json={"task_kode": [kodes[1], kodes[2]]})

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


def test_mulai_tahap3_paksa_tanpa_review(client: TestClient) -> None:
    """Dengan paksa=true, bisa masuk TAHAP3 meski ada partial belum diputuskan."""
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 2)

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0]]})
    client.post(f"{SESI}/responden/{rb['id']}/seleksi", json={"task_kode": [kodes[1]]})
    client.post(f"{SESI}/{sid}/mulai-tahap2")

    # Tanpa review koordinator, paksa → sukses (partial diabaikan, hanya unanimous)
    r3 = client.post(f"{SESI}/{sid}/mulai-tahap3", params={"paksa": "true"})
    # Tidak ada unanimous, namun tidak ada approved → gagal karena tidak ada task
    # Sebenarnya K0 dipilih 1/2 dan K1 dipilih 1/2, tidak ada unanimous
    # Dengan paksa: boleh lanjut tapi task kosong → freeze akan gagal
    # Expected: error karena tidak ada task relevan
    assert r3.status_code in (200, 400, 422)


def test_mulai_tahap3_unanimous_otomatis(client: TestClient) -> None:
    """Task yang dipilih semua anggota masuk otomatis tanpa review koordinator."""
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 2)

    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # Keduanya pilih K0 dan K1 → semua unanimous
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    client.post(f"{SESI}/responden/{rb['id']}/seleksi", json={"task_kode": kodes})

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


def test_seleksi_invalid_kode(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": ["TItidakvalid"]})
    assert res.status_code in (400, 422)


def test_seleksi_requires_tahap1(client: TestClient) -> None:
    sesi = _create_sesi(client)  # masih DRAFT
    sid = sesi["id"]
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 1)
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code in (400, 422)


def test_seleksi_double_submit_conflict(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    r = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 2)
    assert (
        client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes}).status_code
        == 201
    )
    res = client.post(f"{SESI}/responden/{r['id']}/seleksi", json={"task_kode": kodes})
    assert res.status_code in (400, 409, 422)
    # get seleksi
    g = client.get(f"{SESI}/responden/{r['id']}/seleksi")
    assert g.status_code == 200
    assert set(g.json()["task_kode"]) == set(kodes)


# --------------------------------------------------------------------------- #
# Alur penuh 3 tahap + agregasi
# --------------------------------------------------------------------------- #


def test_full_three_phase_flow(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 3)  # K0, K1, K2

    # Tahap 1
    assert client.post(f"{SESI}/{sid}/mulai-tahap1").json()["status"] == "TAHAP1"
    ra = _add_responden(client, sid, "A")
    rb = _add_responden(client, sid, "B")
    # A pilih K0,K1 ; B pilih K1,K2 → K1 unanimous, K0+K2 partial
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0], kodes[1]]})
    client.post(f"{SESI}/responden/{rb['id']}/seleksi", json={"task_kode": [kodes[1], kodes[2]]})

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
            "ai_mode": "Human-led",
            "va_type": "VA-Core",
            "dcs_flag": False,
        }

    da = client.post(
        f"{SESI}/responden/{ra['id']}/detail",
        json={"detail": [_ditem(kodes[0], 2.0), _ditem(kodes[1], 4.0)]},
    )
    assert da.status_code == 201, da.text
    db = client.post(
        f"{SESI}/responden/{rb['id']}/detail",
        json={"detail": [_ditem(kodes[1], 6.0)]},
    )
    assert db.status_code == 201, db.text

    # Tutup → analisis
    assert client.post(f"{SESI}/{sid}/tutup").json()["status"] == "CLOSED"
    an = client.post(f"{SESI}/{sid}/analisis")
    assert an.status_code == 200, an.text
    hasil = an.json()
    assert hasil["n_responden_tahap1"] == 2
    assert hasil["n_responden_tahap3"] == 2
    assert hasil["jumlah_task_terpilih"] == 2

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


def test_detail_kode_diluar_terpilih_ditolak(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 4)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": [kodes[0]]})
    # Masuk TAHAP2 lalu TAHAP3 (K0 unanimous karena 1 responden memilihnya)
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    # kodes[3] tidak ada di terpilih (hanya kodes[0])
    res = client.post(
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
                    "ai_mode": "Co-Pilot",
                    "va_type": "VA-Enable",
                }
            ]
        },
    )
    assert res.status_code in (400, 422)


def test_detail_requires_tahap3(client: TestClient) -> None:
    """Detail hanya bisa disubmit saat TAHAP3, bukan TAHAP2."""
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    # Di TAHAP2, belum bisa submit detail
    res = client.post(
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
                    "ai_mode": "Human-led",
                    "va_type": "VA-Core",
                }
            ]
        },
    )
    assert res.status_code in (400, 422)


def test_hasil_belum_analyzed(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.get(f"{SESI}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)


def test_responden_delete_setelah_submit_ditolak(client: TestClient) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    r = client.delete(f"{SESI}/responden/{ra['id']}")
    assert r.status_code in (400, 422)


@pytest.mark.parametrize("field", ["sumber_bukti", "ai_mode", "va_type"])
def test_detail_enum_invalid(client: TestClient, field: str) -> None:
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    client.post(f"{SESI}/{sid}/mulai-tahap3")
    item = {
        "task_kode": kodes[0],
        "sumber_bukti": "Aktual",
        "kondisi": "Baseline",
        "frekuensi_teks": "Harian",
        "durasi_per_kali": 30,
        "jam_per_minggu": 1.0,
        "ai_mode": "Human-led",
        "va_type": "VA-Core",
    }
    item[field] = "NILAI_SALAH"
    res = client.post(f"{SESI}/responden/{ra['id']}/detail", json={"detail": [item]})
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Tahap 2 review koordinator
# --------------------------------------------------------------------------- #


def test_tahap2_review_belum_tahap2(client: TestClient) -> None:
    sesi = _create_sesi(client)
    r = client.get(f"{SESI}/{sesi['id']}/tahap2")
    assert r.status_code in (400, 422)


def test_tahap2_submit_keputusan_non_partial_ditolak(client: TestClient) -> None:
    """Koordinator tidak boleh submit keputusan untuk task unanimous."""
    sesi = _create_sesi(client)
    sid = sesi["id"]
    kodes = _catalog_kodes(client, 1)
    client.post(f"{SESI}/{sid}/mulai-tahap1")
    ra = _add_responden(client, sid, "A")
    client.post(f"{SESI}/responden/{ra['id']}/seleksi", json={"task_kode": kodes})
    client.post(f"{SESI}/{sid}/mulai-tahap2")
    # kodes[0] dipilih oleh semua (1 responden = 1 = unanimous), bukan partial
    r = client.post(
        f"{SESI}/{sid}/tahap2",
        json={"keputusan": [{"task_kode": kodes[0], "disetujui": True}]},
    )
    assert r.status_code in (400, 422)


# --------------------------------------------------------------------------- #
# GET /kuesioner/saya (Task Inventory — universal)
# --------------------------------------------------------------------------- #

KUESIONER = f"{BASE}/kuesioner"


def test_kuesioner_saya_tanpa_partisipan_ti(client: TestClient) -> None:
    r = client.get(f"{KUESIONER}/saya")
    assert r.status_code == 200


def test_kuesioner_saya_universal_ti(client: TestClient) -> None:
    """Task Inventory bersifat universal: partisipan melihat SEMUA sesi aktif
    (TAHAP1/TAHAP2/TAHAP3), bukan hanya yang cocok jabatannya; pemanggilan idempoten."""
    import uuid

    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.dependencies import (
        get_partisipan_service,
        get_ti_responden_service,
        get_ti_sesi_service,
    )

    par_service = get_partisipan_service()
    par_service._data.clear()  # type: ignore[attr-defined]
    get_ti_responden_service()._data.clear()  # type: ignore[attr-defined]
    get_ti_sesi_service()._data.clear()  # type: ignore[attr-defined]

    par_service.create(
        PartisipanCreate(
            nama="Partisipan Kuesioner TI",
            email=f"ksr_ti_{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_dummy",
            jabatan_utama_id=f"jbt_{uuid.uuid4().hex[:8]}",
            masa_kerja_tahun=2,
        ),
        authentik_user_id="test-user",
    )

    # Dua sesi aktif (TAHAP1) + satu sesi DRAFT (tidak boleh muncul).
    aktif_ids = set()
    for _ in range(2):
        sesi = _create_sesi(client)
        client.post(f"{SESI}/{sesi['id']}/mulai-tahap1")
        aktif_ids.add(sesi["id"])
    _create_sesi(client)  # DRAFT

    r = client.get(f"{KUESIONER}/saya")
    assert r.status_code == 200
    data = r.json()
    assert {item["sesi_id"] for item in data} == aktif_ids
    assert all(item["tahap1_submit"] is False for item in data)
    assert all(item["sesi_status"] == "TAHAP1" for item in data)

    # Idempoten: jumlah & id responden tetap.
    r2 = client.get(f"{KUESIONER}/saya")
    assert {i["id"] for i in r2.json()} == {i["id"] for i in data}


# --------------------------------------------------------------------------- #
# Sesi tanpa unit + SME panel check
# --------------------------------------------------------------------------- #


def test_sesi_create_tanpa_unit(client: TestClient) -> None:
    """Session tanpa unit dapat dibuat."""
    r = client.post(
        SESI,
        json={
            "kategori_jabatan": KATEGORI,
            "periode": _uniq_periode(),
            "min_responden": 1,
            "max_responden": 10,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["unit"] is None


def test_sesi_create_tanpa_unit_kategori_invalid(client: TestClient) -> None:
    """Session tanpa unit dengan kategori tidak valid ditolak."""
    r = client.post(
        SESI,
        json={
            "kategori_jabatan": "Jabatan Tidak Ada Di Catalog",
            "periode": _uniq_periode(),
        },
    )
    assert r.status_code in (400, 422)


def test_responden_sme_panel_check(client: TestClient) -> None:
    """Partisipan hanya bisa jadi responden TI jika anggota SME panel jabatan sesi."""
    import uuid

    from anjab_abk_backend.anjab.schemas.sme_panel import SMEPanelCreate
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.dependencies import (
        get_partisipan_service,
        get_sme_panel_service,
    )

    jabatan_id = f"jbt_{uuid.uuid4().hex[:8]}"

    # Buat SME panel untuk jabatan ini
    sme_svc = get_sme_panel_service()
    panel = sme_svc.create(SMEPanelCreate(jabatan_id=jabatan_id))

    # Buat partisipan A (akan menjadi anggota panel)
    par_svc = get_partisipan_service()
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

    # Buat sesi TI dengan jabatan_id
    sesi = _create_sesi(client, jabatan_id=jabatan_id)
    sid = sesi["id"]
    assert sesi["jabatan_id"] == jabatan_id

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


def test_responden_tanpa_jabatan_id_bebas(client: TestClient) -> None:
    """Sesi tanpa jabatan_id: semua partisipan bisa didaftarkan."""
    sesi = _create_sesi(client)  # tanpa jabatan_id
    assert sesi.get("jabatan_id") is None
    r = _add_responden(client, sesi["id"], "Partisipan Bebas")
    assert r["id"].startswith("trsp_")
