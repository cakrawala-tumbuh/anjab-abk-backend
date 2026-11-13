"""Regresi #142: galat domain pada POST ber-`Idempotency-Key` membalas 409, bukan 500.

Akarnya `IntegrityError` dari `flush()` tanpa SAVEPOINT yang membatalkan transaksi
request; `run_idempotent` lalu memanggil `release()` pada sesi yang sudah gagal sehingga
`PendingRollbackError` menggantikan `ConflictError`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from anjab_abk_backend.models import RedesainKonteksModel, RedesainMasalahModel
from anjab_abk_backend.redesain.seed import seed_versi_metode
from anjab_abk_backend.redesain.services.masalah_sql import SqlMasalahService
from anjab_abk_backend.services.idempotency_sql import SqlIdempotencyStore

URL = "/api/v1/redesain/versi-metode"
PESAN = "Catatan untuk pasangan versi dan bagian itu sudah ada."


def _tim(client_as, partisipan_factory):
    subject = f"idm-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _payload(**kw) -> dict:
    base = {
        "versi": "v1.4",
        "tanggal": "2026-12-01",
        "bagian": "Ambang triase",
        "apa_diperbarui": "Ambang P1-P3 disesuaikan.",
        "alasan_risiko": "Menyesuaikan hasil uji.",
        "status_hasil_uji": "Belum diuji.",
        "pemeriksa_pemutus": "Pimpinan metode",
    }
    return {**base, **kw}


def test_duplikat_versi_metode_dengan_key_409_dan_ulangan_409(
    client_as, partisipan_factory, db_session
):
    seed_versi_metode(db_session)
    c = _tim(client_as, partisipan_factory)
    h = {"Idempotency-Key": "k1"}
    for _ in range(2):
        r = c.post(URL, json=_payload(versi="v1.3", bagian="Register"), headers=h)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "conflict"
        assert r.json()["message"] == PESAN


def test_versi_metode_baru_dengan_key_201_ulang_200_id_sama(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory)
    h = {"Idempotency-Key": "k2"}
    pertama = c.post(URL, json=_payload(), headers=h)
    kedua = c.post(URL, json=_payload(), headers=h)
    assert pertama.status_code == 201, pertama.text
    assert kedua.status_code == 200, kedua.text
    assert kedua.json()["id"] == pertama.json()["id"]


def test_duplikat_masalah_dengan_key_409_bukan_500(
    client_as, partisipan_factory, db_session, monkeypatch
):
    """Balapan dua create: baris kembar masuk lewat `_flush` (tanpa SAVEPOINT) -> 409."""
    konteks_id = db_session.scalars(select(RedesainKonteksModel.id)).first()
    kembar = db_session.scalars(select(RedesainMasalahModel.kode)).first()
    asli = SqlMasalahService._ganti_uraian

    def _ganti_dengan_baris_kembar(self, masalah_id, ut_ids):
        rec = RedesainMasalahModel(
            id=str(uuid.uuid4()),
            kode=kembar,
            konteks_id=konteks_id,
            periode_acuan="TA 2026/27",
            rumusan_hipotesis="kembar",
            sumber_awal_keterbatasan="kembar",
            status_awal="Hipotesis",
            gelombang="G3",
        )
        self._s.add(rec)
        self._flush()
        return asli(self, masalah_id, ut_ids)

    monkeypatch.setattr(SqlMasalahService, "_ganti_uraian", _ganti_dengan_baris_kembar)
    c = _tim(client_as, partisipan_factory)
    payload = {
        "konteks_id": konteks_id,
        "periode_acuan": "TA 2026/27",
        "rumusan_hipotesis": "Dugaan uji",
        "sumber_awal_keterbatasan": "Sumber uji",
        "gelombang": "G3",
    }
    r = c.post("/api/v1/redesain/masalah", json=payload, headers={"Idempotency-Key": "k3"})
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "conflict"


def test_release_pada_sesi_sehat_menghapus_reservasi(db_session):
    store = SqlIdempotencyStore(db_session)
    assert store.reserve("uji-release")
    assert not store.reserve("uji-release")
    store.release("uji-release")
    assert store.reserve("uji-release")


def test_release_pada_sesi_gagal_tidak_menyentuh_db(db_session):
    from sqlalchemy.exc import IntegrityError

    store = SqlIdempotencyStore(db_session)
    assert store.reserve("uji-gagal")
    m = RedesainMasalahModel
    kode = db_session.scalars(select(m.kode)).first()
    konteks_id = db_session.scalars(select(RedesainKonteksModel.id)).first()
    db_session.add(
        m(
            id=str(uuid.uuid4()),
            kode=kode,
            konteks_id=konteks_id,
            periode_acuan="x",
            rumusan_hipotesis="x",
            sumber_awal_keterbatasan="x",
            status_awal="Hipotesis",
            gelombang="G3",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    assert not db_session.is_active
    store.release("uji-gagal")  # tidak boleh melempar PendingRollbackError
