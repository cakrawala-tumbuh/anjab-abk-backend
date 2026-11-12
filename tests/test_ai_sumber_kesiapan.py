"""Tes perakit sumber `kesiapan:` dan keputusan perubahan pada sumber `otorisasi:` (P06/P07).

Data sintetis di PostgreSQL uji; tanpa klien model dan tanpa jaringan.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai.otorisasi_redesain import (
    bangun_authorization_state,
    sumber_otorisasi,
)
from anjab_abk_backend.ai.sumber_redesain import rakit_sumber_kesiapan
from anjab_abk_backend.models import (
    JabatanModel,
    RedesainAlternatifModel,
    RedesainAlternatifPenerimaModel,
    RedesainKeputusanPerubahanModel,
    RedesainKesiapanModel,
    RedesainMasalahModel,
)

P = "2026/27"


def _hex() -> str:
    return uuid.uuid4().hex[:8]


def _masalah(db: Session) -> str:
    return db.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == "M-K01-01")
    ).one()


def _alternatif(db: Session, masalah_id: str) -> RedesainAlternatifModel:
    alt = RedesainAlternatifModel(
        id=str(uuid.uuid4()), kode=f"U-{_hex()}", masalah_id=masalah_id, opsi="Sederhanakan",
        alur_kini_vs_usulan="Tiga format menjadi satu",
    )  # fmt: skip
    db.add(alt)
    db.flush()
    return alt


def _penerima(db: Session, alt: RedesainAlternatifModel, material: bool = True) -> str:
    jid = f"jbt_{_hex()}"
    db.add(JabatanModel(id=jid, kode=jid.upper(), nama=f"Jabatan {jid}", jenis="struktural"))
    db.flush()
    pid = str(uuid.uuid4())
    db.add(
        RedesainAlternatifPenerimaModel(
            id=pid, alternatif_id=alt.id, penerima_jabatan_id=jid, material=material
        )
    )
    db.flush()
    return pid


def _nilai(db: Session, penerima_id: str, status: str, periode: str = P, **ubah: Any) -> None:
    isi: dict[str, Any] = {
        "delta_asal_jam": Decimal("-2.50"), "delta_asal_estimasi": "ESTIMATED",
        "delta_penerima_jam": Decimal("1.00"), "delta_penerima_estimasi": "ESTIMATED",
        "delta_organisasi_jam": Decimal("-1.50"), "delta_organisasi_estimasi": "ESTIMATED",
    }  # fmt: skip
    isi.update(ubah)
    db.add(
        RedesainKesiapanModel(
            id=str(uuid.uuid4()), penerima_id=penerima_id, periode=periode, status=status,
            dinilai_oleh="O-9301", **isi,
        )
    )  # fmt: skip
    db.flush()


def test_dua_penerima_dua_sumber_status_benar_dan_status_opsi_hold(db_session):
    mid = _masalah(db_session)
    alt = _alternatif(db_session, mid)
    p1, p2 = _penerima(db_session, alt), _penerima(db_session, alt)
    _nilai(db_session, p1, "READY")
    sumber = rakit_sumber_kesiapan(db_session, mid, P)
    assert len(sumber) == 2
    assert {s.source_id for s in sumber} == {f"kesiapan:{alt.id}:{p1}", f"kesiapan:{alt.id}:{p2}"}
    assert {s.jenis for s in sumber} == {"REDESAIN"}
    per = {s.source_id: s.teks for s in sumber}
    t1, t2 = per[f"kesiapan:{alt.id}:{p1}"], per[f"kesiapan:{alt.id}:{p2}"]
    assert "status: READY" in t1 and "status: BELUM_DINILAI" in t2
    assert f"kode_alternatif: {alt.kode}" in t1 and f"periode: {P}" in t1
    assert "status_opsi: HOLD" in t1 and "status_opsi: HOLD" in t2
    assert "delta_asal" not in t2


def test_periode_lain_tidak_ikut_dan_penilaian_terakhir_menggantikan(db_session):
    mid = _masalah(db_session)
    alt = _alternatif(db_session, mid)
    p1 = _penerima(db_session, alt)
    _nilai(db_session, p1, "HOLD", alasan_hold="Belum sanggup")
    _nilai(db_session, p1, "CONDITIONAL", syarat="Pelatihan dua minggu")
    _nilai(db_session, p1, "HOLD", periode="2027/28", alasan_hold="periode-lain-q7")
    [s] = rakit_sumber_kesiapan(db_session, mid, P)
    assert "status: CONDITIONAL" in s.teks and "syarat: Pelatihan dua minggu" in s.teks
    assert "Belum sanggup" not in s.teks and "periode-lain-q7" not in s.teks
    assert "status_opsi: CONDITIONAL" in s.teks
    [s2] = rakit_sumber_kesiapan(db_session, mid, "2027/28")
    assert "status: HOLD" in s2.teks and "alasan_hold: periode-lain-q7" in s2.teks


def test_not_estimable_ditulis_apa_adanya_bukan_nol(db_session):
    mid = _masalah(db_session)
    alt = _alternatif(db_session, mid)
    p1 = _penerima(db_session, alt)
    _nilai(
        db_session, p1, "READY",
        delta_penerima_jam=None, delta_penerima_estimasi="NOT_ESTIMABLE",
    )  # fmt: skip
    [s] = rakit_sumber_kesiapan(db_session, mid, P)
    assert "delta_penerima: NOT_ESTIMABLE" in s.teks
    assert "delta_penerima: 0" not in s.teks
    assert "delta_asal: -2.50 jam kerja efektif per periode (ESTIMATED)" in s.teks


def test_masalah_tanpa_penerima_tanpa_sumber_kesiapan(db_session):
    mid = _masalah(db_session)
    _alternatif(db_session, mid)
    assert rakit_sumber_kesiapan(db_session, mid, P) == []


def test_penerima_non_material_belum_dinilai_tidak_menahan_status_opsi(db_session):
    mid = _masalah(db_session)
    alt = _alternatif(db_session, mid)
    p1, p2 = _penerima(db_session, alt), _penerima(db_session, alt, material=False)
    _nilai(db_session, p1, "READY")
    teks = {s.source_id: s.teks for s in rakit_sumber_kesiapan(db_session, mid, P)}
    assert "status_opsi: READY" in teks[f"kesiapan:{alt.id}:{p2}"]
    assert "material: tidak" in teks[f"kesiapan:{alt.id}:{p2}"]


def _putus(db: Session, alt_id: str, keputusan: str, status_opsi: str, periode: str = P) -> None:
    db.add(
        RedesainKeputusanPerubahanModel(
            id=str(uuid.uuid4()), alternatif_id=alt_id, periode=periode, keputusan=keputusan,
            alasan="Alasan uji",
            stop_rule="Berhenti bila gagal" if keputusan == "CONDITIONAL" else None,
            status_opsi_saat_putus=status_opsi, pemutus_kode_orang="O-9301",
        )
    )  # fmt: skip
    db.flush()


def test_otorisasi_memuat_keputusan_perubahan_terakhir_atau_belum_diputus(db_session):
    mid = _masalah(db_session)
    a1, a2 = _alternatif(db_session, mid), _alternatif(db_session, mid)
    _putus(db_session, a1.id, "HOLD", "HOLD")
    _putus(db_session, a1.id, "CONDITIONAL", "CONDITIONAL")
    _putus(db_session, a1.id, "REJECT", "HOLD", periode="2027/28")
    state = bangun_authorization_state(db_session, mid, P)
    per = {k["alternatif_id"]: k for k in state["keputusan_perubahan"]}
    assert per[a1.id]["keputusan"] == "CONDITIONAL"
    assert per[a1.id]["status_opsi_saat_putus"] == "CONDITIONAL"
    assert per[a2.id]["keputusan"] == "BELUM_DIPUTUS"
    assert per[a2.id]["status_opsi_saat_putus"] is None
    assert state["change_ditandatangani"] is False
    teks = sumber_otorisasi(mid, state).teks
    assert "BELUM_DIPUTUS" in teks and "CONDITIONAL" in teks and "REJECT" not in teks


def test_otorisasi_tanpa_periode_tidak_memuat_keputusan_perubahan(db_session):
    mid = _masalah(db_session)
    _alternatif(db_session, mid)
    assert "keputusan_perubahan" not in bangun_authorization_state(db_session, mid)
