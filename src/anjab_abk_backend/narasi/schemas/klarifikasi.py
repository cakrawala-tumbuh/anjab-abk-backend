"""Skema register klarifikasi narasi (`narasi_klarifikasi`, `narasi_klarifikasi_event`).

Register memuat 13 metadata permintaan bukti Tim Kajian plus teks pertanyaan. Pertanyaan
disusun di aplikasi, dikirim fasilitator DI LUAR aplikasi, lalu jawaban mentah dicatat
dengan `response_ref`. Tidak ada skema sunting: koreksi = batalkan lalu buat baru.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATATAN_MIN = 5
"""Panjang minimum `catatan` pada penolakan dan pembatalan."""


class ReviewerApproval(StrEnum):
    """Status persetujuan reviewer atas sebuah pertanyaan klarifikasi."""

    MENUNGGU = "MENUNGGU"
    DISETUJUI = "DISETUJUI"
    DITOLAK = "DITOLAK"


class Disposition(StrEnum):
    """Nasib sebuah pertanyaan klarifikasi.

    `DITOLAK` menutup baris saat reviewer menolak (`TOLAK`); klaim yang sama lalu bebas
    diberi klarifikasi baru, dan riwayat penolakan tetap ada di `narasi_klarifikasi_event`.
    """

    TERBUKA = "TERBUKA"
    TERJAWAB = "TERJAWAB"
    DIBATALKAN = "DIBATALKAN"
    DITOLAK = "DITOLAK"


class AksiKlarifikasi(StrEnum):
    """Jenis aksi pada tabel riwayat `narasi_klarifikasi_event`."""

    DIBUAT = "DIBUAT"
    DISETUJUI = "DISETUJUI"
    DITOLAK = "DITOLAK"
    JAWABAN_DICATAT = "JAWABAN_DICATAT"
    DIBATALKAN = "DIBATALKAN"


class KeputusanReviewer(StrEnum):
    """Keputusan reviewer pada `POST /{id}/persetujuan`."""

    SETUJU = "SETUJU"
    TOLAK = "TOLAK"


class ExposureKlarifikasi(StrEnum):
    """Nilai `exposure`: himpunan `paparan` antrean tinjauan narasi."""

    TIDAK_BERLAKU = "TIDAK_BERLAKU"
    BELUM_TERPAPAR = "BELUM_TERPAPAR"
    LOCKED_PRE_EXPOSURE = "LOCKED_PRE_EXPOSURE"
    EXPOSED = "EXPOSED"
    TIDAK_DIKETAHUI = "TIDAK_DIKETAHUI"


class KlarifikasiCreate(BaseModel):
    """Payload pertanyaan klarifikasi baru (13 metadata + `question_text`).

    Status awal (`MENUNGGU`/`TERBUKA`), pembuat, dan waktu ditentukan sistem.
    """

    model_config = ConfigDict(extra="forbid")

    narasi_id: str = Field(min_length=1, max_length=36, description="ID kasus narasi.")
    claim_id: str = Field(min_length=1, max_length=100, description="Claim_ID yang ditanyakan.")
    source_ids_checked: list[str] = Field(
        min_length=1, description="Source_IDs_checked: sumber yang sudah dicek (minimal satu)."
    )
    materiality_reason: str = Field(min_length=1, description="Mengapa pertanyaan ini material.")
    alternative_hypothesis: str = Field(min_length=1, description="Hipotesis alternatif.")
    intended_decision: str = Field(min_length=1, description="Keputusan yang hendak dibantu.")
    recipient_role: str = Field(min_length=1, max_length=100, description="RecipientRole.")
    periode: str = Field(min_length=1, max_length=20, description="Period.")
    exposure: ExposureKlarifikasi = Field(description="Exposure (himpunan `paparan` antrean).")
    due_trigger: str = Field(min_length=1, description="DueTrigger: kapan jawaban dibutuhkan.")
    question_text: str = Field(
        min_length=1, description="Teks pertanyaan; paling banyak satu tanda tanya."
    )

    @field_validator("source_ids_checked")
    @classmethod
    def _sumber_tidak_kosong(cls, nilai: list[str]) -> list[str]:
        """Tolak id sumber kosong/spasi saja.

        Raises:
            ValueError: Ada elemen kosong (422).
        """
        if any(not s.strip() for s in nilai):
            raise ValueError("Id sumber tidak boleh kosong.")
        return nilai

    @field_validator(
        "claim_id",
        "materiality_reason",
        "alternative_hypothesis",
        "intended_decision",
        "recipient_role",
        "periode",
        "due_trigger",
        "question_text",
    )
    @classmethod
    def _tidak_hanya_spasi(cls, nilai: str) -> str:
        """Tolak teks yang hanya berisi spasi (nilai dikembalikan apa adanya).

        Raises:
            ValueError: Nilai kosong setelah spasi dibuang (422).
        """
        if not nilai.strip():
            raise ValueError("Tidak boleh kosong.")
        return nilai

    @field_validator("question_text")
    @classmethod
    def _satu_tanda_tanya(cls, nilai: str) -> str:
        """Pastikan pertanyaan hanya satu (paling banyak satu tanda tanya).

        Raises:
            ValueError: Ada lebih dari satu karakter `?` (422).
        """
        if nilai.count("?") > 1:
            raise ValueError("Hanya satu pertanyaan: paling banyak satu tanda tanya.")
        return nilai


class KlarifikasiDariUsulan(BaseModel):
    """Body `POST /dari-usulan/{ai_usulan_id}`: isian yang tidak berasal dari usulan P04.

    Field lain register diturunkan dari usulan dengan pemetaan tetap (lihat
    `SqlKlarifikasiService.dari_usulan`).
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100, description="Claim_ID yang ditanyakan.")
    due_trigger: str = Field(min_length=1, description="DueTrigger: kapan jawaban dibutuhkan.")
    exposure: ExposureKlarifikasi = Field(description="Exposure (himpunan `paparan` antrean).")
    intended_decision: str | None = Field(
        default=None,
        description="Keputusan yang hendak dibantu; bila kosong dipakai `why_ask` dari usulan.",
    )


class PersetujuanKlarifikasi(BaseModel):
    """Payload keputusan reviewer atas pertanyaan klarifikasi.

    `TOLAK` sekaligus menutup baris (`disposition` menjadi `DITOLAK`).
    """

    model_config = ConfigDict(extra="forbid")

    keputusan: KeputusanReviewer
    catatan: str | None = Field(default=None, description="Wajib (>= 5 karakter) bila TOLAK.")

    @model_validator(mode="after")
    def _catatan_tolak(self) -> PersetujuanKlarifikasi:
        """Wajibkan catatan berisi untuk penolakan.

        Raises:
            ValueError: `TOLAK` tanpa catatan >= `CATATAN_MIN` karakter (422).
        """
        if self.keputusan is KeputusanReviewer.TOLAK and (
            self.catatan is None or len(self.catatan.strip()) < CATATAN_MIN
        ):
            raise ValueError(f"Catatan penolakan minimal {CATATAN_MIN} karakter.")
        return self


class JawabanKlarifikasi(BaseModel):
    """Payload pencatatan jawaban mentah; keduanya wajib."""

    model_config = ConfigDict(extra="forbid")

    response_ref: str = Field(min_length=1, max_length=200, description="ResponseRef.")
    jawaban_mentah: str = Field(min_length=1, description="Jawaban apa adanya dari responden.")

    @field_validator("response_ref", "jawaban_mentah")
    @classmethod
    def _tidak_hanya_spasi(cls, nilai: str) -> str:
        """Tolak nilai yang hanya berisi spasi.

        Raises:
            ValueError: Nilai kosong setelah spasi dibuang (422).
        """
        if not nilai.strip():
            raise ValueError("Tidak boleh kosong.")
        return nilai


class BatalkanKlarifikasi(BaseModel):
    """Payload pembatalan pertanyaan yang masih `TERBUKA`."""

    model_config = ConfigDict(extra="forbid")

    catatan: str = Field(min_length=CATATAN_MIN, description="Alasan pembatalan.")


class KlarifikasiEventRead(BaseModel):
    """Satu baris riwayat append-only sebuah pertanyaan."""

    id: str
    klarifikasi_id: str
    aksi: AksiKlarifikasi
    actor_key: str
    catatan: str | None
    terjadi_pada: datetime


class KlarifikasiRead(BaseModel):
    """Satu pertanyaan klarifikasi: 13 metadata + `question_text` + status."""

    id: str = Field(description="Question_ID (UUID v4).")
    narasi_id: str
    claim_id: str
    source_ids_checked: list[str]
    materiality_reason: str
    alternative_hypothesis: str
    intended_decision: str
    recipient_role: str
    periode: str
    exposure: str
    due_trigger: str
    question_text: str
    reviewer_approval: ReviewerApproval
    response_ref: str | None
    jawaban_mentah: str | None
    disposition: Disposition
    ai_usulan_id: str | None
    dibuat_oleh: str
    created_at: datetime
    updated_at: datetime


class KlarifikasiDetail(KlarifikasiRead):
    """`KlarifikasiRead` plus riwayat aksi (terlama dulu)."""

    riwayat: list[KlarifikasiEventRead]
