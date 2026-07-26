"""Test endpoint admin backup & restore basis data (backlog 025).

Skenario positif (`test_backup_restore_round_trip`) memvalidasi ROUND-TRIP NYATA:
`pg_dump`/`pg_restore` berjalan sebagai subprocess terhadap `DATABASE_URL` yang sama
dipakai harness test — koneksi TERPISAH dari sesi SQLAlchemy `db_session` (savepoint)
yang dipakai fixture `client` untuk test lain. Perubahan lewat endpoint HTTP biasa
(`client`) TIDAK ikut ter-commit secara nyata ke basis data (hidup dalam savepoint yang
di-rollback saat teardown) — jadi test ini memakai `Session(engine)` TERPISAH dengan
commit sungguhan, supaya `pg_dump` (proses lain, koneksi baru) benar-benar melihat
datanya. Baris uji ("marker") dibersihkan di blok `finally` agar tidak mencemari
basis data nyata yang dipakai bersama sepanjang sesi test.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from anjab_abk_backend.config import Settings
from anjab_abk_backend.core.schemas.jenjang_pendidikan import (
    JenjangPendidikanCreate,
    JenjangPendidikanUpdate,
)
from anjab_abk_backend.core.services.jenjang_pendidikan_sql import SqlJenjangPendidikanService
from anjab_abk_backend.db import get_db_settings
from anjab_abk_backend.main import create_app
from anjab_abk_backend.services.backup import BackupService

BASE = "/api/v1/system"


def _db_name() -> str:
    return BackupService(get_db_settings()).database_name


def _commit_marker(engine, kode: str, nama: str) -> str:
    """Buat baris `JenjangPendidikan` via sesi TERPISAH dengan commit NYATA (bukan
    savepoint fixture `db_session`) — agar terlihat oleh `pg_dump` (koneksi lain)."""
    with Session(engine) as s:
        svc = SqlJenjangPendidikanService(s)
        rec = svc.create(JenjangPendidikanCreate(kode=kode, nama=nama, urutan=999))
        s.commit()
        return rec.id


def _update_marker_nama(engine, jp_id: str, nama: str) -> None:
    with Session(engine) as s:
        svc = SqlJenjangPendidikanService(s)
        svc.update(jp_id, JenjangPendidikanUpdate(nama=nama))
        s.commit()


def _read_marker_nama(engine, jp_id: str) -> str:
    with Session(engine) as s:
        svc = SqlJenjangPendidikanService(s)
        return svc.get(jp_id).nama


def _delete_marker(engine, jp_id: str) -> None:
    with Session(engine) as s:
        svc = SqlJenjangPendidikanService(s)
        try:
            svc.delete(jp_id)
            s.commit()
        except Exception:
            s.rollback()


@pytest.fixture
def marker_kode() -> str:
    return f"BKP{uuid.uuid4().hex[:8].upper()}"


def test_backup_restore_round_trip(client: TestClient, engine, marker_kode: str) -> None:
    jp_id = _commit_marker(engine, marker_kode, "Nama Asli")
    try:
        r = client.post(f"{BASE}/backup")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert "attachment;" in r.headers["content-disposition"]
        assert ".dump" in r.headers["content-disposition"]
        dump_bytes = r.content
        assert dump_bytes[:5] == b"PGDMP", "keluaran pg_dump custom format diawali PGDMP"

        # Ubah data SETELAH backup diambil — harus kembali seperti semula pasca restore.
        _update_marker_nama(engine, jp_id, "Nama Diubah Setelah Backup")
        assert _read_marker_nama(engine, jp_id) == "Nama Diubah Setelah Backup"

        files = {"berkas": ("backup.dump", dump_bytes, "application/octet-stream")}
        data = {"konfirmasi": _db_name()}
        rr = client.post(f"{BASE}/restore", files=files, data=data)
        assert rr.status_code == 200, rr.text
        body = rr.json()
        assert body["status"] == "ok"
        assert body["revisi_alembic"]
        assert body["peringatan"] == []

        assert _read_marker_nama(engine, jp_id) == "Nama Asli"
    finally:
        _delete_marker(engine, jp_id)


def test_backup_requires_admin(anon_client: TestClient) -> None:
    assert anon_client.post(f"{BASE}/backup").status_code == 401


def test_backup_non_admin_forbidden(client_as) -> None:
    non_admin = client_as("backup-nonadmin", groups=["partisipan"])
    assert non_admin.post(f"{BASE}/backup").status_code == 403


def test_restore_requires_admin(anon_client: TestClient) -> None:
    r = anon_client.post(
        f"{BASE}/restore",
        files={"berkas": ("x.dump", b"junk")},
        data={"konfirmasi": "whatever"},
    )
    assert r.status_code == 401


def test_restore_non_admin_forbidden(client_as) -> None:
    non_admin = client_as("restore-nonadmin", groups=["partisipan"])
    r = non_admin.post(
        f"{BASE}/restore",
        files={"berkas": ("x.dump", b"junk")},
        data={"konfirmasi": "whatever"},
    )
    assert r.status_code == 403


def test_restore_konfirmasi_salah_ditolak_422(client: TestClient) -> None:
    """`konfirmasi` yang tidak cocok ditolak SEBELUM `pg_restore` dijalankan sama
    sekali — berkas junk tidak masalah karena tidak pernah diproses."""
    r = client.post(
        f"{BASE}/restore",
        files={"berkas": ("x.dump", b"bukan dump asli")},
        data={"konfirmasi": "nama-basis-data-yang-salah"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "message" in body


def test_restore_berkas_bukan_dump_valid_ditolak_422_tanpa_bocor_stacktrace(
    client: TestClient,
) -> None:
    """`konfirmasi` benar tapi berkas bukan dump `pg_dump` valid → `pg_restore` gagal,
    dipetakan ke envelope error baku (bukan 500 telanjang / stack trace)."""
    r = client.post(
        f"{BASE}/restore",
        files={"berkas": ("x.dump", b"ini jelas bukan dump pg_dump format custom")},
        data={"konfirmasi": _db_name()},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "Traceback" not in r.text


def test_body_besar_ke_endpoint_non_restore_tetap_413(anon_client: TestClient) -> None:
    """Batas umum 1 MiB TETAP berlaku untuk path selain `/system/restore`."""
    payload = b"x" * (2 * 1024 * 1024)
    r = anon_client.post(
        "/api/v1/health", content=payload, headers={"Content-Type": "application/octet-stream"}
    )
    assert r.status_code == 413


def test_restore_body_melebihi_batas_khusus_ditolak_413() -> None:
    """`restore_max_body_bytes` (bukan `max_request_body_bytes` umum) berlaku untuk
    `/api/v1/system/restore` — diverifikasi dengan batas kecil agar tidak perlu
    membangkitkan berkas ratusan MB di test."""
    settings = Settings(
        docs_enabled=True,
        cors_origins=[],
        allowed_hosts=["*"],
        require_if_match=False,
        max_request_body_bytes=1_048_576,
        restore_max_body_bytes=1_000,
    )
    app = create_app(settings=settings)
    with TestClient(app) as c:
        big = b"x" * 2_000
        r = c.post(
            f"{BASE}/restore",
            files={"berkas": ("x.dump", big)},
            data={"konfirmasi": "apa-saja"},
        )
    assert r.status_code == 413


def test_openapi_memuat_endpoint_backup_restore(anon_client: TestClient) -> None:
    schema = anon_client.get("/openapi.json").json()
    backup_op = schema["paths"][f"{BASE}/backup"]["post"]
    restore_op = schema["paths"][f"{BASE}/restore"]["post"]
    assert "401" in backup_op["responses"]
    assert "403" in backup_op["responses"]
    assert "401" in restore_op["responses"]
    assert "403" in restore_op["responses"]
    assert "422" in restore_op["responses"]
    assert "413" in restore_op["responses"]
