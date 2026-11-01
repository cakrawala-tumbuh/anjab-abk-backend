"""Tes alternatif redesain: CRUD+search Tim, kode `U-NNN`, aturan opsi/status (backlog `#59`)."""

from __future__ import annotations

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel
from anjab_abk_backend.redesain.schemas.penilaian import hari_ini_wib

URL = "/api/v1/redesain/alternatif"
URL_KODE = "/api/v1/redesain/kode-orang"
URL_PENILAIAN = "/api/v1/redesain/penilaian"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _alt(masalah_id: str, **kw):
    base = {
        "masalah_id": masalah_id,
        "opsi": "Sederhanakan",
        "alur_kini_vs_usulan": "Kini tiga tahap manual; usulan satu formulir.",
    }
    base.update(kw)
    return base


def test_create_kode_default_search_dan_pihak_jabatan(
    client_as, partisipan_factory, db_session, jabatan_id_tk
):
    c = _tim(client_as, partisipan_factory, "alt-1")
    mid = _masalah_id(db_session)
    r = c.post(URL, json=_alt(mid, pihak_asal_jabatan_id=jabatan_id_tk))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["kode"] == "U-001"
    assert a["status_telaah"] == "Belum ditelaah"
    assert a["gap_penerima"] == "Belum tahu"
    assert a["pihak_asal_jabatan_id"] == jabatan_id_tk

    s = c.post(f"{URL}/search", json={"domain": [["opsi", "=", "Sederhanakan"]]})
    assert s.status_code == 200, s.text
    assert s.json()["total"] >= 1
    assert c.get(f"{URL}/{a['id']}").json()["kode"] == "U-001"
    assert c.get(URL).json()["total"] >= 1
    assert c.post(URL, json=_alt(mid)).json()["kode"] == "U-002"


def test_patch_uji_disetujui_butuh_keputusan_dan_pemutus_riwayat(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "alt-2")
    mid = _masalah_id(db_session)
    pemutus = c.post(URL_KODE, json={"keterangan_peran": "Pemutus"}).json()["kode"]
    a = c.post(URL, json=_alt(mid, opsi="Uji terbatas")).json()

    gagal = c.patch(f"{URL}/{a['id']}", json={"status_telaah": "Uji disetujui terpisah"})
    assert gagal.status_code == 422, gagal.text
    ok = c.patch(
        f"{URL}/{a['id']}",
        json={
            "status_telaah": "Uji disetujui terpisah",
            "keputusan": "Uji di satu kelas.",
            "pemutus_kode_orang": pemutus,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status_telaah"] == "Uji disetujui terpisah"

    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "alternatif", rw.entitas_id == a["id"])
    ).all()
    assert sorted(r.aksi for r in rows) == ["create", "update"]


def test_create_langsung_uji_disetujui_tanpa_keputusan_422(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "alt-3")
    mid = _masalah_id(db_session)
    r = c.post(URL, json=_alt(mid, status_telaah="Uji disetujui terpisah"))
    assert r.status_code == 422, r.text


def test_alihkan_tanpa_penerima_dan_jabatan_tak_dikenal_422(
    client_as, partisipan_factory, db_session, jabatan_id_tk
):
    c = _tim(client_as, partisipan_factory, "alt-4")
    mid = _masalah_id(db_session)
    assert c.post(URL, json=_alt(mid, opsi="Alihkan tugas bersyarat")).status_code == 422
    assert c.post(URL, json=_alt(mid, pihak_asal_jabatan_id="jbt-tidak-ada")).status_code == 422
    ok = c.post(
        URL,
        json=_alt(mid, opsi="Alihkan tugas bersyarat", pihak_penerima_jabatan_id=jabatan_id_tk),
    )
    assert ok.status_code == 201, ok.text
    # Mengosongkan penerima pada opsi pengalihan ditolak pada PATCH juga.
    p = c.patch(f"{URL}/{ok.json()['id']}", json={"pihak_penerima_jabatan_id": None})
    assert p.status_code == 422, p.text


def test_kosakata_dan_masalah_tak_dikenal_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "alt-5")
    mid = _masalah_id(db_session)
    assert c.post(URL, json=_alt(mid, gap_penerima="Ada indikasi")).status_code == 422
    assert c.post(URL, json=_alt(mid, opsi="Rumor")).status_code == 422
    assert c.post(URL, json=_alt("tidak-ada")).status_code == 422
    assert c.post(URL, json=_alt(mid, pemutus_kode_orang="O-9999")).status_code == 422


def test_prioritas_final_penilaian_tak_mengubah_status_telaah(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "alt-6")
    mid = _masalah_id(db_session, "M-K02-01")
    a = c.post(URL, json=_alt(mid)).json()
    pn = c.post(
        URL_PENILAIAN,
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
    )
    assert pn.status_code == 201, pn.text
    pid = pn.json()["id"]
    kode = c.post(URL_KODE, json={"keterangan_peran": "Pemutus"}).json()["kode"]
    put = c.post(
        f"{URL_PENILAIAN}/{pid}/putuskan",
        json={
            "prioritas_final": "P3 - Pantau",
            "alasan_final": "Dampak kecil.",
            "pemutus_kode_orang": kode,
            "pemutus_jabatan": "Ketua Tim Kajian",
            "tanggal_keputusan": hari_ini_wib().isoformat(),
        },
    )
    assert put.status_code == 200, put.text
    assert c.get(f"{URL}/{a['id']}").json()["status_telaah"] == "Belum ditelaah"


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory, db_session):
    partisipan_factory("alt-7")
    sp = client_as("alt-7", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_alt(_masalah_id(db_session))).status_code == 403
