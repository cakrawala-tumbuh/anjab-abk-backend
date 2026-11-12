"""Test gerbang redaksi PII: pola, penanda stabil, kamus nama, daftar izin, dan log."""

from __future__ import annotations

import hashlib
import logging

import pytest
from sqlalchemy.orm import Session

from anjab_abk_backend.ai.redaksi import (
    SumberAi,
    gerbang_masukan,
    muat_kamus_nama,
    periksa_pii,
)
from anjab_abk_backend.config import Settings
from anjab_abk_backend.models import PartisipanModel

_BAWAAN = Settings(_env_file=None)
_SAMARKAN = Settings(_env_file=None, ai_pii_mode="SAMARKAN")
_KAMUS = ["Siti Rahmawati", "Budi Santoso"]


def _sumber(teks: str, jenis: str = "SINTETIS", hash_: str | None = None) -> SumberAi:
    return SumberAi(
        source_id="s1",
        source_hash=hash_ or hashlib.sha256(teks.encode()).hexdigest(),
        jenis=jenis,
        teks=teks,
    )


@pytest.mark.parametrize(
    ("teks", "kategori"),
    [
        ("hubungi andi.x@contoh.id segera", "EMAIL"),
        ("telp 081234567890 kantor", "TELEPON"),
        ("telp +6281234567890 kantor", "TELEPON"),
        ("telp 6281234567890 kantor", "TELEPON"),
        ("NIK 3201234567890123 tercatat", "NIK"),
        ("NIP 198501012010011001 tercatat", "NIP"),
    ],
)
def test_pola_positif(teks: str, kategori: str) -> None:
    hasil = periksa_pii(teks, [])
    assert hasil.temuan == {kategori: 1}
    assert f"[{kategori}_1]" in hasil.teks


@pytest.mark.parametrize(
    "teks",
    [
        "angka 123456789012345 lima belas digit",
        "angka 12345678901234567 tujuh belas digit",
        "tahun 2026 dan 08 saja",
        "tanpa pii sama sekali",
    ],
)
def test_pola_negatif(teks: str) -> None:
    hasil = periksa_pii(teks, [])
    assert hasil.temuan == {}
    assert hasil.teks == teks


def test_penanda_stabil_untuk_nilai_sama() -> None:
    hasil = periksa_pii("a@x.id lalu b@x.id lalu A@x.id", [])
    assert hasil.teks == "[EMAIL_1] lalu [EMAIL_2] lalu [EMAIL_1]"
    assert hasil.temuan == {"EMAIL": 3}


def test_kata_nama_kamus_dan_batas_kata() -> None:
    hasil = periksa_pii("Rahmawati hadir, siti juga, tetapi sitiawan tidak", _KAMUS)
    assert "Rahmawati" not in hasil.teks
    assert "sitiawan" in hasil.teks
    assert hasil.temuan["NAMA_TERDAFTAR"] == 2
    penuh = periksa_pii("Siti  Rahmawati dan BUDI santoso", _KAMUS)
    assert penuh.teks == "[NAMA_TERDAFTAR_1] dan [NAMA_TERDAFTAR_2]"


def test_kata_nama_pendek_tidak_ikut() -> None:
    assert periksa_pii("Ani dan Ali", ["Ani Ali Nur"]).temuan == {}


def test_konteks_orang_tua_memblok_pada_mode_samarkan() -> None:
    teks = "Pertemuan dengan orang tua Zainuddin soal nilai"
    hasil = gerbang_masukan(_sumber(teks), [], _SAMARKAN)
    assert not hasil.lolos
    assert hasil.alasan == "PII_DITEMUKAN"
    assert hasil.temuan == {"NAMA_MURID_KELUARGA": 1}
    assert periksa_pii("wali kelas hadir", []).temuan == {}


def test_gerbang_bawaan_jenis_hrd_ditolak() -> None:
    hasil = gerbang_masukan(_sumber("teks aman", jenis="HRD"), [], _BAWAAN)
    assert (hasil.lolos, hasil.alasan, hasil.sumber) == (False, "JENIS_DITOLAK", None)


def test_gerbang_wcp_tercantum_tetap_ditolak() -> None:
    s = Settings(_env_file=None, ai_jenis_sumber_diizinkan=["SINTETIS", "WCP_JAWABAN"])
    hasil = gerbang_masukan(_sumber("teks aman", jenis="WCP_JAWABAN"), [], s)
    assert hasil.alasan == "JENIS_DITOLAK"


def test_gerbang_hash_tak_cocok_dan_sumber_kosong() -> None:
    assert (
        gerbang_masukan(_sumber("isi", hash_="ab" * 32), [], _BAWAAN).alasan
        == "METADATA_SUMBER_HILANG"
    )
    assert gerbang_masukan(_sumber(""), [], _BAWAAN).alasan == "SUMBER_KOSONG"
    assert gerbang_masukan(None, [], _BAWAAN).alasan == "SUMBER_KOSONG"


def test_gerbang_bawaan_blokir_pii_sintetis() -> None:
    hasil = gerbang_masukan(_sumber("kontak a@x.id"), [], _BAWAAN)
    assert (hasil.lolos, hasil.alasan) == (False, "PII_DITEMUKAN")
    assert hasil.temuan == {"EMAIL": 1}


def test_gerbang_samarkan_meloloskan_dengan_hash_asli() -> None:
    teks = "a@x.id, 081234567890, 3201234567890123, 198501012010011001, Rahmawati"
    hasil = gerbang_masukan(_sumber(teks), _KAMUS, _SAMARKAN)
    assert hasil.lolos and hasil.alasan is None and hasil.sumber is not None
    assert hasil.sumber.teks == ("[EMAIL_1], [TELEPON_1], [NIK_1], [NIP_1], [NAMA_TERDAFTAR_1]")
    assert hasil.sumber.source_hash == hashlib.sha256(teks.encode()).hexdigest()


def test_gerbang_sintetis_bersih_lolos() -> None:
    hasil = gerbang_masukan(_sumber("narasi sintetis"), _KAMUS, _BAWAAN)
    assert hasil.lolos and hasil.sumber is not None and hasil.temuan == {}


def test_log_dan_hasil_tidak_memuat_nilai_pii(caplog: pytest.LogCaptureFixture) -> None:
    rahasia = ["rahasia.pribadi@x.id", "081234567899", "Zainuddin"]
    teks = f"{rahasia[0]} {rahasia[1]} orang tua {rahasia[2]}"
    with caplog.at_level(logging.DEBUG):
        hasil = gerbang_masukan(_sumber(teks), [], _BAWAAN)
    gabung = caplog.text + repr(hasil)
    assert not hasil.lolos
    for nilai in rahasia:
        assert nilai not in gabung


def test_muat_kamus_nama_aktif_dan_nonaktif(db_session: Session) -> None:
    for i, (nama, aktif) in enumerate([("Kamus Aktifa", True), ("Kamus Nonaktif", False)]):
        db_session.add(
            PartisipanModel(
                id=f"par_kamus{i}",
                nama=nama,
                email=f"kamus{i}@x.id",
                sekolah_id="skl_x",
                jabatan_utama_id="jbt_x",
                masa_kerja_tahun=1,
                aktif=aktif,
            )
        )
    db_session.flush()
    kamus = muat_kamus_nama(db_session)
    assert "Kamus Aktifa" in kamus and "Kamus Nonaktif" in kamus


_KETERANGAN = Settings(_env_file=None, ai_jenis_sumber_diizinkan=["KETERANGAN_ORANG"])


def test_gerbang_keterangan_orang_diizinkan_env_bersih_lolos() -> None:
    hasil = gerbang_masukan(
        _sumber("Cerita guru tentang rapat.", jenis="KETERANGAN_ORANG"), [], _KETERANGAN
    )
    assert hasil.lolos and hasil.alasan is None


def test_gerbang_keterangan_orang_ber_pii_tetap_ditolak() -> None:
    teks = "Hubungi 081234567890 atau NIK 3201234567890123."
    hasil = gerbang_masukan(_sumber(teks, jenis="KETERANGAN_ORANG"), [], _KETERANGAN)
    assert (hasil.lolos, hasil.alasan) == (False, "PII_DITEMUKAN")


def test_gerbang_keterangan_orang_bawaan_ditolak() -> None:
    hasil = gerbang_masukan(_sumber("teks aman", jenis="KETERANGAN_ORANG"), [], _BAWAAN)
    assert hasil.alasan == "JENIS_DITOLAK"


def test_gerbang_murid_diizinkan_env_tetap_ditolak() -> None:
    s = Settings(_env_file=None, ai_jenis_sumber_diizinkan=["MURID_X"])
    hasil = gerbang_masukan(_sumber("teks aman", jenis="MURID_X"), [], s)
    assert hasil.alasan == "JENIS_DITOLAK"
