"""Tes rute antrean tinjauan Tim: `/api/v1/narasi/antrean` dan `/narasi/kasus/{id}/tinjauan`."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from anjab_abk_backend.models import NarasiEventModel, NarasiKasusModel, NarasiSumberModel
from anjab_abk_backend.narasi.schemas.kasus import EventKind, RevisionOrigin, StatusNarasi
from anjab_abk_backend.narasi.schemas.mesin import (
    AKTOR_AI_WORKER,
    AktorNarasi,
    KutipanSumber,
    NarasiKasusCreate,
)
from anjab_abk_backend.narasi.services.narasi_sql import SqlNarasiService

ANTREAN = "/api/v1/narasi/antrean"
KASUS = "/api/v1/narasi/kasus"
AI = AktorNarasi(key=AKTOR_AI_WORKER, role="SYSTEM")
META = {
    "contradictions": ["a bertentangan dengan b", "c"],
    "unknowns": ["u1"],
    "missing_facts": [],
    "claim_to_source_map": {"k1": "s1"},
    "recommended_review_scope": "pasal 3",
    "label_dokumenter": "DRAF AI",
}


@pytest.fixture
def svc(db_session):
    return SqlNarasiService(db_session)


@pytest.fixture
def sumber(db_session):
    teks = "teks sumber lengkap"
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


def _kasus(svc, **ubah):
    nilai = {
        "instrument_id": "wcp",
        "field_key": f"f-{uuid.uuid4().hex[:8]}",
        "peran_ref": "guru",
        "periode": "2026/27",
        "narrative_kind": "F1_FORMAL",
        "intended_use": "uji",
        "permission_scope": "tim",
        "sensitivity_class": "NONPRIBADI",
    }
    nilai.update(ubah)
    return svc.buat_kasus(NarasiKasusCreate(**nilai), AI)


def _draf(svc, sumber, **ubah):
    """Kasus berstatus AI_DRAFT dengan satu versi AI ber-metadata."""
    k = _kasus(svc, **ubah)
    v = svc.tambah_versi(
        k.id,
        revision_origin=RevisionOrigin.AI_DRAFT,
        status_hasil=StatusNarasi.AI_DRAFT,
        teks="draf AI",
        sumber=[sumber],
        supersedes_id=None,
        aktor=AI,
        metadata_ai=dict(META),
    )
    return k, v


def _need_fact(svc):
    k = _kasus(svc)
    v = svc.tambah_versi(
        k.id,
        revision_origin=RevisionOrigin.AI_DRAFT,
        status_hasil=StatusNarasi.NEED_FACT,
        teks=None,
        sumber=[],
        supersedes_id=None,
        aktor=AI,
    )
    return k, v


def _tim(client_as, subject="tim-antrean"):
    return client_as(subject, groups=["tim-kajian"])


def _tinjau(c, narasi_id, aksi, versi_id, **ekstra):
    return c.post(
        f"{KASUS}/{narasi_id}/tinjauan",
        json={"aksi": aksi, "narasi_versi_id": versi_id, **ekstra},
    )


def test_antrean_tiga_status_urut_dan_filter(client_as, svc, sumber, db_session):
    k1, _ = _draf(svc, sumber, periode="2026/27")
    k2, _ = _need_fact(svc)
    k3 = _kasus(svc)  # SOURCE_CHECKED: bukan antrean
    k4, v4 = _draf(svc, sumber, instrument_id="dcs")
    svc.catat_event(k4.id, v4.id, EventKind.TEAM_APPROVE, AktorNarasi("x", "r"), None)
    dasar = datetime(2026, 1, 1, tzinfo=UTC)
    for i, k in enumerate((k2, k1)):
        db_session.execute(
            update(NarasiKasusModel)
            .where(NarasiKasusModel.id == k.id)
            .values(updated_at=dasar + timedelta(days=i))
        )
    c = _tim(client_as)
    d = c.get(ANTREAN).json()
    ids = [x["narasi_id"] for x in d["items"]]
    assert k3.id not in ids and k4.id not in ids
    assert ids.index(k2.id) < ids.index(k1.id)
    assert "teks" not in d["items"][0]
    item = next(x for x in d["items"] if x["narasi_id"] == k1.id)
    assert item["jumlah_sumber"] == 1
    assert item["jumlah_kontradiksi"] == 2
    assert item["label_dokumenter"] == "DRAF AI"
    assert item["revision_no"] == 1
    assert c.get(ANTREAN, params={"status": "NEED_FACT"}).json()["items"][0]["narasi_id"] == k2.id
    assert c.get(ANTREAN, params={"status": "TEAM_VERIFIED"}).status_code == 422
    assert c.get(ANTREAN, params={"instrument_id": "tak-ada"}).json()["total"] == 0
    assert c.get(ANTREAN, params={"periode": "2026/27"}).json()["total"] >= 2


def test_detail_memuat_sumber_kontradiksi_dan_paparan(client_as, svc, sumber):
    k, v = _draf(svc, sumber)
    d = _tim(client_as).get(f"{ANTREAN}/{k.id}").json()
    assert d["teks"] == "draf AI"
    assert d["versi_id"] == v.id
    assert d["sumber"][0]["teks"] == "teks sumber lengkap"
    assert d["sumber"][0]["judul"] == "Pedoman"
    assert d["contradictions"] == META["contradictions"]
    assert d["unknowns"] == ["u1"]
    assert d["claim_to_source_map"] == {"k1": "s1"}
    assert d["recommended_review_scope"] == "pasal 3"
    assert d["paparan"] == "TIDAK_BERLAKU"
    assert "keluaran" not in d and "metadata_ai" not in d


def test_detail_negatif_409_dan_404(client_as, svc, sumber):
    k = _kasus(svc)
    c = _tim(client_as)
    r = c.get(f"{ANTREAN}/{k.id}")
    assert r.status_code == 409
    assert r.json()["error"] == "narasi_tidak_dalam_antrean"
    k2, v2 = _draf(svc, sumber)
    assert _tinjau(c, k2.id, "TERIMA", v2.id).status_code == 201
    assert c.get(f"{ANTREAN}/{k2.id}").status_code == 409
    assert c.get(f"{ANTREAN}/{uuid.uuid4()}").status_code == 404


def test_empat_aksi_status_dan_event(client_as, svc, sumber, db_session):
    c = _tim(client_as, "tim-empat")
    peta = {
        "TERIMA": ("TEAM_APPROVE", "TEAM_VERIFIED", {}),
        "TOLAK": ("TEAM_REJECT", "SOURCE_CHECKED", {"catatan": "tidak sesuai sumber"}),
        "BUTUH_SUMBER": ("NEED_SOURCE", "NEED_FACT", {"catatan": "perlu dokumen"}),
    }
    for aksi, (kind, status, ekstra) in peta.items():
        k, v = _draf(svc, sumber)
        r = _tinjau(c, k.id, aksi, v.id, **ekstra)
        assert r.status_code == 201, r.text
        e = r.json()
        assert e["event_kind"] == kind and e["ke_status"] == status
        assert e["actor_key"] == "tim-empat" and e["actor_role"] == "tim-kajian"
        assert e["narasi_versi_id"] == v.id
        assert svc.get_kasus(k.id).status.value == status
    k, v = _draf(svc, sumber)
    r = _tinjau(
        c,
        k.id,
        "KOREKSI",
        v.id,
        teks="teks koreksi",
        sumber=[{"sumber_id": sumber.sumber_id, "basis_relation": "DIRECT"}],
    )
    assert r.status_code == 201, r.text
    e = r.json()
    baru = svc.versi_terbaru(k.id)
    assert baru.id != v.id and baru.revision_no == 2
    assert baru.revision_origin == RevisionOrigin.REVIEWER_EDIT
    assert baru.supersedes_id == v.id
    assert e["narasi_versi_id"] == baru.id
    assert e["event_kind"] == "TEAM_REVISE" and e["ke_status"] == "TEAM_REVIEW"
    n = db_session.scalar(
        select(func.count()).select_from(NarasiEventModel).where(NarasiEventModel.narasi_id == k.id)
    )
    assert n == 1


def test_catatan_wajib_pada_tolak_dan_butuh_sumber(client_as, svc, sumber):
    c = _tim(client_as)
    k, v = _draf(svc, sumber)
    for aksi in ("TOLAK", "BUTUH_SUMBER"):
        assert _tinjau(c, k.id, aksi, v.id).status_code == 422
        assert _tinjau(c, k.id, aksi, v.id, catatan="abc").status_code == 422
    assert svc.get_kasus(k.id).status == StatusNarasi.AI_DRAFT


def test_koreksi_tanpa_teks_atau_sumber_422(client_as, svc, sumber):
    c = _tim(client_as)
    k, v = _draf(svc, sumber)
    assert _tinjau(c, k.id, "KOREKSI", v.id).status_code == 422
    assert _tinjau(c, k.id, "KOREKSI", v.id, teks="x").status_code == 422
    r = _tinjau(
        c,
        k.id,
        "KOREKSI",
        v.id,
        teks="x",
        sumber=[{"sumber_id": "tak-ada", "basis_relation": "DIRECT"}],
    )
    assert r.status_code == 422
    assert svc.versi_terbaru(k.id).id == v.id


def test_versi_basi_409_tanpa_baris(client_as, svc, sumber, db_session):
    c = _tim(client_as)
    k, v = _draf(svc, sumber)
    koreksi = {
        "teks": "x",
        "sumber": [{"sumber_id": sumber.sumber_id, "basis_relation": "DIRECT"}],
    }
    for aksi, ekstra in (("TERIMA", {}), ("KOREKSI", koreksi)):
        r = _tinjau(c, k.id, aksi, str(uuid.uuid4()), **ekstra)
        assert r.status_code == 409
        assert r.json()["error"] == "versi_basi"
    n = db_session.scalar(
        select(func.count()).select_from(NarasiEventModel).where(NarasiEventModel.narasi_id == k.id)
    )
    assert n == 0 and svc.versi_terbaru(k.id).id == v.id


def test_terima_need_fact_409_dan_koreksi_need_fact_berjalan(client_as, svc, sumber):
    c = _tim(client_as)
    k, v = _need_fact(svc)
    r = _tinjau(c, k.id, "TERIMA", v.id)
    assert r.status_code == 409
    assert r.json()["error"] == "narasi_tanpa_teks"
    assert svc.get_kasus(k.id).status == StatusNarasi.NEED_FACT
    r = _tinjau(
        c,
        k.id,
        "KOREKSI",
        v.id,
        teks="teks dari reviewer",
        sumber=[{"sumber_id": sumber.sumber_id, "basis_relation": "DIRECT"}],
    )
    assert r.status_code == 201, r.text
    assert r.json()["ke_status"] == "TEAM_REVIEW"


def test_tinjauan_pada_team_verified_409_dan_id_tak_dikenal_404(client_as, svc, sumber):
    c = _tim(client_as)
    k, v = _draf(svc, sumber)
    assert _tinjau(c, k.id, "TERIMA", v.id).status_code == 201
    assert _tinjau(c, k.id, "TERIMA", v.id).status_code == 409
    assert _tinjau(c, str(uuid.uuid4()), "TERIMA", v.id).status_code == 404


def test_aktor_pada_body_diabaikan(client_as, svc, sumber):
    c = _tim(client_as, "tim-sungguhan")
    k, v = _draf(svc, sumber)
    r = _tinjau(c, k.id, "TERIMA", v.id, actor_key="palsu", actor_role="admin")
    assert r.status_code == 201
    assert r.json()["actor_key"] == "tim-sungguhan"
    assert r.json()["actor_role"] == "tim-kajian"


def test_otorisasi(client_as, anon_client, svc, sumber):
    k, v = _draf(svc, sumber)
    kasus_url = f"{KASUS}/{k.id}/tinjauan"
    body = {"aksi": "TERIMA", "narasi_versi_id": v.id}
    assert anon_client.get(ANTREAN).status_code == 401
    assert anon_client.get(f"{ANTREAN}/{k.id}").status_code == 401
    assert anon_client.post(kasus_url, json=body).status_code == 401
    for grup in (["admin"], ["sekolah-pengisi"]):
        c = client_as("bukan-tim", groups=grup)
        assert c.get(ANTREAN).status_code == 403
        assert c.get(f"{ANTREAN}/{k.id}").status_code == 403
        assert c.post(kasus_url, json=body).status_code == 403
    assert svc.get_kasus(k.id).status == StatusNarasi.AI_DRAFT


def test_openapi_rute_baru(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths[ANTREAN]) == {"get"}
    assert set(paths[f"{ANTREAN}/{{narasi_id}}"]) == {"get"}
    assert set(paths[f"{KASUS}/{{narasi_id}}/tinjauan"]) == {"post"}


# --- backlog #132: paparan dinamis untuk F2 ---------------------------------------------

SESI_TI = "/api/v1/task-inventory/sesi"


def _responden_ti(client, app, jabatan_id, jumlah):
    """`jumlah` responden TI baru dalam satu sesi (admin), saklar pra-bank hidup."""
    from anjab_abk_backend.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, feature_prebank_freeze=True
    )
    r = client.post(SESI_TI, json={"jabatan_id": jabatan_id, "cabang": "Bandung"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post(f"{SESI_TI}/{sid}/mulai-tahap1").status_code == 200
    ids = []
    for n in range(jumlah):
        r = client.post(f"{SESI_TI}/{sid}/responden", json={"nama": f"Responden {n}"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


def _f2(svc, sumber, ref):
    """Kasus F2_ACTUAL berstatus AI_DRAFT dengan `assignment_ref` = ref."""
    return _draf(svc, sumber, narrative_kind="F2_ACTUAL", assignment_ref=ref)


def _paparan_item(c, narasi_id):
    items = c.get(ANTREAN, params={"limit": 200}).json()["items"]
    return next(x for x in items if x["narasi_id"] == narasi_id)["paparan"]


def test_paparan_f2_exposed_belum_terpapar_dan_locked(
    client, app, client_as, svc, sumber, jabatan_id_tk
):
    r_exposed, r_belum, r_locked = _responden_ti(client, app, jabatan_id_tk, 3)
    u = f"{SESI_TI}/responden"
    assert client.post(f"{u}/{r_exposed}/paparan", json={"jenis": "BANK_TUGAS"}).status_code == 201
    client.put(f"{u}/{r_locked}/cerita-prabank", json={"teks": "cerita saya"})
    assert client.post(f"{u}/{r_locked}/cerita-prabank/bekukan").status_code == 200
    assert client.post(f"{u}/{r_locked}/paparan", json={"jenis": "BANK_TUGAS"}).status_code == 201
    kasus = {
        "EXPOSED": _f2(svc, sumber, r_exposed)[0],
        "BELUM_TERPAPAR": _f2(svc, sumber, r_belum)[0],
        "LOCKED_PRE_EXPOSURE": _f2(svc, sumber, r_locked)[0],
    }
    c = _tim(client_as)
    for nilai, k in kasus.items():
        assert _paparan_item(c, k.id) == nilai
        assert c.get(f"{ANTREAN}/{k.id}").json()["paparan"] == nilai


def test_paparan_f2_tanpa_pasangan_dan_f1_tidak_berlaku(client_as, svc, sumber):
    acak = _f2(svc, sumber, str(uuid.uuid4()))[0]
    tanpa_ref = _draf(svc, sumber, narrative_kind="F2_ACTUAL")[0]
    f1 = _draf(svc, sumber, assignment_ref=str(uuid.uuid4()))[0]
    c = _tim(client_as)
    assert _paparan_item(c, acak.id) == "TIDAK_DIKETAHUI"
    assert _paparan_item(c, tanpa_ref.id) == "TIDAK_DIKETAHUI"
    assert _paparan_item(c, f1.id) == "TIDAK_BERLAKU"
    assert c.get(f"{ANTREAN}/{acak.id}").json()["paparan"] == "TIDAK_DIKETAHUI"
    assert c.get(f"{ANTREAN}/{f1.id}").json()["paparan"] == "TIDAK_BERLAKU"


def test_paparan_daftar_satu_kueri_batch(client_as, svc, sumber, db_session):
    """Jumlah kueri ke `ti_responden` tetap 1 walau halaman memuat banyak kasus F2."""
    from sqlalchemy import event

    for _ in range(5):
        _f2(svc, sumber, str(uuid.uuid4()))
    c = _tim(client_as)
    kueri: list[str] = []

    def _catat(conn, cursor, statement, *a):
        kueri.append(statement)

    mesin = db_session.get_bind()
    event.listen(mesin, "before_cursor_execute", _catat)
    try:
        assert c.get(ANTREAN, params={"limit": 200}).status_code == 200
    finally:
        event.remove(mesin, "before_cursor_execute", _catat)
    assert sum("FROM ti_responden" in q for q in kueri) == 1
