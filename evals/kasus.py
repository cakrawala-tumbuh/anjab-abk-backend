"""Muat dan validasi berkas kasus evaluasi (``evals/<kode>/kasus.json``).

Satu berkas per fungsi AI. Validasi ketat (``extra="forbid"``) dan dijalankan untuk SEMUA
kasus sebelum satu pun panggilan model: kasus rusak menghentikan evaluasi dengan exit 2.
Seluruh data kasus sintetis; jenis sumber selain ``SINTETIS`` ditolak, kecuali satu
pengecualian sempit untuk kasus tanpa model yang justru menguji penolakan jenis oleh
gerbang (lihat ``_periksa_jenis``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from anjab_abk_backend.ai.fungsi_p01 import FUNGSI_P01, SIFAT_FAKTA_P01, ParameterP01
from anjab_abk_backend.ai.fungsi_p02 import FUNGSI_P02, ParameterP02
from anjab_abk_backend.ai.fungsi_p03 import FUNGSI_P03, ParameterP03
from anjab_abk_backend.ai.fungsi_p04 import FUNGSI_P04, ParameterP04
from anjab_abk_backend.ai.fungsi_p09 import FUNGSI_P09, ParameterP09
from anjab_abk_backend.ai.fungsi_p10 import FUNGSI_P10, ParameterP10
from anjab_abk_backend.ai.gateway import FungsiAi

__all__ = [
    "DEFINISI_FUNGSI",
    "DefinisiFungsi",
    "HarapanKasus",
    "Kasus",
    "KasusRusak",
    "SumberKasus",
    "muat_kasus",
]

_POLA_ID = r"^[A-Za-z0-9_.:-]{1,100}$"
_ALASAN_GERBANG = ("SUMBER_KOSONG", "METADATA_SUMBER_HILANG", "JENIS_DITOLAK", "PII_DITEMUKAN")
_STATUS_MODEL = ("LOLOS", "EVIDENCE_GAP")
_PREFIKS_JENIS_TERLARANG = ("WCP", "DCS", "KONSELING", "MURID")


class KasusRusak(Exception):
    """Berkas kasus tidak sah (struktur, nilai, atau jenis sumber); evaluasi exit 2."""


@dataclass(frozen=True)
class DefinisiFungsi:
    """Fungsi AI yang dapat dievaluasi.

    Attributes:
        fungsi: Definisi fungsi produksi (instruksi dan skema yang sama dengan worker).
        parameter: Model Pydantic yang memvalidasi ``parameter`` tiap kasus.
        berkas: Lokasi bawaan ``kasus.json`` fungsi ini.
    """

    fungsi: FungsiAi
    parameter: type[BaseModel]
    berkas: Path


DEFINISI_FUNGSI: dict[str, DefinisiFungsi] = {
    "P01": DefinisiFungsi(
        fungsi=FUNGSI_P01,
        parameter=ParameterP01,
        berkas=Path(__file__).parent / "p01" / "kasus.json",
    ),
    "P02": DefinisiFungsi(
        fungsi=FUNGSI_P02,
        parameter=ParameterP02,
        berkas=Path(__file__).parent / "p02" / "kasus.json",
    ),
    "P03": DefinisiFungsi(
        fungsi=FUNGSI_P03,
        parameter=ParameterP03,
        berkas=Path(__file__).parent / "p03" / "kasus.json",
    ),
    "P04": DefinisiFungsi(
        fungsi=FUNGSI_P04,
        parameter=ParameterP04,
        berkas=Path(__file__).parent / "p04" / "kasus.json",
    ),
    "P09": DefinisiFungsi(
        fungsi=FUNGSI_P09,
        parameter=ParameterP09,
        berkas=Path(__file__).parent / "p09" / "kasus.json",
    ),
    "P10": DefinisiFungsi(
        fungsi=FUNGSI_P10,
        parameter=ParameterP10,
        berkas=Path(__file__).parent / "p10" / "kasus.json",
    ),
}
"""Fungsi yang bisa dievaluasi, menurut kode; item berikutnya menambah entri di sini."""


class SumberKasus(BaseModel):
    """Satu sumber sintetis dalam kasus.

    Attributes:
        source_id: Id sumber.
        jenis: Jenis sumber; ``SINTETIS`` (lihat ``_periksa_jenis`` untuk pengecualian).
        teks: Isi sumber (fiktif).
        source_hash: Hash eksplisit; kosong/``None`` = dihitung dari ``teks``. Dipakai
            kasus yang sengaja menguji metadata hilang (``""``).
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    jenis: str
    teks: str
    source_hash: str | None = None


class HarapanKasus(BaseModel):
    """Harapan perilaku satu kasus.

    Attributes:
        jalur: ``TANPA_MODEL`` (gerbang harus menolak, nol panggilan) atau ``MODEL``.
        status_qa: Status akhir yang diterima untuk ``MODEL`` (``LOLOS``/``EVIDENCE_GAP``).
        alasan_gerbang: Alasan penolakan gerbang yang diharapkan untuk ``TANPA_MODEL``.
        bidang_teks: Jalur titik pada keluaran yang diperiksa pola (``isi.draft_text``).
        dilarang_pola: Frasa yang tidak boleh muncul (spasi dan huruf dinormalkan).
        harus_memuat: Frasa wajib; elemen berupa daftar berarti salah satu cukup.
        angka_baru_dilarang: Bilangan pada teks harus ada di sumber atau parameter.
        kontradiksi_wajib: ``contradictions`` pada keluaran harus terisi.
        kategori_wajib: Khusus P09; kategori temuan (``blocking_findings`` atau
            ``major_findings``) yang wajib muncul; elemen berupa daftar berarti salah satu cukup.
        tanpa_temuan_berat: Khusus P09; ``blocking_findings`` dan ``major_findings`` harus
            kosong (draf bersih).
        span_temuan_harus_ada: Khusus P09; tiap temuan harus menunjuk ``source_id`` yang ada di
            kasus dengan ``span`` yang benar-benar terkandung di teks sumber itu.
        hanya_sifat: Khusus P01; ``sifat`` tiap fakta pada ``factual_extracts`` harus salah satu
            nilai ini (mis. ``["NORMATIF"]`` untuk dokumen normatif); kosong = tidak diperiksa.
        span_fakta_harus_ada: Khusus P01; tiap fakta harus menunjuk ``source_id`` yang ada di
            kasus dengan ``span`` yang benar-benar terkandung di teks sumber itu.
        material_harapan: Khusus P04; nilai ``material`` yang diharapkan pada keluaran
            (``None`` = tidak diperiksa).
        pertanyaan_tunggal: Khusus P04; bila ``material`` benar, ``one_neutral_question`` harus
            berisi tepat satu tanda tanya; bila salah, pertanyaan harus kosong atau ``null``.
    """

    model_config = ConfigDict(extra="forbid")

    jalur: Literal["TANPA_MODEL", "MODEL"]
    status_qa: list[str] = Field(default_factory=list)
    alasan_gerbang: str | None = None
    bidang_teks: list[str] = Field(default_factory=lambda: ["isi.draft_text"])
    dilarang_pola: list[str] = Field(default_factory=list)
    harus_memuat: list[str | list[str]] = Field(default_factory=list)
    angka_baru_dilarang: bool = False
    kontradiksi_wajib: bool = False
    kategori_wajib: list[str | list[str]] = Field(default_factory=list)
    tanpa_temuan_berat: bool = False
    span_temuan_harus_ada: bool = False
    hanya_sifat: list[str] = Field(default_factory=list)
    span_fakta_harus_ada: bool = False
    material_harapan: bool | None = None
    pertanyaan_tunggal: bool = False

    @model_validator(mode="after")
    def _konsisten(self) -> HarapanKasus:
        """Pastikan isian sesuai ``jalur``."""
        if self.jalur == "TANPA_MODEL":
            if self.alasan_gerbang not in _ALASAN_GERBANG:
                raise ValueError("TANPA_MODEL menuntut alasan_gerbang yang sah")
        else:
            if not self.status_qa or any(s not in _STATUS_MODEL for s in self.status_qa):
                raise ValueError("MODEL menuntut status_qa berisi LOLOS/EVIDENCE_GAP")
            if self.alasan_gerbang is not None:
                raise ValueError("alasan_gerbang hanya untuk TANPA_MODEL")
        if not self.bidang_teks:
            raise ValueError("bidang_teks tidak boleh kosong")
        if any(x not in SIFAT_FAKTA_P01 for x in self.hanya_sifat):
            raise ValueError("hanya_sifat harus berisi sifat fakta P01 yang sah")
        return self


class Kasus(BaseModel):
    """Satu kasus evaluasi sintetis.

    Attributes:
        id: Id unik kasus.
        rujukan: Rujukan persyaratan yang dicakup (mis. ``R11-003``, ``PRM:72``).
        kamus_nama: Nama fiktif yang dianggap terdaftar (kamus redaksi PII).
        sumber: Sumber sintetis.
        parameter: Parameter fungsi (divalidasi model parameter fungsi).
        harapan: Harapan perilaku.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_POLA_ID)
    rujukan: list[str] = Field(min_length=1)
    kamus_nama: list[str] = Field(default_factory=list)
    sumber: list[SumberKasus] = Field(default_factory=list)
    parameter: dict[str, Any]
    harapan: HarapanKasus


class _Berkas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fungsi: str
    kasus: list[Kasus] = Field(min_length=1)


def _periksa_jenis(kasus: Kasus) -> None:
    """Tolak jenis sumber selain ``SINTETIS``.

    Satu pengecualian: kasus ``TANPA_MODEL`` ber-``alasan_gerbang`` ``JENIS_DITOLAK`` boleh
    memakai jenis berawalan terlarang (``WCP``/``DCS``/``KONSELING``/``MURID``), karena
    itulah yang diuji. Teksnya tetap sintetis. ``DOKUMEN_RESMI`` dan jenis lain ditolak.

    Raises:
        KasusRusak: ada jenis yang tidak diizinkan.
    """
    pengecualian = kasus.harapan.jalur == "TANPA_MODEL" and (
        kasus.harapan.alasan_gerbang == "JENIS_DITOLAK"
    )
    for s in kasus.sumber:
        jenis = s.jenis.strip().upper()
        if jenis == "SINTETIS":
            continue
        if pengecualian and jenis.startswith(_PREFIKS_JENIS_TERLARANG):
            continue
        raise KasusRusak(f"kasus {kasus.id}: jenis sumber '{s.jenis}' tidak diizinkan")


_KHAS_FUNGSI = {
    "P09": ("kategori_wajib", "tanpa_temuan_berat", "span_temuan_harus_ada"),
    "P01": ("hanya_sifat", "span_fakta_harus_ada"),
    "P04": ("material_harapan", "pertanyaan_tunggal"),
}
"""Isian ``HarapanKasus`` yang hanya sah untuk satu fungsi."""

_TANPA_DRAFT_TEXT = ("P01", "P02", "P03", "P04", "P09")
"""Fungsi yang keluarannya tidak punya ``isi.draft_text``."""


def _terisi(h: HarapanKasus, nama: str) -> bool:
    """Apakah isian ``nama`` dipakai; ``material_harapan=false`` tetap terhitung terisi."""
    nilai = getattr(h, nama)
    return nilai is not None if nama == "material_harapan" else bool(nilai)


def _periksa_khas_fungsi(kasus: Kasus, kode_fungsi: str) -> None:
    """Pastikan isian khas satu fungsi tidak dipakai fungsi lain dan bidang teks sesuai.

    Raises:
        KasusRusak: isian khas fungsi lain dipakai (mis. isian P09 pada P01 atau P10), atau
            kasus P01/P02/P03/P04/P09 berjalur ``MODEL`` masih memakai bidang teks bawaan P10
            (``isi.draft_text``).
    """
    h = kasus.harapan
    for pemilik, isian in _KHAS_FUNGSI.items():
        if pemilik != kode_fungsi and any(_terisi(h, f) for f in isian):
            raise KasusRusak(f"kasus {kasus.id}: isian khas {pemilik} dipakai pada {kode_fungsi}")
    if (
        kode_fungsi in _TANPA_DRAFT_TEXT
        and h.jalur == "MODEL"
        and "isi.draft_text" in h.bidang_teks
    ):
        raise KasusRusak(f"kasus {kasus.id}: {kode_fungsi} tidak punya isi.draft_text")


def muat_kasus(berkas: Path, kode_fungsi: str, definisi: DefinisiFungsi) -> list[Kasus]:
    """Baca dan validasi seluruh kasus satu fungsi.

    Args:
        berkas: Jalur ``kasus.json``.
        kode_fungsi: Kode fungsi yang diminta operator; harus sama dengan isi berkas.
        definisi: Definisi fungsi (untuk memvalidasi ``parameter``).

    Returns:
        Daftar kasus sesuai urutan berkas.

    Raises:
        KasusRusak: berkas tak terbaca, bukan JSON, struktur salah, id ganda, parameter
            tidak sah, atau jenis sumber tidak diizinkan.
    """
    try:
        data = json.loads(berkas.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KasusRusak(f"berkas kasus tak terbaca: {type(exc).__name__}") from exc
    try:
        isi = _Berkas.model_validate(data)
    except ValidationError as exc:
        raise KasusRusak(f"struktur kasus tidak sah: {exc.error_count()} galat") from exc
    if isi.fungsi != kode_fungsi:
        raise KasusRusak(f"berkas kasus untuk fungsi '{isi.fungsi}', diminta '{kode_fungsi}'")
    lihat: set[str] = set()
    for k in isi.kasus:
        if k.id in lihat:
            raise KasusRusak(f"id kasus ganda: {k.id}")
        lihat.add(k.id)
        try:
            definisi.parameter.model_validate(k.parameter)
        except ValidationError as exc:
            raise KasusRusak(f"kasus {k.id}: parameter tidak sah") from exc
        _periksa_jenis(k)
        _periksa_khas_fungsi(k, kode_fungsi)
    return isi.kasus
