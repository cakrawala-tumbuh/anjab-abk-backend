"""Regresi FK `ON DELETE CASCADE`: hapus sesi/responden membersihkan seluruh anaknya.

Baris disisipkan LANGSUNG lewat `db_session` (bukan API) agar test tidak bergantung
pada alur bisnis (submit, panel, dsb.) — yang diuji di sini murni perilaku FK di
level DB saat sesi/responden dihapus.

ID ditangkap ke variabel LOKAL sebelum memanggil delete — setelah `SqlXSesiService.
delete()` memanggil `session.expire_all()`, atribut objek ORM yang barisnya sudah
lenyap lewat CASCADE (bukan `session.delete()` langsung) akan raise
`ObjectDeletedError` saat diakses lagi.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.models import (
    DcsJawabanModel,
    DcsRespondenModel,
    DcsSesiModel,
    OpmJawabanModel,
    OpmRespondenModel,
    OpmSesiModel,
    TiDetailModel,
    TiRespondenModel,
    TiSeleksiModel,
    TiSesiModel,
    TiTahap2Model,
    WcpJawabanModel,
    WcpRespondenModel,
    WcpSesiModel,
)


def _count(db_session: Session, model, **filters) -> int:
    stmt = select(func.count()).select_from(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return db_session.scalar(stmt) or 0


def test_hapus_dcs_sesi_cascade_responden_jawaban(client: TestClient, db_session: Session) -> None:
    sesi_id = f"dses_{uuid.uuid4().hex[:8]}"
    rsp_id = f"drsp_{uuid.uuid4().hex[:8]}"
    db_session.add(DcsSesiModel(id=sesi_id, periode="2026-01", status="DRAFT", catatan=None))
    db_session.flush()
    db_session.add(
        DcsRespondenModel(id=rsp_id, sesi_id=sesi_id, jabatan_label="Guru", sudah_submit=False)
    )
    db_session.flush()
    db_session.add(
        DcsJawabanModel(
            id=f"djwb_{uuid.uuid4().hex[:8]}", responden_id=rsp_id, item_id="D01", skor_raw=3
        )
    )
    db_session.flush()

    r = client.delete(f"/api/v1/dcs/sesi/{sesi_id}", params={"paksa": True})
    assert r.status_code == 204

    assert _count(db_session, DcsRespondenModel, sesi_id=sesi_id) == 0
    assert _count(db_session, DcsJawabanModel, responden_id=rsp_id) == 0


def test_hapus_wcp_sesi_cascade_responden_jawaban(client: TestClient, db_session: Session) -> None:
    sesi_id = f"wses_{uuid.uuid4().hex[:8]}"
    rsp_id = f"wrsp_{uuid.uuid4().hex[:8]}"
    db_session.add(WcpSesiModel(id=sesi_id, periode="2026-01", status="DRAFT", catatan=None))
    db_session.flush()
    db_session.add(
        WcpRespondenModel(id=rsp_id, sesi_id=sesi_id, jabatan_label="Guru", sudah_submit=False)
    )
    db_session.flush()
    db_session.add(
        WcpJawabanModel(
            id=f"wjwb_{uuid.uuid4().hex[:8]}", responden_id=rsp_id, item_id="W01", skor_raw=3
        )
    )
    db_session.flush()

    r = client.delete(f"/api/v1/wcp/sesi/{sesi_id}", params={"paksa": True})
    assert r.status_code == 204

    assert _count(db_session, WcpRespondenModel, sesi_id=sesi_id) == 0
    assert _count(db_session, WcpJawabanModel, responden_id=rsp_id) == 0


def test_hapus_opm_sesi_cascade_responden_jawaban(client: TestClient, db_session: Session) -> None:
    sesi_id = f"opses_{uuid.uuid4().hex[:8]}"
    rsp_id = f"oprs_{uuid.uuid4().hex[:8]}"
    db_session.add(
        OpmSesiModel(
            id=sesi_id,
            jabatan_id=f"jbt_{uuid.uuid4().hex[:8]}",
            ti_sesi_id=f"tises_{uuid.uuid4().hex[:8]}",
            periode="2026-01",
            status="DRAFT",
        )
    )
    db_session.flush()
    db_session.add(
        OpmRespondenModel(id=rsp_id, sesi_id=sesi_id, jabatan_label="Guru", sudah_submit=False)
    )
    db_session.flush()
    db_session.add(
        OpmJawabanModel(
            id=f"opjw_{uuid.uuid4().hex[:8]}",
            responden_id=rsp_id,
            task_kode="TI001",
            importance=3,
            frequency=3,
            criticality=3,
        )
    )
    db_session.flush()

    r = client.delete(f"/api/v1/opm/sesi/{sesi_id}", params={"paksa": True})
    assert r.status_code == 204

    assert _count(db_session, OpmRespondenModel, sesi_id=sesi_id) == 0
    assert _count(db_session, OpmJawabanModel, responden_id=rsp_id) == 0


def test_hapus_ti_sesi_cascade_responden_seleksi_detail_tahap2(
    client: TestClient, db_session: Session
) -> None:
    sesi_id = f"tises_{uuid.uuid4().hex[:8]}"
    rsp_id = f"tirs_{uuid.uuid4().hex[:8]}"
    db_session.add(
        TiSesiModel(
            id=sesi_id, jabatan_id=f"jbt_{uuid.uuid4().hex[:8]}", periode="2026-01", status="DRAFT"
        )
    )
    db_session.flush()
    db_session.add(TiRespondenModel(id=rsp_id, sesi_id=sesi_id))
    db_session.flush()
    db_session.add(
        TiSeleksiModel(
            id=f"tisl_{uuid.uuid4().hex[:8]}",
            responden_id=rsp_id,
            sesi_id=sesi_id,
            task_kode="TI001",
        )
    )
    db_session.add(
        TiDetailModel(
            id=f"tidt_{uuid.uuid4().hex[:8]}",
            responden_id=rsp_id,
            sesi_id=sesi_id,
            task_kode="TI001",
            sumber_bukti="LOGBOOK",
            kondisi="NORMAL",
            frekuensi_teks="setiap hari",
            durasi_per_kali=30,
            jam_per_minggu=2.5,
            ai_mode="MANDIRI",
            va_type="VA",
        )
    )
    db_session.add(
        TiTahap2Model(
            id=f"tth2_{uuid.uuid4().hex[:8]}", sesi_id=sesi_id, task_kode="TI001", disetujui=True
        )
    )
    db_session.flush()

    r = client.delete(f"/api/v1/task-inventory/sesi/{sesi_id}", params={"paksa": True})
    assert r.status_code == 204

    assert _count(db_session, TiRespondenModel, sesi_id=sesi_id) == 0
    assert _count(db_session, TiSeleksiModel, sesi_id=sesi_id) == 0
    assert _count(db_session, TiDetailModel, sesi_id=sesi_id) == 0
    assert _count(db_session, TiTahap2Model, sesi_id=sesi_id) == 0


def test_hapus_dcs_responden_cascade_jawaban(client: TestClient, db_session: Session) -> None:
    """Regresi: `responden_sql.py::delete()` dulu tidak menghapus jawaban anaknya."""
    sesi_id = f"dses_{uuid.uuid4().hex[:8]}"
    rsp_id = f"drsp_{uuid.uuid4().hex[:8]}"
    db_session.add(DcsSesiModel(id=sesi_id, periode="2026-01", status="OPEN"))
    db_session.flush()
    db_session.add(
        DcsRespondenModel(id=rsp_id, sesi_id=sesi_id, jabatan_label="Guru", sudah_submit=False)
    )
    db_session.flush()
    db_session.add(
        DcsJawabanModel(
            id=f"djwb_{uuid.uuid4().hex[:8]}", responden_id=rsp_id, item_id="D01", skor_raw=3
        )
    )
    db_session.flush()

    r = client.delete(f"/api/v1/dcs/sesi/responden/{rsp_id}")
    assert r.status_code == 204

    assert _count(db_session, DcsJawabanModel, responden_id=rsp_id) == 0
