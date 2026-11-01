"""Tes penilaian redesain: CRUD+search Tim, saran triase tersimpan, 409/422/403 (backlog `#57`)."""

from __future__ import annotations

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel

URL = "/api/v1/redesain/penilaian"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _t03(masalah_id: str, **kw):
    base = {
        "masalah_id": masalah_id,
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


def test_create_t03_lalu_patch_k3_rendah_hitung_ulang_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "pnl-1")
    mid = _masalah_id(db_session)
    r = c.post(URL, json=_t03(mid))
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["saran_otomatis"] == "P1 - Utama"
    assert p["versi_aturan_triase"] == "v1.3"

    u = c.patch(f"{URL}/{p['id']}", json={"k3": "Rendah"})
    assert u.status_code == 200, u.text
    assert u.json()["saran_otomatis"] == "P2 - Berikutnya"
    assert u.json()["k4"] == "Tinggi"

    assert c.get(f"{URL}/{p['id']}").json()["saran_otomatis"] == "P2 - Berikutnya"
    assert c.get(URL).json()["total"] >= 1
    s = c.post(f"{URL}/search", json={"domain": [["saran_otomatis", "=", "P2 - Berikutnya"]]})
    assert s.status_code == 200, s.text
    assert [x["id"] for x in s.json()["items"]] == [p["id"]]

    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "penilaian", rw.entitas_id == p["id"])
    ).all()
    assert sorted(x.aksi for x in rows) == ["create", "update"]
    upd = next(x for x in rows if x.aksi == "update")
    assert upd.nilai_sesudah["saran_otomatis"] == "P2 - Berikutnya"


def test_saran_di_payload_diabaikan(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-2")
    mid = _masalah_id(db_session)
    r = c.post(
        URL,
        json=_t03(mid, saran_otomatis="P3 - Pantau", versi_aturan_triase="v0"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["saran_otomatis"] == "P1 - Utama"
    assert r.json()["versi_aturan_triase"] == "v1.3"
    u = c.patch(f"{URL}/{r.json()['id']}", json={"saran_otomatis": "P0 - Eskalasi"})
    assert u.status_code == 200, u.text
    assert u.json()["saran_otomatis"] == "P1 - Utama"


def test_belum_cukup_klarifikasi_dan_k_kosong(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-3")
    r = c.post(URL, json=_t03(_masalah_id(db_session), status_bukti="Belum cukup"))
    assert r.status_code == 201, r.text
    assert r.json()["saran_otomatis"] == "K - Klarifikasi"
    kosong = c.post(
        URL,
        json={
            "masalah_id": _masalah_id(db_session, "M-K02-01"),
            "status_bukti": "Diperkuat untuk klaim",
            "gap_material": "Tidak",
            "indikasi_kritis": "Tidak terlihat",
        },
    )
    assert kosong.status_code == 201, kosong.text
    assert kosong.json()["k1"] is None
    assert kosong.json()["saran_otomatis"] == "K - Klarifikasi"


def test_create_kedua_409_dan_validasi_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-4")
    mid = _masalah_id(db_session)
    assert c.post(URL, json=_t03(mid)).status_code == 201
    assert c.post(URL, json=_t03(mid)).status_code == 409
    assert c.post(URL, json=_t03(mid, indikasi_kritis="Ya")).status_code == 422
    assert c.post(URL, json=_t03("tidak-ada")).status_code == 422
    assert c.post(URL, json=_t03(mid, asing="x")).status_code == 422
    assert c.get(f"{URL}/tidak-ada").status_code == 404


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory, db_session):
    partisipan_factory("pnl-5")
    sp = client_as("pnl-5", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_t03(_masalah_id(db_session))).status_code == 403
    assert sp.post(f"{URL}/search", json={"domain": []}).status_code == 403


# --- BE-8b (#58): prioritas final beralasan, status, agenda, sebaran K ---------------------

import uuid  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from anjab_abk_backend.models import RedesainKodeOrangModel, RedesainKonfirmasiModel  # noqa: E402
from anjab_abk_backend.redesain.schemas.penilaian import hari_ini_wib  # noqa: E402


def _kode_orang(db_session, kode: str = "O-9001") -> str:
    db_session.add(RedesainKodeOrangModel(id=str(uuid.uuid4()), kode=kode))
    db_session.flush()
    return kode


def _putus(kode: str, **kw):
    base = {
        "prioritas_final": "P1 - Utama",
        "alasan_final": "Dampak besar pada guru.",
        "pemutus_kode_orang": kode,
        "pemutus_jabatan": "Ketua Tim Kajian",
        "tanggal_keputusan": hari_ini_wib().isoformat(),
    }
    base.update(kw)
    return base


def test_putuskan_sama_saran_peringatan_kosong_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "pnl-6")
    kode = _kode_orang(db_session)
    p = c.post(URL, json=_t03(_masalah_id(db_session))).json()
    assert p["status_penilaian"] == "Belum ditelaah"
    r = c.post(f"{URL}/{p['id']}/putuskan", json=_putus(kode))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["peringatan"] == []
    assert j["status_penilaian"] == "Telah diputuskan"
    assert j["saran_saat_keputusan"] == "P1 - Utama"
    assert j["pemutus_kode_orang"] == kode
    # boleh diulang; setiap keputusan tercatat
    assert (
        c.post(
            f"{URL}/{p['id']}/putuskan", json=_putus(kode, prioritas_final="P2 - Berikutnya")
        ).status_code
        == 200
    )
    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "penilaian", rw.entitas_id == p["id"], rw.aksi == "putuskan")
    ).all()
    assert len(rows) == 2


def test_putuskan_hipotesis_p1_peringatan_tanpa_bukti(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-7")
    kode = _kode_orang(db_session)
    p = c.post(
        URL, json=_t03(_masalah_id(db_session), status_bukti="Hipotesis", k3="Tinggi")
    ).json()
    r = c.post(f"{URL}/{p['id']}/putuskan", json=_putus(kode, prioritas_final="P1 - Utama"))
    assert r.status_code == 200, r.text
    kodes = {x["kode"] for x in r.json()["peringatan"]}
    assert "PRIORITAS_TANPA_BUKTI" in kodes


def test_putuskan_beda_saran_bukti_kuat_hanya_berbeda(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-8")
    kode = _kode_orang(db_session)
    p = c.post(URL, json=_t03(_masalah_id(db_session))).json()
    assert p["saran_otomatis"] == "P1 - Utama"
    r = c.post(f"{URL}/{p['id']}/putuskan", json=_putus(kode, prioritas_final="P3 - Pantau"))
    assert r.status_code == 200, r.text
    assert [x["kode"] for x in r.json()["peringatan"]] == ["BERBEDA_DARI_SARAN"]


def test_putuskan_validasi_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-9")
    kode = _kode_orang(db_session)
    pid = c.post(URL, json=_t03(_masalah_id(db_session))).json()["id"]
    u = f"{URL}/{pid}/putuskan"
    assert c.post(u, json=_putus(kode, alasan_final="")).status_code == 422
    assert c.post(u, json=_putus(kode, alasan_final="   ")).status_code == 422
    body = _putus(kode)
    del body["alasan_final"]
    assert c.post(u, json=body).status_code == 422
    besok = (hari_ini_wib() + timedelta(days=1)).isoformat()
    assert c.post(u, json=_putus(kode, tanggal_keputusan=besok)).status_code == 422
    assert c.post(u, json=_putus("O-0000-xx")).status_code == 422
    assert c.post(f"{URL}/tidak-ada/putuskan", json=_putus(kode)).status_code == 404
    assert isinstance(date.today(), date)


def test_status_empat_nilai_dan_telah_diputuskan_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-10")
    pid = c.post(URL, json=_t03(_masalah_id(db_session))).json()["id"]
    for st in ("Perlu klarifikasi", "Siap untuk telaah yayasan", "Ditunda", "Belum ditelaah"):
        r = c.post(f"{URL}/{pid}/status", json={"status_penilaian": st})
        assert r.status_code == 200, r.text
        assert r.json()["status_penilaian"] == st
    assert (
        c.post(f"{URL}/{pid}/status", json={"status_penilaian": "Telah diputuskan"}).status_code
        == 422
    )
    assert (
        c.post(f"{URL}/tidak-ada/status", json={"status_penilaian": "Ditunda"}).status_code == 404
    )


def test_agenda_yayasan_hanya_siap(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-11")
    a = c.post(URL, json=_t03(_masalah_id(db_session))).json()["id"]
    c.post(URL, json=_t03(_masalah_id(db_session, "M-K02-01")))
    c.post(f"{URL}/{a}/status", json={"status_penilaian": "Siap untuk telaah yayasan"})
    r = c.get(f"{URL}/agenda-yayasan")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["items"]] == [a]
    assert r.json()["total"] == 1


def _konf(db_session, mid: str, status: str, k1: str | None, menggantikan: str | None = None):
    kid = str(uuid.uuid4())
    db_session.add(
        RedesainKonfirmasiModel(
            id=kid,
            masalah_id=mid,
            kode_orang="O-9100",
            sekolah_id="skl-x",
            tanggal=date.today(),
            status=status,
            k1=k1,
            menggantikan_id=menggantikan,
        )
    )
    db_session.flush()
    return kid


def test_sebaran_k_abaikan_draf_dan_digantikan(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-12")
    mid = _masalah_id(db_session)
    _konf(db_session, mid, "terkirim", "Tinggi")
    lama = _konf(db_session, mid, "terkirim", "Sedang")
    _konf(db_session, mid, "draf", "Rendah")
    r = c.get(f"/api/v1/redesain/masalah/{mid}/sebaran-k")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["jumlah_konfirmasi"] == 2
    assert j["k1"] == {"Tinggi": 1, "Sedang": 1, "Rendah": 0, "Belum tahu": 0, "kosong": 0}
    assert j["k2"]["kosong"] == 2
    # ralat menggantikan `lama` -> hitungan bergeser ke versi baru
    _konf(db_session, mid, "terkirim", "Rendah", menggantikan=lama)
    j = c.get(f"/api/v1/redesain/masalah/{mid}/sebaran-k").json()
    assert j["k1"] == {"Tinggi": 1, "Sedang": 0, "Rendah": 1, "Belum tahu": 0, "kosong": 0}
    assert c.get("/api/v1/redesain/masalah/tidak-ada/sebaran-k").status_code == 404


def test_sebaran_k_draf_ralat_tidak_menggantikan_terkirim(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "pnl-14")
    mid = _masalah_id(db_session)
    url = f"/api/v1/redesain/masalah/{mid}/sebaran-k"
    lama = _konf(db_session, mid, "terkirim", "Sedang")
    ralat = _konf(db_session, mid, "draf", "Rendah", menggantikan=lama)
    j = c.get(url).json()
    assert j["jumlah_konfirmasi"] == 1
    assert j["k1"]["Sedang"] == 1 and j["k1"]["Rendah"] == 0
    # draf ralat dikirim -> menggantikan versi lama
    db_session.get(RedesainKonfirmasiModel, ralat).status = "terkirim"
    db_session.flush()
    j = c.get(url).json()
    assert j["jumlah_konfirmasi"] == 1
    assert j["k1"]["Rendah"] == 1 and j["k1"]["Sedang"] == 0


def test_sebaran_k_dua_rantai_satu_punya_draf_ralat(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-15")
    mid = _masalah_id(db_session)
    a = _konf(db_session, mid, "terkirim", "Sedang")
    _konf(db_session, mid, "terkirim", "Tinggi")
    _konf(db_session, mid, "draf", "Rendah", menggantikan=a)
    assert c.get(f"/api/v1/redesain/masalah/{mid}/sebaran-k").json()["jumlah_konfirmasi"] == 2


def test_sebaran_k_hanya_draf_nol(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-16")
    mid = _masalah_id(db_session)
    _konf(db_session, mid, "draf", "Rendah")
    assert c.get(f"/api/v1/redesain/masalah/{mid}/sebaran-k").json()["jumlah_konfirmasi"] == 0


def test_endpoint_baru_ditolak_untuk_sekolah_pengisi(client_as, partisipan_factory, db_session):
    partisipan_factory("pnl-13")
    kode = _kode_orang(db_session, "O-9002")
    mid = _masalah_id(db_session)
    sp = client_as("pnl-13", groups=["sekolah-pengisi"])
    assert sp.post(f"{URL}/x/putuskan", json=_putus(kode)).status_code == 403
    assert sp.post(f"{URL}/x/status", json={"status_penilaian": "Ditunda"}).status_code == 403
    assert sp.get(f"{URL}/agenda-yayasan").status_code == 403
    assert sp.get(f"/api/v1/redesain/masalah/{mid}/sebaran-k").status_code == 403
