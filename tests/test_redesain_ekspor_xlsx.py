"""Tes ekspor register XLSX 14 sheet redesain (backlog `#65`)."""

from __future__ import annotations

import uuid
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select

from anjab_abk_backend.models import RedesainKonteksModel
from anjab_abk_backend.redesain.ekspor_xlsx import (
    BARIS_HEADER,
    KALIMAT_STATIS,
    SHEET,
    XLSX_MEDIA_TYPE,
)

URL = "/api/v1/redesain/ekspor/register.xlsx"
KONF = "/api/v1/redesain/konfirmasi"
URUTAN = [
    "MULAI",
    "KONTEKS",
    "MASALAH",
    "KONFIRMASI",
    "BUKTI",
    "ALUR",
    "PENILAIAN",
    "ALTERNATIF",
    "SESI",
    "YAYASAN",
    "RUBRIK",
    "UJI_RUMUS",
    "CAKUPAN_19",
    "PERUBAHAN",
]


def _skenario(client_as, partisipan_factory, db_session):
    """Sekolah + masalah + alur + konfirmasi terkirim (diralat) + koreksi + penilaian."""
    admin = client_as("adm-x65", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    sekolah = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Xlsx {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_x"},
    ).json()["id"]
    partisipan_factory("tim-x65")
    pengisi_sub = f"skl-{uuid.uuid4().hex[:6]}"
    partisipan_factory(pengisi_sub, sekolah_id=sekolah)

    def tim():
        return client_as("tim-x65", groups=["tim-kajian"])

    konteks_id = db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == "K-01")
    ).one()
    mid = (
        tim()
        .post(
            "/api/v1/redesain/masalah",
            json={
                "konteks_id": konteks_id,
                "sekolah_id": sekolah,
                "periode_acuan": "TA 2026/27",
                "rumusan_hipotesis": "Jadwal disusun manual.",
                "sumber_awal_keterbatasan": "Catatan rapat.",
                "gelombang": "G1",
            },
        )
        .json()["id"]
    )
    tim().post(f"/api/v1/redesain/masalah/{mid}/status-konfirmasi", json={"dibuka": True})
    pid = (
        tim()
        .post(
            "/api/v1/redesain/proses",
            json={
                "masalah_id": mid,
                "sekolah_id": sekolah,
                "periode": "TA 2026/27",
                "nama_proses": "Jadwal",
            },
        )
        .json()["id"]
    )
    lid = (
        tim()
        .post(
            f"/api/v1/redesain/proses/{pid}/langkah",
            json={
                "tahap": "Susun",
                "pemicu_input": "Awal semester",
                "pelaksana": "Wakil Kepala Sekolah",
                "pekerjaan_sistem": "Spreadsheet",
                "keluaran_penerima": "Draf",
                "status_langkah": "Hipotesis",
            },
        )
        .json()["id"]
    )

    def pengisi():
        return client_as(pengisi_sub, groups=["sekolah-pengisi"])

    kid = pengisi().post(KONF, json={"masalah_id": mid}).json()["id"]
    pengisi().patch(f"{KONF}/{kid}", json={"cerita_sebelum": "Cerita kami."})
    pengisi().post(f"{KONF}/{kid}/kunci-cerita")
    pengisi().post(f"{KONF}/{kid}/tampilkan-dugaan")
    kor = pengisi().post(
        f"/api/v1/redesain/langkah/{lid}/koreksi",
        json={"isi": "Kami juga pakai WA.", "konfirmasi_id": kid},
    )
    assert kor.status_code == 201, kor.text
    isi = {
        "peran": "Guru",
        "kesesuaian": "Sebagian",
        "k1": "Tinggi",
        "k2": "Sedang",
        "k3": "Rendah",
        "k4": "Belum tahu",
        "indikasi_risiko": "Ada indikasi",
        "catatan_independensi": "Hadir sendiri.",
    }
    assert pengisi().patch(f"{KONF}/{kid}", json=isi).status_code == 200
    assert pengisi().post(f"{KONF}/{kid}/kirim").status_code == 200
    ralat = pengisi().post(f"{KONF}/{kid}/ralat")
    assert ralat.status_code == 201, ralat.text
    pen = tim().post(
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
    )
    assert pen.status_code == 201, pen.text
    return {"saran": pen.json()["saran_otomatis"], "kode_orang": kor.json()["kode_orang"]}


def _wb(resp):
    assert resp.status_code == 200, resp.text
    return load_workbook(BytesIO(resp.content))


def _baris(ws) -> list[list[object]]:
    return [
        [c.value for c in row]
        for row in ws.iter_rows(min_row=BARIS_HEADER + 1)
        if any(c.value is not None for c in row)
    ]


def test_empat_belas_sheet_header_dan_hitungan(client_as, partisipan_factory, db_session):
    s = _skenario(client_as, partisipan_factory, db_session)
    r = client_as("tim-x65", groups=["tim-kajian"]).get(URL)
    assert r.headers["content-type"].startswith(XLSX_MEDIA_TYPE)
    assert r.headers["content-disposition"].startswith('attachment; filename="register-redesain-')
    wb = _wb(r)
    assert wb.sheetnames == URUTAN == list(SHEET)
    for nama, (judul, header) in SHEET.items():
        ws = wb[nama]
        assert ws.cell(row=1, column=1).value == judul
        if header:
            assert [c.value for c in ws[BARIS_HEADER]][: len(header)] == header
            assert ws.max_column == len(header)
        else:
            assert ws.cell(row=2, column=1).value == KALIMAT_STATIS
    assert len(_baris(wb["KONTEKS"])) == 14
    assert len(_baris(wb["MASALAH"])) == 9  # 8 hipotesis seed + 1 masalah skenario
    assert len(_baris(wb["CAKUPAN_19"])) == 19
    pen = _baris(wb["PENILAIAN"])
    assert len(pen) == 1 and pen[0][9] == s["saran"]
    assert not _baris(wb["RUBRIK"])


def test_alur_koreksi_konfirmasi_digantikan_dan_tanpa_pii(
    client_as, partisipan_factory, db_session
):
    s = _skenario(client_as, partisipan_factory, db_session)
    wb = _wb(client_as("tim-x65", groups=["tim-kajian"]).get(URL))
    alur = _baris(wb["ALUR"])
    assert len(alur) == 1
    assert alur[0][13] == f"{s['kode_orang']}: Kami juga pakai WA."
    assert s["kode_orang"].startswith("O-")
    konf = _baris(wb["KONFIRMASI"])
    assert len(konf) == 1  # ralat masih draf -> hanya versi terkirim
    assert konf[0][6] == "Ya"
    assert konf[0][15] == "Ada indikasi"
    # Semantik `digantikan` mengikuti service konfirmasi: ada ralat (draf) yang menggantikannya.
    assert konf[0][16] == "[digantikan] Hadir sendiri."
    nama_atau_email = ("Partisipan ", "@test.id")
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    assert not any(x in c.value for x in nama_atau_email), (ws.title, c.coordinate)


def test_penanda_digantikan_pada_pembangkit():
    from datetime import UTC, date, datetime

    from anjab_abk_backend.redesain.ekspor_xlsx import DataRegister, bangun_register
    from anjab_abk_backend.redesain.schemas.konfirmasi import KonfirmasiDaftarRead
    from anjab_abk_backend.redesain.schemas.masalah import MasalahRead

    now = datetime.now(UTC)
    m = MasalahRead.model_construct(
        **{
            **dict.fromkeys(MasalahRead.model_fields),
            "id": "m1",
            "kode": "M-K01-01",
            "periode_acuan": "TA",
            "uraian_tugas_ids": [],
        },
    )
    dasar = {
        "masalah_id": "m1",
        "kode_orang": "O-0001",
        "sekolah_id": "s1",
        "sumber": "daring",
        "peran": "Guru",
        "tanggal": date(2026, 11, 1),
        "status": "terkirim",
        "created_at": now,
        "updated_at": now,
        "catatan_independensi": "Hadir sendiri.",
        **dict.fromkeys(
            [
                "cerita_sebelum",
                "dugaan_diperlihatkan",
                "kesesuaian",
                "koreksi",
                "masalah_baru",
                "k1",
                "k2",
                "k3",
                "k4",
                "alasan_k",
                "indikasi_risiko",
                "catatan_akses",
            ]
        ),
    }
    lama = KonfirmasiDaftarRead.model_construct(id="a", digantikan=True, **dasar)
    baru = KonfirmasiDaftarRead.model_construct(id="b", digantikan=False, **dasar)
    wb = load_workbook(BytesIO(bangun_register(DataRegister(masalah=[m], konfirmasi=[lama, baru]))))
    konf = _baris(wb["KONFIRMASI"])
    assert [b[16] for b in konf] == ["[digantikan] Hadir sendiri.", "Hadir sendiri."]


def test_negatif_403_401(client_as, anon_client):
    assert client_as("skl-x65", groups=["sekolah-pengisi"]).get(URL).status_code == 403
    assert anon_client.get(URL).status_code == 401
