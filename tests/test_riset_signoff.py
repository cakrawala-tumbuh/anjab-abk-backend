"""Tes sign-off PI/etik protokol riset: unggah PDF multipart, metadata, unduh, batas body."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from anjab_abk_backend.config import Settings, get_settings

URL = "/api/v1/riset/protokol"
PDF_KECIL = b"%PDF-1.4\n%uji\n" + bytes(range(256)) * 4
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _tim(client_as, subject: str = "tim-pi"):
    return client_as(subject, groups=["tim-kajian"])


def _protokol(c, *, kunci: bool = True) -> str:
    body = {"kode": f"SO-{uuid.uuid4().hex[:8]}", "judul": "Protokol uji", "isi": "Isi."}
    pid = c.post(URL, json=body).json()["id"]
    if kunci:
        assert c.post(f"{URL}/{pid}/kunci").status_code == 200
    return pid


def _kirim(c, pid, *, isi=PDF_KECIL, tipe="application/pdf", tanggal=None, **ubah):
    data = {"pi_nama": "Dr. PI Uji", "tanggal_persetujuan_etik": "2026-01-05"}
    if tanggal is not None:
        data["tanggal_persetujuan_etik"] = tanggal
    data.update(ubah)
    data = {k: v for k, v in data.items() if v is not None}
    return c.post(f"{URL}/{pid}/sign-off", data=data, files={"lampiran": ("etik.pdf", isi, tipe)})


def test_unggah_pdf_2mib_lalu_unduh_byte_identik(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    pdf = b"%PDF-1.7\n" + b"A" * (2 * 1024 * 1024)
    r = _kirim(c, pid, isi=pdf, nomor_persetujuan_etik="KEPK/123")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["lampiran_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert d["lampiran_ukuran"] == len(pdf) and d["lampiran_nama"] == "etik.pdf"
    assert d["pi_nama"] == "Dr. PI Uji" and d["dicatat_oleh"] == "tim-pi"
    assert d["nomor_persetujuan_etik"] == "KEPK/123" and "lampiran_pdf" not in d
    m = c.get(f"{URL}/{pid}/sign-off")
    assert m.status_code == 200 and m.json()["id"] == d["id"]
    u = c.get(f"{URL}/{pid}/sign-off/lampiran")
    assert u.status_code == 200 and u.content == pdf
    assert u.headers["content-type"].startswith("application/pdf")
    assert u.headers["content-disposition"].startswith("attachment")
    assert u.headers["etag"].strip('"') == d["lampiran_sha256"]
    assert c.get(f"{URL}/{pid}").json()["signoff_ada"] is True


def test_signoff_ada_false_sebelum_dicatat_dan_get_404(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    assert c.get(f"{URL}/{pid}").json()["signoff_ada"] is False
    r = c.get(f"{URL}/{pid}/sign-off")
    assert r.status_code == 404 and r.json()["error"] == "SIGNOFF_TAK_ADA"
    assert c.get(f"{URL}/{pid}/sign-off/lampiran").status_code == 404


def test_protokol_draf_409_dan_protokol_tak_ada_404(client_as):
    c = _tim(client_as)
    r = _kirim(c, _protokol(c, kunci=False))
    assert r.status_code == 409 and r.json()["error"] == "PROTOKOL_BELUM_TERKUNCI"
    assert _kirim(c, str(uuid.uuid4())).status_code == 404


def test_signoff_kedua_409(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    assert _kirim(c, pid).status_code == 201
    r = _kirim(c, pid)
    assert r.status_code == 409 and r.json()["error"] == "SIGNOFF_SUDAH_ADA"


def test_bukan_pdf_422_png_berlabel_pdf_dan_label_salah(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    r = _kirim(c, pid, isi=PNG)
    assert r.status_code == 422 and r.json()["error"] == "LAMPIRAN_BUKAN_PDF"
    r2 = _kirim(c, pid, tipe="image/png")
    assert r2.status_code == 422 and r2.json()["error"] == "LAMPIRAN_BUKAN_PDF"
    assert c.get(f"{URL}/{pid}/sign-off").status_code == 404  # tidak ada yang tersimpan


def test_berkas_melebihi_batas_ditolak_422(app, client_as):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, riset_signoff_max_bytes=1000
    )
    c = _tim(client_as)
    pid = _protokol(c)
    r = _kirim(c, pid, isi=b"%PDF-" + b"B" * 2000)
    assert r.status_code == 422 and r.json()["error"] == "LAMPIRAN_TERLALU_BESAR"


def test_berkas_lewat_batas_body_rute_413(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    r = _kirim(c, pid, isi=b"%PDF-" + b"C" * (5 * 1024 * 1024 + 200_000))
    assert r.status_code == 413


def test_tanggal_wajib_dan_tidak_boleh_masa_depan(client_as):
    c = _tim(client_as)
    pid = _protokol(c)
    r = c.post(
        f"{URL}/{pid}/sign-off",
        data={"pi_nama": "Dr. PI"},
        files={"lampiran": ("e.pdf", PDF_KECIL, "application/pdf")},
    )
    assert r.status_code == 422
    besok = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    r2 = _kirim(c, pid, tanggal=besok)
    assert r2.status_code == 422
    assert c.get(f"{URL}/{pid}/sign-off").status_code == 404


def test_pi_nama_kosong_422(client_as):
    c = _tim(client_as)
    assert _kirim(c, _protokol(c), pi_nama="").status_code == 422


def test_bukan_tim_kajian_403(client_as):
    pid = _protokol(_tim(client_as))
    lain = client_as("bukan-tim", groups=["partisipan"])
    assert _kirim(lain, pid).status_code == 403
    assert lain.get(f"{URL}/{pid}/sign-off").status_code == 403
    assert lain.get(f"{URL}/{pid}/sign-off/lampiran").status_code == 403


def test_rute_lain_tetap_dibatasi_1mib(client_as):
    c = _tim(client_as)
    r = c.post(URL, json={"kode": "BESAR", "judul": "x", "isi": "y" * (2 * 1024 * 1024)})
    assert r.status_code == 413
