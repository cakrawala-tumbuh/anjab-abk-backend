"""Test job asinkron: mesin status, flag fitur, dan endpoint baca."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from anjab_abk_backend.config import Settings
from anjab_abk_backend.errors import ConflictError, NotFoundError
from anjab_abk_backend.fitur import FiturNonaktifError
from anjab_abk_backend.models import AsyncJobModel
from anjab_abk_backend.schemas.async_job import TRANSISI_SAH, StatusJob
from anjab_abk_backend.schemas.common import FiturKode
from anjab_abk_backend.services.async_job_sql import SqlAsyncJobService

_HIDUP = Settings(_env_file=None, feature_ai_narrative_draft=True)
_MATI = Settings(_env_file=None, feature_ai_narrative_draft=False)


def _svc(db: Session, settings: Settings = _HIDUP) -> SqlAsyncJobService:
    return SqlAsyncJobService(db, settings)


def _buat(db: Session):
    return _svc(db).create(FiturKode.AI_NARRATIVE_DRAFT, "draf_narasi", "ref-1", "tester")


def test_job_transisi_sah_dan_updated_at_berubah(db_session: Session) -> None:
    svc = _svc(db_session)
    job = _buat(db_session)
    assert job.status == StatusJob.PENDING
    t0 = job.updated_at
    r = svc.transisi(job.id, StatusJob.RUNNING)
    assert r.status == StatusJob.RUNNING and r.updated_at > t0
    assert svc.transisi(job.id, StatusJob.SUCCEEDED).status == StatusJob.SUCCEEDED
    job2 = _buat(db_session)
    svc.transisi(job2.id, StatusJob.RUNNING)
    assert svc.transisi(job2.id, StatusJob.MANUAL_REVIEW, "x").status == StatusJob.MANUAL_REVIEW


def test_job_retry_menaikkan_percobaan(db_session: Session) -> None:
    svc = _svc(db_session)
    job = _buat(db_session)
    svc.transisi(job.id, StatusJob.RUNNING)
    svc.transisi(job.id, StatusJob.FAILED, "timeout")
    r = svc.transisi(job.id, StatusJob.PENDING)
    assert r.percobaan == 1 and r.status == StatusJob.PENDING


def test_job_transisi_tak_sah_409(db_session: Session) -> None:
    svc = _svc(db_session)
    job = _buat(db_session)
    with pytest.raises(ConflictError):
        svc.transisi(job.id, StatusJob.SUCCEEDED)
    svc.transisi(job.id, StatusJob.RUNNING)
    svc.transisi(job.id, StatusJob.SUCCEEDED)
    with pytest.raises(ConflictError):
        svc.transisi(job.id, StatusJob.RUNNING)
    job2 = _buat(db_session)
    svc.transisi(job2.id, StatusJob.RUNNING)
    svc.transisi(job2.id, StatusJob.MANUAL_REVIEW)
    with pytest.raises(ConflictError):
        svc.transisi(job2.id, StatusJob.PENDING)


def test_job_semua_pasangan_tak_sah_ditolak(db_session: Session) -> None:
    svc = _svc(db_session)
    for asal in StatusJob:
        for ke in StatusJob:
            if ke in TRANSISI_SAH[asal]:
                continue
            job = _buat(db_session)
            rec = db_session.get(AsyncJobModel, job.id)
            rec.status = asal.value
            db_session.flush()
            with pytest.raises(ConflictError):
                svc.transisi(job.id, ke)


def test_job_flag_mati_create_409_tanpa_baris(db_session: Session) -> None:
    with pytest.raises(FiturNonaktifError) as ei:
        _svc(db_session, _MATI).create(FiturKode.AI_NARRATIVE_DRAFT, "j", None, None)
    assert ei.value.error_code == "feature_disabled"
    assert db_session.query(AsyncJobModel).count() == 0


def test_job_get_tak_ada_404(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        _svc(db_session).get("tidak-ada")


def test_endpoint_job_admin_200_tanpa_dibuat_oleh(client: TestClient, db_session: Session) -> None:
    job = _buat(db_session)
    r = client.get(f"/api/v1/system/jobs/{job.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING" and body["id"] == job.id
    assert "dibuat_oleh" not in body


def test_endpoint_job_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get("/api/v1/system/jobs/abc").status_code == 401


def test_endpoint_job_non_admin_403(app, client_as) -> None:
    c = client_as("user-biasa", groups=["partisipan"])
    assert c.get("/api/v1/system/jobs/abc").status_code == 403


def test_endpoint_job_tak_ada_404(client: TestClient) -> None:
    r = client.get("/api/v1/system/jobs/acak-tidak-ada")
    assert r.status_code == 404
