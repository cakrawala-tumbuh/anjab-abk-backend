"""Tes keputusan perubahan (ChangeDecision) alternatif redesain (backlog `#134`)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    JabatanModel,
    RedesainKeputusanPerubahanModel,
    RedesainKodeOrangModel,
    RedesainMasalahModel,
)
from anjab_abk_backend.redesain.schemas.penilaian import hari_ini_wib

URL = "/api/v1/redesain/alternatif"
P = "2026/27"


def _hidup(app, aktif: bool = True) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, feature_change_authorization=aktif
    )


def _jabatan(db_session) -> str:
    jid = f"jbt_{uuid.uuid4().hex[:8]}"
    db_session.add(
        JabatanModel(id=jid, kode=jid.upper(), nama=f"Jabatan {jid}", jenis="struktural")
    )
    db_session.flush()
    return jid


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _alternatif(c, db_session) -> str:
    mid = db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == "M-K01-01")
    ).one()
    r = c.post(
        URL,
        json={
            "masalah_id": mid,
            "opsi": "Sederhanakan",
            "alur_kini_vs_usulan": "Kini A; usulan B.",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _penerima(c, aid: str, db_session) -> str:
    r = c.post(f"{URL}/{aid}/penerima", json={"penerima_jabatan_id": _jabatan(db_session)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _nilai(c, aid: str, pid: str, status: str = "READY", periode: str = P) -> None:
    body = {
        "penerima_id": pid,
        "periode": periode,
        "status": status,
        "delta_asal_jam": "1.00",
        "delta_penerima_jam": "1.00",
        "delta_organisasi_jam": "0.00",
    }
    if status == "CONDITIONAL":
        body["syarat"] = "Pelatihan dulu."
    if status == "HOLD":
        body["alasan_hold"] = "Belum siap."
    assert c.post(f"{URL}/{aid}/kesiapan", json=body).status_code == 201


def _putus(c, aid: str, keputusan: str, **kw):
    body = {"periode": P, "keputusan": keputusan, "alasan": "Alasan yang cukup."}
    body.update(kw)
    return c.post(f"{URL}/{aid}/keputusan-perubahan", json=body)


def _siap(c, db_session, status: str | None):
    """Alternatif dengan satu penerima material berstatus `status` (None = belum dinilai)."""
    aid = _alternatif(c, db_session)
    pid = _penerima(c, aid, db_session)
    if status:
        _nilai(c, aid, pid, status)
    return aid


def test_approve_saat_ready_201_dan_riwayat(client_as, partisipan_factory, db_session, app):
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-1")
    aid = _siap(c, db_session, "READY")
    r = _putus(c, aid, "APPROVE")
    assert r.status_code == 201, r.text
    assert r.json()["status_opsi_saat_putus"] == "READY"
    assert r.json()["keputusan"] == "APPROVE"
    h = c.get(f"{URL}/{aid}/keputusan-perubahan", params={"periode": P})
    assert h.status_code == 200 and [x["id"] for x in h.json()] == [r.json()["id"]]


def test_conditional_dengan_stop_rule_dan_hold_reject_pada_opsi_hold(
    client_as, partisipan_factory, db_session, app
):
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-2")
    aid = _siap(c, db_session, "CONDITIONAL")
    r = _putus(c, aid, "CONDITIONAL", stop_rule="Hentikan bila beban > 4 jam.")
    assert r.status_code == 201, r.text
    assert r.json()["status_opsi_saat_putus"] == "CONDITIONAL"
    aid2 = _siap(c, db_session, "HOLD")
    assert _putus(c, aid2, "HOLD").status_code == 201
    r2 = _putus(c, aid2, "REJECT")
    assert r2.status_code == 201 and r2.json()["status_opsi_saat_putus"] == "HOLD"
    riwayat = c.get(f"{URL}/{aid2}/keputusan-perubahan").json()
    assert [x["keputusan"] for x in riwayat] == ["HOLD", "REJECT"]  # urut naik


def test_saklar_mati_post_409_get_tetap_200(client_as, partisipan_factory, db_session, app):
    _hidup(app, False)
    c = _tim(client_as, partisipan_factory, "kp-3")
    aid = _siap(c, db_session, "READY")
    r = _putus(c, aid, "APPROVE")
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled"
    assert c.get(f"{URL}/{aid}/keputusan-perubahan").status_code == 200


def test_negatif_aturan_status_opsi_dan_validasi(client_as, partisipan_factory, db_session, app):
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-4")
    aid = _siap(c, db_session, "HOLD")
    r = _putus(c, aid, "APPROVE")
    assert r.status_code == 409 and r.json()["error"] == "KESIAPAN_BELUM_READY"
    r = _putus(c, aid, "CONDITIONAL", stop_rule="Berhenti bila X.")
    assert r.status_code == 409 and r.json()["error"] == "KESIAPAN_HOLD"
    # APPROVE saat CONDITIONAL juga ditolak.
    aid2 = _siap(c, db_session, "CONDITIONAL")
    r = _putus(c, aid2, "APPROVE")
    assert r.status_code == 409 and r.json()["error"] == "KESIAPAN_BELUM_READY"
    # Belum dinilai = HOLD.
    aid3 = _siap(c, db_session, None)
    assert _putus(c, aid3, "APPROVE").status_code == 409
    # 422: stop_rule hilang/kosong, alasan pendek, periode salah, keputusan asing.
    aid4 = _siap(c, db_session, "READY")
    assert _putus(c, aid4, "CONDITIONAL").status_code == 422
    assert _putus(c, aid4, "CONDITIONAL", stop_rule="  ").status_code == 422
    assert _putus(c, aid4, "APPROVE", alasan="abc").status_code == 422
    assert _putus(c, aid4, "APPROVE", periode="2026-27").status_code == 422
    assert _putus(c, aid4, "MAYBE").status_code == 422
    assert _putus(c, "tidak-ada", "HOLD").status_code == 404
    n = db_session.scalar(select(func.count()).select_from(RedesainKeputusanPerubahanModel))
    assert n == 0  # semua penolakan tidak menulis baris


def test_non_tim_kajian_403(client_as, partisipan_factory, db_session, app):
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-5")
    aid = _siap(c, db_session, "READY")
    partisipan_factory("kp-5b")
    sp = client_as("kp-5b", groups=["sekolah-pengisi"])
    assert _putus(sp, aid, "APPROVE").status_code == 403
    assert sp.get(f"{URL}/{aid}/keputusan-perubahan").status_code == 403


def test_status_opsi_saat_putus_adalah_salinan_dan_tidak_berubah(
    client_as, partisipan_factory, db_session, app
):
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-6")
    aid = _alternatif(c, db_session)
    pid = _penerima(c, aid, db_session)
    _nilai(c, aid, pid, "READY")
    assert _putus(c, aid, "APPROVE").status_code == 201
    _nilai(c, aid, pid, "HOLD")  # matriks berubah setelahnya
    assert _putus(c, aid, "HOLD").status_code == 201
    h = c.get(f"{URL}/{aid}/keputusan-perubahan").json()
    assert [x["status_opsi_saat_putus"] for x in h] == ["READY", "HOLD"]
    # filter periode lain kosong
    assert c.get(f"{URL}/{aid}/keputusan-perubahan", params={"periode": "2027/28"}).json() == []


def test_putuskan_prioritas_tidak_menambah_keputusan_perubahan(
    client_as, partisipan_factory, db_session, app
):
    """Pemisahan: `POST /redesain/penilaian/{id}/putuskan` tidak menulis tabel ini."""
    _hidup(app)
    c = _tim(client_as, partisipan_factory, "kp-7")
    db_session.add(RedesainKodeOrangModel(id=str(uuid.uuid4()), kode="O-9134"))
    db_session.flush()
    mid = db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == "M-K01-01")
    ).one()
    p = c.post(
        "/api/v1/redesain/penilaian",
        json={
            "masalah_id": mid,
            "status_bukti": "Diperkuat untuk klaim",
            "gap_material": "Tidak",
            "indikasi_kritis": "Tidak terlihat",
            "k1": "Sedang",
            "k2": "Rendah",
            "k3": "Tinggi",
            "k4": "Tinggi",
        },
    ).json()
    r = c.post(
        f"/api/v1/redesain/penilaian/{p['id']}/putuskan",
        json={
            "prioritas_final": "P1 - Utama",
            "alasan_final": "Dampak besar pada guru.",
            "pemutus_kode_orang": "O-9134",
            "pemutus_jabatan": "Ketua Tim Kajian",
            "tanggal_keputusan": hari_ini_wib().isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    n = db_session.scalar(select(func.count()).select_from(RedesainKeputusanPerubahanModel))
    assert n == 0
