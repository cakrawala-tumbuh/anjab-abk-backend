"""Tes metrik alur narasi UX-13: detak menit aktif dan `GET /api/v1/narasi/metrik`."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from anjab_abk_backend.models import NarasiMenitAktifModel, NarasiSumberModel
from anjab_abk_backend.narasi.schemas.kasus import EventKind, RevisionOrigin, StatusNarasi
from anjab_abk_backend.narasi.schemas.mesin import (
    AKTOR_AI_WORKER,
    AktorNarasi,
    KutipanSumber,
    NarasiKasusCreate,
)
from anjab_abk_backend.narasi.services.metrik_sql import SqlNarasiMetrikService
from anjab_abk_backend.narasi.services.narasi_sql import SqlNarasiService

METRIK = "/api/v1/narasi/metrik"
KASUS = "/api/v1/narasi/kasus"
AI = AktorNarasi(key=AKTOR_AI_WORKER, role="SYSTEM")
TIM = AktorNarasi(key="tim-x", role="tim-kajian")


@pytest.fixture
def svc(db_session):
    return SqlNarasiService(db_session)


@pytest.fixture
def metrik_svc(db_session):
    return SqlNarasiMetrikService(db_session)


@pytest.fixture
def sumber(db_session):
    teks = "teks sumber"
    rec = NarasiSumberModel(
        id=str(uuid.uuid4()),
        judul="Pedoman",
        jenis="SINTETIS",
        versi="v1",
        periode="2026/27",
        teks=teks,
        teks_hash=hashlib.sha256(teks.encode()).hexdigest(),
        dibuat_oleh="t",
    )
    db_session.add(rec)
    db_session.flush()
    return KutipanSumber(
        sumber_id=rec.id, source_hash=rec.teks_hash, basis_relation="DIRECT", source_span="1-5"
    )


def _kasus(svc, kind="F1_FORMAL"):
    return svc.buat_kasus(
        NarasiKasusCreate(
            instrument_id="wcp",
            field_key=f"f-{uuid.uuid4().hex[:8]}",
            peran_ref="guru",
            periode="2026/27",
            narrative_kind=kind,
            intended_use="uji",
            permission_scope="tim",
            sensitivity_class="NONPRIBADI",
        ),
        AI,
    )


def _versi(svc, kasus, sumber=None, status=StatusNarasi.AI_DRAFT):
    return svc.tambah_versi(
        kasus.id,
        revision_origin=RevisionOrigin.AI_DRAFT,
        status_hasil=status,
        teks="draf" if sumber is not None else None,
        sumber=[sumber] if sumber is not None else [],
        supersedes_id=None,
        aktor=AI,
    )


def _tim(client_as, subject="tim-metrik"):
    return client_as(subject, groups=["tim-kajian"])


def _rentang():
    h = datetime.now(UTC).date()
    kemarin, besok = h - timedelta(days=1), h + timedelta(days=1)
    return {"dari": kemarin.isoformat(), "sampai": besok.isoformat()}


def _jumlah_baris(db_session, narasi_id):
    return db_session.scalar(
        select(func.count())
        .select_from(NarasiMenitAktifModel)
        .where(NarasiMenitAktifModel.narasi_id == narasi_id)
    )


def test_detak_ganda_satu_menit_satu_baris_menit_berbeda_dua(client_as, svc, db_session):
    k = _kasus(svc)
    c = _tim(client_as)
    for _ in range(2):
        r = c.post(f"{KASUS}/{k.id}/menit-aktif")
        assert r.status_code == 204 and r.content == b""
    jumlah = _jumlah_baris(db_session, k.id)
    assert jumlah in (1, 2)  # 2 hanya bila batas menit terlewati di antara dua panggilan
    layanan = SqlNarasiMetrikService(db_session)
    dasar = datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)
    layanan.catat_menit_aktif(k.id, "orang-a", dasar)
    layanan.catat_menit_aktif(k.id, "orang-a", dasar + timedelta(seconds=20))
    assert _jumlah_baris(db_session, k.id) == jumlah + 1
    layanan.catat_menit_aktif(k.id, "orang-a", dasar + timedelta(minutes=1))
    layanan.catat_menit_aktif(k.id, "orang-b", dasar)
    assert _jumlah_baris(db_session, k.id) == jumlah + 3
    menit = db_session.scalars(
        select(NarasiMenitAktifModel.menit).where(NarasiMenitAktifModel.actor_key == "orang-a")
    ).all()
    assert all(m.second == 0 and m.microsecond == 0 for m in menit)


def test_detak_actor_dari_token_dan_kasus_tak_ada_404(client_as, svc, db_session):
    k = _kasus(svc)
    _tim(client_as, "reviewer-1").post(f"{KASUS}/{k.id}/menit-aktif")
    aktor = db_session.scalars(
        select(NarasiMenitAktifModel.actor_key).where(NarasiMenitAktifModel.narasi_id == k.id)
    ).all()
    assert aktor == ["reviewer-1"]
    r = _tim(client_as).post(f"{KASUS}/{uuid.uuid4()}/menit-aktif")
    assert r.status_code == 404


def test_detak_bukan_tim_403_tanpa_token_401(client_as, anon_client, svc):
    k = _kasus(svc)
    bukan_tim = client_as("u", groups=["partisipan"])
    assert bukan_tim.post(f"{KASUS}/{k.id}/menit-aktif").status_code == 403
    assert anon_client.post(f"{KASUS}/{k.id}/menit-aktif").status_code == 401


def test_metrik_tiga_keputusan_rate_sepertiga(client_as, svc, sumber):
    k1, k2, k3 = _kasus(svc), _kasus(svc), _kasus(svc)
    v = [_versi(svc, k, sumber) for k in (k1, k2, k3)]
    svc.catat_event(k1.id, v[0].id, EventKind.TEAM_APPROVE, TIM, None)
    svc.catat_event(k2.id, v[1].id, EventKind.TEAM_REVISE, TIM, None)
    svc.catat_event(k3.id, v[2].id, EventKind.TEAM_REJECT, TIM, "ditolak karena salah")
    d = _tim(client_as).get(METRIK, params=_rentang()).json()
    assert d["jumlah_keputusan"] == 3
    assert d["correction_rate"] == 0.3333 and d["rejection_rate"] == 0.3333
    assert d["source_coverage"] == 1.0
    assert d["menit_aktif_total"] == 0 and d["menit_aktif_median_per_kasus"] is None
    assert d["metrik_ditahan"] == [{"kode": "false_negative", "alasan": "menunggu OD-13"}]
    assert not [key for key in d if "negative" in key]


def test_metrik_source_coverage_campuran_dan_filter_kind(client_as, svc, sumber):
    f1 = _kasus(svc, "F1_FORMAL")
    f2 = _kasus(svc, "F2_ACTUAL")
    v1 = _versi(svc, f1, sumber)
    v2 = _versi(svc, f2, None, StatusNarasi.NEED_FACT)
    svc.catat_event(f1.id, v1.id, EventKind.TEAM_APPROVE, TIM, None)
    svc.catat_event(f2.id, v2.id, EventKind.NEED_SOURCE, TIM, "butuh sumber lain")
    c = _tim(client_as)
    semua = c.get(METRIK, params=_rentang()).json()
    assert semua["source_coverage"] == 0.5 and semua["jumlah_keputusan"] == 2
    assert semua["correction_rate"] == 0.0
    f1_saja = c.get(METRIK, params={**_rentang(), "narrative_kind": "F1_FORMAL"}).json()
    assert f1_saja["jumlah_keputusan"] == 1 and f1_saja["source_coverage"] == 1.0
    f2_saja = c.get(METRIK, params={**_rentang(), "narrative_kind": "F2_ACTUAL"}).json()
    assert f2_saja["jumlah_keputusan"] == 1 and f2_saja["source_coverage"] == 0.0


def test_metrik_median_menit_aktif_dua_kasus_tiga_dan_lima(client_as, svc, metrik_svc):
    a, b = _kasus(svc), _kasus(svc)
    sekarang = datetime.now(UTC)
    for i in range(3):
        metrik_svc.catat_menit_aktif(a.id, "r", sekarang.replace(minute=i))
    for i in range(5):
        metrik_svc.catat_menit_aktif(b.id, "r", sekarang.replace(minute=i))
    d = _tim(client_as).get(METRIK, params=_rentang()).json()
    assert d["menit_aktif_total"] == 8
    assert d["menit_aktif_median_per_kasus"] == 4.0


def test_metrik_rentang_tanpa_data_rasio_null(client_as):
    d = _tim(client_as).get(METRIK, params={"dari": "2020-01-01", "sampai": "2020-01-31"}).json()
    assert d["jumlah_keputusan"] == 0
    assert d["correction_rate"] is None and d["rejection_rate"] is None
    assert d["source_coverage"] is None and d["menit_aktif_median_per_kasus"] is None
    assert d["menit_aktif_total"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"dari": "2026-02-01", "sampai": "2026-01-01"},
        {"dari": "2025-01-01", "sampai": "2026-01-02"},
        {"dari": "bukan-tanggal", "sampai": "2026-01-02"},
        {"dari": "2026-01-01"},
    ],
)
def test_metrik_parameter_salah_422(client_as, params):
    assert _tim(client_as).get(METRIK, params=params).status_code == 422


def test_metrik_rentang_366_hari_sah(client_as):
    r = _tim(client_as).get(METRIK, params={"dari": "2025-01-01", "sampai": "2025-12-31"})
    assert r.status_code == 200
    r = _tim(client_as).get(METRIK, params={"dari": "2024-01-01", "sampai": "2024-12-31"})
    assert r.status_code == 200  # 2024 kabisat: 366 hari tepat


def test_metrik_bukan_tim_403_tanpa_token_401(client_as, anon_client):
    assert client_as("u", groups=["partisipan"]).get(METRIK, params=_rentang()).status_code == 403
    assert anon_client.get(METRIK, params=_rentang()).status_code == 401


def test_menit_aktif_append_only_update_dan_delete_ditolak(svc, metrik_svc, db_session):
    k = _kasus(svc)
    metrik_svc.catat_menit_aktif(k.id, "r")
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("UPDATE narasi_menit_aktif SET actor_key = 'lain'"))
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("DELETE FROM narasi_menit_aktif"))
