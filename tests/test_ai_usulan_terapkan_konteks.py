"""Tes aksi Terapkan kandidat P11 (`POST /api/v1/ai/usulan/{id}/terapkan-konteks`, backlog #128).

Data sintetis; tidak ada panggilan model. Baris `ai_run`, `ai_usulan`, dan `ai_usulan_putusan`
dibuat langsung. Test DB sudah berisi seed K-01...K-14, jadi kode baru memakai K-15 ke atas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    RedesainKonteksModel,
    RedesainRiwayatModel,
)

URL = "/api/v1/ai/usulan"
KONTEKS = "/api/v1/redesain/konteks"
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


def _kandidat(n: int) -> dict[str, Any]:
    return {
        "tema": f"Tema kandidat {n}",
        "ruang_dugaan": f"Ruang dugaan kandidat {n}",
        "sumber_draft": f"Sumber draf kandidat {n}",
        "batas_pemeriksaan": f"Batas pemeriksaan kandidat {n}",
        "gelombang_saran": "G2",
        "mirip_kode": None,
        "source_ids": ["konteks:K-01"],
    }


def _usulan(
    db: Session,
    *,
    fungsi: str = "P11",
    sasaran_jenis: str = "REDESAIN_KONTEKS",
    isi: dict[str, Any] | None | str = "default",
    putusan: list[str] | None = None,
) -> AiUsulanModel:
    """Buat satu usulan terserap beserta deret putusan (urut waktu) langsung di DB."""
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id,
            fungsi=fungsi,
            prompt_version="v1",
            prompt_hash="a" * 64,
            model_diminta="model-uji",
            protocol_id="uji",
            input_snapshot_id="b" * 64,
            sumber=[],
            masukan={},
            keluaran={},
            status_qa="LOLOS",
            kode_qa=[],
        )
    )
    db.flush()
    if isi == "default":
        isi = {"konteks_candidates": [_kandidat(0), _kandidat(1)], "reviewer_questions": []}
    rec = AiUsulanModel(
        id=str(uuid.uuid4()),
        fungsi=fungsi,
        sasaran_jenis=sasaran_jenis,
        sasaran_id="KATALOG",
        job_id=str(uuid.uuid4()),
        ai_run_id=run_id,
        sumber_ids=["konteks:K-01"],
        diminta_oleh="tim-1",
        created_at=_DASAR,
        diserap_at=_DASAR,
        hasil_serap="USULAN_DIBUAT",
        isi=isi,
        amplop={"source_refs": ["konteks:K-01"]},
        output_hash="c" * 64,
    )
    db.add(rec)
    db.flush()
    for i, p in enumerate(putusan or []):
        db.add(
            AiUsulanPutusanModel(
                id=str(uuid.uuid4()),
                usulan_id=rec.id,
                putusan=p,
                tingkat_koreksi=None if p == "APPROVE" else "MINOR",
                catatan="Catatan reviewer." if p == "REJECT" else None,
                teks_koreksi="Koreksi bebas." if p == "REVISE" else None,
                actor_key="reviewer-1",
                created_at=_DASAR + timedelta(minutes=i + 1),
            )
        )
    db.flush()
    return rec


@pytest.fixture
def tim(client_as, partisipan_factory):
    partisipan_factory("tk-terapkan")
    return client_as("tk-terapkan", groups=["tim-kajian"])


def _isian_revisi() -> dict[str, str]:
    return {
        "tema": "Tema hasil revisi",
        "ruang_dugaan": "Ruang revisi",
        "sumber_draft": "Sumber revisi",
        "batas_pemeriksaan": "Batas revisi",
    }


# --- positif -------------------------------------------------------------------------------


def test_approve_membuat_konteks_dari_kandidat_dan_riwayat(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 1, "kode": "K-15", "gelombang": "G3", "tema": "Tema ditimpa"},
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["kode"] == "K-15"
    assert d["gelombang"] == "G3"
    assert d["tema"] == "Tema ditimpa"
    assert d["ruang_dugaan"] == "Ruang dugaan kandidat 1"
    assert d["sumber_draft"] == "Sumber draf kandidat 1"
    assert d["batas_pemeriksaan"] == "Batas pemeriksaan kandidat 1"
    assert d["aktif"] is True
    assert d["ai_usulan_id"] == rec.id
    assert d["ai_kandidat_indeks"] == 1
    riwayat = db_session.scalars(
        select(RedesainRiwayatModel).where(RedesainRiwayatModel.entitas_id == d["id"])
    ).all()
    assert [(x.entitas, x.aksi) for x in riwayat] == [("konteks", "create")]
    # GET dan search memuat penanda asal; search per ai_usulan_id menandai kandidat terterapkan.
    assert tim.get(f"{KONTEKS}/{d['id']}").json()["ai_usulan_id"] == rec.id
    cari = tim.post(f"{KONTEKS}/search", json={"domain": [["ai_usulan_id", "=", rec.id]]})
    assert cari.status_code == 200
    assert [(i["kode"], i["ai_kandidat_indeks"]) for i in cari.json()["items"]] == [("K-15", 1)]


def test_revise_dengan_keempat_isian_memakai_isian_kiriman(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE", "REVISE"])
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-16", "gelombang": "G1", **_isian_revisi()},
    )
    assert r.status_code == 201, r.text
    d = r.json()
    for k, v in _isian_revisi().items():
        assert d[k] == v


def test_kandidat_lain_tetap_bisa_diterapkan(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    for indeks, kode in ((0, "K-17"), (1, "K-18")):
        r = tim.post(
            f"{URL}/{rec.id}/terapkan-konteks",
            json={"indeks_kandidat": indeks, "kode": kode, "gelombang": "G2"},
        )
        assert r.status_code == 201, r.text


def test_konteks_manual_tanpa_penanda_asal(tim):
    r = tim.post(
        KONTEKS,
        json={
            "kode": "K-19",
            "tema": "t",
            "gelombang": "G1",
            "ruang_dugaan": "r",
            "sumber_draft": "s",
            "batas_pemeriksaan": "b",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["ai_usulan_id"] is None
    assert r.json()["ai_kandidat_indeks"] is None


# --- negatif -------------------------------------------------------------------------------


@pytest.mark.parametrize("putusan", [[], ["APPROVE", "REJECT"]])
def test_tanpa_putusan_atau_reject_409_belum_diterima(tim, db_session, putusan):
    rec = _usulan(db_session, putusan=putusan)
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-20", "gelombang": "G1"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "USULAN_BELUM_DITERIMA"


def test_revise_tanpa_isian_422(tim, db_session):
    rec = _usulan(db_session, putusan=["REVISE"])
    isian = _isian_revisi()
    isian.pop("batas_pemeriksaan")
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-21", "gelombang": "G1", **isian},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "ISIAN_REVISI_WAJIB"


@pytest.mark.parametrize(
    ("fungsi", "sasaran"), [("P09", "REDESAIN_KONTEKS"), ("P11", "REDESAIN_MASALAH")]
)
def test_usulan_bukan_p11_422(tim, db_session, fungsi, sasaran):
    rec = _usulan(db_session, fungsi=fungsi, sasaran_jenis=sasaran, putusan=["APPROVE"])
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-22", "gelombang": "G1"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "USULAN_BUKAN_P11"


def test_indeks_di_luar_rentang_dan_isi_null_422(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 9, "kode": "K-23", "gelombang": "G1"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "KANDIDAT_TAK_ADA"
    kosong = _usulan(db_session, isi=None, putusan=["APPROVE"])
    r = tim.post(
        f"{URL}/{kosong.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-23", "gelombang": "G1"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "KANDIDAT_TAK_ADA"


def test_usulan_tak_ada_404(tim):
    r = tim.post(
        f"{URL}/{uuid.uuid4()}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-24", "gelombang": "G1"},
    )
    assert r.status_code == 404, r.text


def test_ulang_kandidat_sama_409_sudah_diterapkan(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    pertama = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-25", "gelombang": "G1"},
        headers={"Idempotency-Key": "kunci-satu"},
    )
    assert pertama.status_code == 201, pertama.text
    kedua = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-26", "gelombang": "G1"},
        headers={"Idempotency-Key": "kunci-dua"},
    )
    assert kedua.status_code == 409, kedua.text
    body = kedua.json()
    assert body["error"] == "KANDIDAT_SUDAH_DITERAPKAN"
    assert body["details"][0]["code"] == "KANDIDAT_SUDAH_DITERAPKAN"
    assert body["details"][0]["msg"] == pertama.json()["id"]


def test_kode_yang_ada_409_conflict(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-01", "gelombang": "G1"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "conflict"


def test_isian_kandidat_tidak_sah_422(tim, db_session):
    kandidat = _kandidat(0) | {"tema": "x" * 201}
    rec = _usulan(
        db_session,
        isi={"konteks_candidates": [kandidat], "reviewer_questions": []},
        putusan=["APPROVE"],
    )
    r = tim.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-27", "gelombang": "G1"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "validation_error"


def test_body_field_asing_dan_indeks_negatif_422(tim, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    for badan in (
        {"indeks_kandidat": 0, "kode": "K-28", "gelombang": "G1", "aktif": False},
        {"indeks_kandidat": -1, "kode": "K-28", "gelombang": "G1"},
        {"indeks_kandidat": 0, "kode": "X-28", "gelombang": "G1"},
    ):
        r = tim.post(f"{URL}/{rec.id}/terapkan-konteks", json=badan)
        assert r.status_code == 422, r.text


def test_non_tim_kajian_403(client_as, partisipan_factory, db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    partisipan_factory("bukan-tim")
    c = client_as("bukan-tim", groups=[])
    r = c.post(
        f"{URL}/{rec.id}/terapkan-konteks",
        json={"indeks_kandidat": 0, "kode": "K-29", "gelombang": "G1"},
    )
    assert r.status_code == 403, r.text


def test_putusan_tidak_menulis_konteks(tim, db_session):
    rec = _usulan(db_session)
    sebelum = db_session.scalar(select(func.count()).select_from(RedesainKonteksModel))
    r = tim.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"})
    assert r.status_code == 201, r.text
    assert db_session.scalar(select(func.count()).select_from(RedesainKonteksModel)) == sebelum


# --- constraint basis data ------------------------------------------------------------------


def test_check_menolak_hanya_satu_kolom_asal(db_session):
    rec = _usulan(db_session, putusan=["APPROVE"])
    with pytest.raises(IntegrityError) as info, db_session.begin_nested():
        db_session.execute(
            text(
                "INSERT INTO redesain_konteks (id, kode, tema, gelombang, ruang_dugaan, "
                "sumber_draft, batas_pemeriksaan, aktif, ai_usulan_id, created_at, updated_at) "
                "VALUES (:id, 'K-30', 't', 'G1', 'r', 's', 'b', true, :u, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "u": rec.id},
        )
    assert "ck_redesain_konteks_asal_usulan_ai" in str(info.value)
