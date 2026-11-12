"""Skema Pydantic alternatif redesain (sheet ALTERNATIF; BUKAN bagian skor K1-K4)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .kosakata import OpsiAlternatif, StatusTelaahAlternatif, YaTidak


class AlternatifCreate(BaseModel):
    """Payload alternatif baru; `kode` dibangkitkan sistem (`U-001`, global)."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah redesain yang dicarikan alternatif.")
    opsi: OpsiAlternatif = Field(description="Jenis alternatif.")
    alur_kini_vs_usulan: str = Field(min_length=1, description="Alur kini dibanding alur usulan.")
    pihak_asal_jabatan_id: str | None = Field(
        default=None, max_length=40, description="ID jabatan pihak asal (bukan orang)."
    )
    pihak_penerima_jabatan_id: str | None = Field(
        default=None, max_length=40, description="ID jabatan penerima; wajib bila opsi pengalihan."
    )
    komitmen_penerima: str | None = None
    jadwal_puncak: str | None = None
    keterampilan_akses: str | None = None
    tambahan_bersih: str | None = None
    risiko_layanan: str | None = None
    gap_penerima: YaTidak = Field(default="Belum tahu", description="Ada gap pada penerima?")
    status_telaah: StatusTelaahAlternatif = Field(default="Belum ditelaah")
    pemutus_kode_orang: str | None = Field(default=None, max_length=20, examples=["O-0001"])
    keputusan: str | None = None
    prasyarat_monitoring: str | None = None
    catatan_versi_bukti: str | None = None


class AlternatifUpdate(BaseModel):
    """Payload ubah parsial alternatif. `kode` dan `masalah_id` tidak dapat diubah.

    Field nullable boleh dikosongkan dengan `null`; field wajib yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    opsi: OpsiAlternatif | None = None
    alur_kini_vs_usulan: str | None = Field(default=None, min_length=1)
    pihak_asal_jabatan_id: str | None = Field(default=None, max_length=40)
    pihak_penerima_jabatan_id: str | None = Field(default=None, max_length=40)
    komitmen_penerima: str | None = None
    jadwal_puncak: str | None = None
    keterampilan_akses: str | None = None
    tambahan_bersih: str | None = None
    risiko_layanan: str | None = None
    gap_penerima: YaTidak | None = None
    status_telaah: StatusTelaahAlternatif | None = None
    pemutus_kode_orang: str | None = Field(default=None, max_length=20)
    keputusan: str | None = None
    prasyarat_monitoring: str | None = None
    catatan_versi_bukti: str | None = None


class AlternatifRead(BaseModel):
    """Satu alternatif redesain."""

    id: str = Field(description="ID alternatif (UUID v4).")
    kode: str = Field(description="Kode alternatif.", examples=["U-001"])
    masalah_id: str
    opsi: OpsiAlternatif
    alur_kini_vs_usulan: str
    pihak_asal_jabatan_id: str | None
    pihak_penerima_jabatan_id: str | None
    komitmen_penerima: str | None
    jadwal_puncak: str | None
    keterampilan_akses: str | None
    tambahan_bersih: str | None
    risiko_layanan: str | None
    gap_penerima: YaTidak
    status_telaah: StatusTelaahAlternatif
    pemutus_kode_orang: str | None
    keputusan: str | None
    prasyarat_monitoring: str | None
    catatan_versi_bukti: str | None
    created_at: datetime
    updated_at: datetime


POLA_PERIODE = r"^\d{4}/\d{2}$"
"""Pola periode kesiapan, mis. `2026/27` (selaras `narasi_kasus.periode`)."""


class StatusKesiapan(StrEnum):
    """Status kesiapan satu penerima pada satu periode."""

    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    HOLD = "HOLD"


class EstimasiDelta(StrEnum):
    """Apakah delta beban dapat diperkirakan; `NOT_ESTIMABLE` bukan nol."""

    ESTIMATED = "ESTIMATED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class PenerimaCreate(BaseModel):
    """Payload penambahan penerima pada alternatif (RecipientAssignment)."""

    model_config = ConfigDict(extra="forbid")

    penerima_jabatan_id: str = Field(
        min_length=1, max_length=40, description="ID jabatan penerima (bukan orang)."
    )
    material: bool = Field(
        default=True, description="Penerima material: belum siap menahan seluruh opsi (HOLD)."
    )
    catatan: str | None = None


class PenerimaRead(BaseModel):
    """Satu penerima alternatif."""

    id: str = Field(description="ID penerima alternatif (RecipientAssignment_ID, UUID v4).")
    alternatif_id: str
    penerima_jabatan_id: str
    material: bool
    catatan: str | None
    created_at: datetime


class KesiapanCreate(BaseModel):
    """Payload penilaian kesiapan (append-only; koreksi = penilaian baru).

    Satuan delta: jam kerja efektif per periode, positif = beban bertambah. Untuk tiap sisi,
    `NOT_ESTIMABLE` mewajibkan nilai `null`, dan `ESTIMATED` mewajibkan nilai berisi.
    """

    model_config = ConfigDict(extra="forbid")

    penerima_id: str = Field(min_length=1, max_length=36)
    periode: str = Field(pattern=POLA_PERIODE, max_length=20, examples=["2026/27"])
    status: StatusKesiapan
    delta_asal_jam: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    delta_asal_estimasi: EstimasiDelta = EstimasiDelta.ESTIMATED
    delta_penerima_jam: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    delta_penerima_estimasi: EstimasiDelta = EstimasiDelta.ESTIMATED
    delta_organisasi_jam: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    delta_organisasi_estimasi: EstimasiDelta = EstimasiDelta.ESTIMATED
    syarat: str | None = Field(default=None, description="Wajib bila status CONDITIONAL.")
    alasan_hold: str | None = Field(default=None, description="Wajib bila status HOLD.")

    @model_validator(mode="after")
    def _periksa_aturan(self) -> Self:
        """Tegakkan NOT_ESTIMABLE <=> null per sisi, serta syarat/alasan_hold menurut status."""
        for sisi in ("asal", "penerima", "organisasi"):
            nilai = getattr(self, f"delta_{sisi}_jam")
            tak_terestimasi = getattr(self, f"delta_{sisi}_estimasi") == EstimasiDelta.NOT_ESTIMABLE
            if tak_terestimasi and nilai is not None:
                raise ValueError(
                    f"delta_{sisi}_jam harus null bila delta_{sisi}_estimasi NOT_ESTIMABLE."
                )
            if not tak_terestimasi and nilai is None:
                raise ValueError(
                    f"delta_{sisi}_jam wajib diisi bila delta_{sisi}_estimasi ESTIMATED."
                )
        if self.status == StatusKesiapan.CONDITIONAL and not (self.syarat or "").strip():
            raise ValueError("syarat wajib diisi bila status CONDITIONAL.")
        if self.status == StatusKesiapan.HOLD and not (self.alasan_hold or "").strip():
            raise ValueError("alasan_hold wajib diisi bila status HOLD.")
        return self


class KesiapanRead(BaseModel):
    """Satu penilaian kesiapan tersimpan."""

    id: str
    penerima_id: str
    periode: str
    status: StatusKesiapan
    delta_asal_jam: Decimal | None
    delta_asal_estimasi: EstimasiDelta
    delta_penerima_jam: Decimal | None
    delta_penerima_estimasi: EstimasiDelta
    delta_organisasi_jam: Decimal | None
    delta_organisasi_estimasi: EstimasiDelta
    syarat: str | None
    alasan_hold: str | None
    dinilai_oleh: str = Field(description="Kode orang pemberi penilaian.")
    created_at: datetime


class KesiapanBaris(BaseModel):
    """Satu baris matriks: penerima beserta penilaian TERAKHIR pada periode yang diminta."""

    penerima_id: str
    penerima_jabatan_id: str
    material: bool
    status: StatusKesiapan | None = Field(description="Null bila belum dinilai pada periode ini.")
    delta_asal_jam: Decimal | None
    delta_asal_estimasi: EstimasiDelta | None
    delta_penerima_jam: Decimal | None
    delta_penerima_estimasi: EstimasiDelta | None
    delta_organisasi_jam: Decimal | None
    delta_organisasi_estimasi: EstimasiDelta | None
    syarat: str | None
    alasan_hold: str | None
    dinilai_pada: datetime | None


class KesiapanMatriksRead(BaseModel):
    """Matriks kesiapan satu alternatif pada satu periode beserta status opsinya."""

    alternatif_id: str
    periode: str
    status_opsi: StatusKesiapan = Field(
        description="HOLD bila ada penerima material HOLD/belum dinilai atau tanpa penerima."
    )
    baris: list[KesiapanBaris]


class KeputusanPerubahan(StrEnum):
    """Keputusan perubahan (ChangeDecision), terpisah dari keputusan prioritas."""

    APPROVE = "APPROVE"
    CONDITIONAL = "CONDITIONAL"
    HOLD = "HOLD"
    REJECT = "REJECT"


class KeputusanPerubahanCreate(BaseModel):
    """Payload keputusan perubahan per alternatif per periode (append-only).

    `stop_rule` wajib berisi bila `keputusan` CONDITIONAL; pilot bersyarat harus reversibel.
    """

    model_config = ConfigDict(extra="forbid")

    periode: str = Field(pattern=POLA_PERIODE, max_length=20, examples=["2026/27"])
    keputusan: KeputusanPerubahan
    alasan: str = Field(min_length=5, description="Alasan keputusan, minimal 5 karakter.")
    stop_rule: str | None = Field(default=None, description="Wajib bila CONDITIONAL.")

    @model_validator(mode="after")
    def _periksa_aturan(self) -> Self:
        """Tegakkan alasan tidak kosong (setelah strip) dan `stop_rule` wajib bila CONDITIONAL."""
        if len(self.alasan.strip()) < 5:
            raise ValueError("alasan minimal 5 karakter (tanpa spasi tepi).")
        if self.keputusan == KeputusanPerubahan.CONDITIONAL and not (self.stop_rule or "").strip():
            raise ValueError("stop_rule wajib diisi bila keputusan CONDITIONAL.")
        return self


class KeputusanPerubahanRead(BaseModel):
    """Satu keputusan perubahan tersimpan."""

    id: str
    alternatif_id: str
    periode: str
    keputusan: KeputusanPerubahan
    alasan: str
    stop_rule: str | None
    status_opsi_saat_putus: StatusKesiapan = Field(
        description="Salinan `status_opsi` matriks kesiapan saat keputusan dicatat."
    )
    pemutus_kode_orang: str = Field(description="Kode orang pemutus.")
    created_at: datetime
