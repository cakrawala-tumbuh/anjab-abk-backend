"""Test endpoint GET /time-study/kuesioner/saya (assignment-based, tanpa sesi)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

KUESIONER_BASE = "/api/v1/time-study/kuesioner"
PNG_BASE = "/api/v1/time-study/penugasan"


def _build_partisipan(db_session, *, authentik_user_id: str = "test-user"):
    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    par_service = SqlPartisipanService(db_session)
    return par_service.create(
        PartisipanCreate(
            nama="Partisipan Kuesioner TS",
            email=f"ksr_ts_{uuid.uuid4().hex[:4]}@test.id",
            sekolah_id="skl_dummy",
            jabatan_utama_id=f"jbt_{uuid.uuid4().hex[:8]}",
            masa_kerja_tahun=2,
        ),
        authentik_user_id=authentik_user_id,
    )


def test_kuesioner_saya_tanpa_partisipan(client: TestClient) -> None:
    r = client.get(f"{KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_tanpa_penugasan(client: TestClient, db_session) -> None:
    """Partisipan ada tapi belum ditugaskan Time Study — kuesioner kosong."""
    _build_partisipan(db_session)
    r = client.get(f"{KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_dengan_penugasan_aktif(client: TestClient, db_session) -> None:
    par = _build_partisipan(db_session)

    r = client.get(f"{KUESIONER_BASE}/saya")
    assert r.json() == []

    assign_r = client.post(PNG_BASE, json={"partisipan_id": par.id, "aktif": True})
    assert assign_r.status_code == 201

    r2 = client.get(f"{KUESIONER_BASE}/saya")
    assert r2.status_code == 200
    data = r2.json()
    assert len(data) == 1
    assert data[0]["aktif"] is True
    assert data[0]["jumlah_log"] == 0


def test_kuesioner_saya_penugasan_nonaktif_disembunyikan(client: TestClient, db_session) -> None:
    par = _build_partisipan(db_session)
    assign_r = client.post(PNG_BASE, json={"partisipan_id": par.id, "aktif": False})
    assert assign_r.status_code == 201

    r = client.get(f"{KUESIONER_BASE}/saya")
    assert r.status_code == 200
    assert r.json() == []


def test_kuesioner_saya_jumlah_log_bertambah(client: TestClient, db_session) -> None:
    par = _build_partisipan(db_session)
    png = client.post(PNG_BASE, json={"partisipan_id": par.id, "aktif": True}).json()

    client.post(
        f"{PNG_BASE}/{png['id']}/log",
        json={
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
        },
    )

    r = client.get(f"{KUESIONER_BASE}/saya")
    assert r.json()[0]["jumlah_log"] == 1
