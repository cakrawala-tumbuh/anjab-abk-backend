"""Tes ekspor DOCX ringkasan yayasan dan lembar konfirmasi pra-isi (#63)."""

from __future__ import annotations

import uuid
from io import BytesIO

from docx import Document
from sqlalchemy import select

from anjab_abk_backend.models import RedesainKodeOrangModel, RedesainMasalahModel
from anjab_abk_backend.redesain.ekspor_docx import DOCX_MEDIA_TYPE
from anjab_abk_backend.redesain.schemas.penilaian import hari_ini_wib

URL = "/api/v1/redesain/ekspor"
PNL = "/api/v1/redesain/penilaian"
SIAP = "Siap untuk telaah yayasan"


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _mid(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _nilai(mid: str, **kw):
    base = {
        "masalah_id": mid,
        "status_bukti": "Diperkuat untuk klaim",
        "gap_material": "Tidak",
        "indikasi_kritis": "Tidak terlihat",
        "k1": "Sedang",
        "k2": "Rendah",
        "k3": "Tinggi",
        "k4": "Tinggi",
    }
    base.update(kw)
    return base


def _teks(resp) -> str:
    doc = Document(BytesIO(resp.content))
    bagian = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            bagian.extend(c.text for c in row.cells)
    return "\n".join(bagian)


def test_ringkasan_satu_masalah_diputuskan(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "eks-1")
    mid = _mid(db_session)
    db_session.add(RedesainKodeOrangModel(id=str(uuid.uuid4()), kode="O-9401"))
    db_session.flush()
    pid = c.post(PNL, json=_nilai(mid, indikasi_kritis="Ada indikasi")).json()["id"]
    put = c.post(
        f"{PNL}/{pid}/putuskan",
        json={
            "prioritas_final": "P1 - Utama",
            "alasan_final": "Dampak besar.",
            "pemutus_kode_orang": "O-9401",
            "pemutus_jabatan": "Ketua Tim Kajian",
            "tanggal_keputusan": hari_ini_wib().isoformat(),
        },
    )
    assert put.status_code == 200, put.text
    r = c.get(f"{URL}/ringkasan-yayasan/{mid}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(DOCX_MEDIA_TYPE)
    assert r.headers["content-disposition"] == 'attachment; filename="M-K01-01.docx"'
    t = _teks(r)
    assert "M-K01-01" in t
    assert "RINGKASAN TELAAH PRIORITAS — YAYASAN" in t
    assert "■ Ada indikasi" in t
    assert "□ Tidak terlihat" in t
    assert "P1 - Utama" in t
    assert "O-9401 — Ketua Tim Kajian" in t


def test_ringkasan_tidak_memuat_nama_atau_email_partisipan(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "eks-2")
    mid = _mid(db_session)
    c.post(PNL, json=_nilai(mid))
    t = _teks(c.get(f"{URL}/ringkasan-yayasan/{mid}"))
    from anjab_abk_backend.models import PartisipanModel

    for nama, email in db_session.execute(
        select(PartisipanModel.nama, PartisipanModel.email)
    ).all():
        if nama:
            assert nama not in t
        if email:
            assert email not in t


def test_batch_dua_agenda_urut_kode_dan_tanpa_hasil_404(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "eks-3")
    assert c.get(f"{URL}/ringkasan-yayasan").status_code == 404
    a = c.post(PNL, json=_nilai(_mid(db_session, "M-K02-01"))).json()["id"]
    b = c.post(PNL, json=_nilai(_mid(db_session, "M-K01-01"))).json()["id"]
    for pid in (a, b):
        s = c.post(f"{PNL}/{pid}/status", json={"status_penilaian": SIAP})
        assert s.status_code == 200, s.text
    r = c.get(f"{URL}/ringkasan-yayasan")
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="agenda-yayasan.docx"'
    t = _teks(r)
    assert t.index("M-K01-01") < t.index("M-K02-01")


def test_lembar_konfirmasi_bagian_a_dan_pilihan_indikasi(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "eks-4")
    mid = _mid(db_session)
    rumusan = c.get(f"/api/v1/redesain/masalah/{mid}").json()["rumusan_hipotesis"]
    r = c.get(f"{URL}/lembar-konfirmasi/{mid}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(DOCX_MEDIA_TYPE)
    t = _teks(r)
    assert "M-K01-01" in t
    assert "K-01" in t
    assert rumusan in t
    for p in ("Ada indikasi", "Tidak terlihat", "Belum tahu"):
        assert f"□ {p}" in t


def test_negatif_404_403_401(client_as, partisipan_factory, db_session, anon_client):
    c = _tim(client_as, partisipan_factory, "eks-5")
    acak = uuid.uuid4()
    assert c.get(f"{URL}/ringkasan-yayasan/{acak}").status_code == 404
    assert c.get(f"{URL}/lembar-konfirmasi/{acak}").status_code == 404
    mid = _mid(db_session)
    partisipan_factory("eks-6")
    sp = client_as("eks-6", groups=["sekolah-pengisi"])
    assert sp.get(f"{URL}/ringkasan-yayasan/{mid}").status_code == 403
    assert sp.get(f"{URL}/ringkasan-yayasan").status_code == 403
    assert sp.get(f"{URL}/lembar-konfirmasi/{mid}").status_code == 403
    assert anon_client.get(f"{URL}/ringkasan-yayasan/{mid}").status_code == 401
