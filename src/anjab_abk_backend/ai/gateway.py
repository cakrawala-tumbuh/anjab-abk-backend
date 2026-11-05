"""Gateway pengajuan job AI: gerbang masukan, register run, lalu antrean job.

Alur ``AiGateway.ajukan``: saklar/flag -> gerbang PII per sumber -> ``ai_run`` ->
``async_job``. Gateway TIDAK memanggil model; itu tugas worker (``ai/worker.py``).
Satu-satunya tabel yang ditulis adalah ``ai_run`` dan ``async_job``. Registri
fungsi produksi sengaja kosong, sehingga belum ada pemanggil yang sah.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import NotFoundError
from ..fitur import FiturNonaktifError, ai_boleh_jalan
from ..schemas.ai_run import AiSumber, StatusQaAi
from ..schemas.async_job import AsyncJobRead, StatusJob
from ..schemas.common import FiturKode
from ..services.ai_penyedia_sql import SqlAiPenyediaService
from ..services.ai_run import AiRunService
from ..services.ai_run_sql import SqlAiRunService
from ..services.async_job import AsyncJobService
from ..services.async_job_sql import SqlAsyncJobService
from .guardrail import hash_instruksi, susun_prompt_version
from .penyedia import AiPenyediaMode
from .redaksi import SumberAi, gerbang_masukan, muat_kamus_nama, periksa_pii

__all__ = [
    "FUNGSI_TERDAFTAR",
    "FITUR_AI",
    "AiGateway",
    "FungsiAi",
    "ambil_fungsi",
]

FITUR_AI = FiturKode.AI_NARRATIVE_DRAFT
"""Flag fitur yang menggerbang seluruh job AI."""

_ALASAN_EVIDENCE_GAP = frozenset({"SUMBER_KOSONG", "METADATA_SUMBER_HILANG"})


@dataclass(frozen=True)
class FungsiAi:
    """Definisi satu fungsi AI.

    Attributes:
        kode: Kode unik fungsi (juga ``async_job.jenis`` dan ``ai_run.fungsi``).
        prompt_version: Versi instruksi fungsi, mis. ``v1``.
        instruksi: Instruksi fungsi; guardrail ditambahkan di depannya.
        skema_isi: JSON Schema untuk field ``isi`` pada amplop keluaran.
    """

    kode: str
    prompt_version: str
    instruksi: str
    skema_isi: dict[str, Any]


FUNGSI_TERDAFTAR: dict[str, FungsiAi] = {}
"""Registri fungsi AI. Produksi kosong; uji menyuntik fungsi tiruan."""


def ambil_fungsi(kode: str, registri: dict[str, FungsiAi] | None = None) -> FungsiAi:
    """Cari fungsi terdaftar.

    Args:
        kode: Kode fungsi.
        registri: Registri alternatif; bawaan ``FUNGSI_TERDAFTAR``.

    Returns:
        ``FungsiAi`` terkait.

    Raises:
        NotFoundError: kode tidak terdaftar (404).
    """
    reg = FUNGSI_TERDAFTAR if registri is None else registri
    fungsi = reg.get(kode)
    if fungsi is None:
        raise NotFoundError(f"Fungsi AI '{kode}' tidak terdaftar.")
    return fungsi


class AiGateway:
    """Mengajukan job AI melalui gerbang masukan dan register run.

    Satu instance dipakai di atas satu ``Session``; gateway hanya ``flush``,
    commit dilakukan pemilik sesi.
    """

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        jobs: AsyncJobService | None = None,
        runs: AiRunService | None = None,
        registri: dict[str, FungsiAi] | None = None,
    ) -> None:
        """Siapkan gateway.

        Args:
            session: Sesi basis data.
            settings: Pengaturan aplikasi.
            jobs: Service job; bawaan ``SqlAsyncJobService``.
            runs: Service register run; bawaan ``SqlAiRunService``.
            registri: Registri fungsi; bawaan ``FUNGSI_TERDAFTAR``.
        """
        self._s = session
        self._settings = settings
        self._jobs = jobs or SqlAsyncJobService(session, settings)
        self._runs = runs or SqlAiRunService(session, settings)
        self._registri = registri

    def ajukan(
        self,
        kode_fungsi: str,
        sumber: list[SumberAi],
        parameter: dict[str, Any],
        ref_id: str | None,
        dibuat_oleh: str | None,
    ) -> AsyncJobRead:
        """Ajukan satu job AI.

        Gerbang dijalankan per sumber sesuai urutan daftar; sumber pertama yang
        ditolak menentukan alasan seluruh pengajuan (fail closed). Daftar kosong
        menjadi ``SUMBER_KOSONG``. ``SUMBER_KOSONG`` dan ``METADATA_SUMBER_HILANG``
        menghasilkan run ``EVIDENCE_GAP``; alasan lain (termasuk PII pada
        ``parameter``) run ``DIBLOKIR``. Keduanya berakhir job ``MANUAL_REVIEW``
        tanpa pemanggilan model. Bila lolos, run ``MENUNGGU`` memuat masukan
        tersamarkan dan job ``PENDING`` dengan ``ref_id`` = id run.

        Args:
            kode_fungsi: Kode fungsi terdaftar.
            sumber: Sumber data calon masukan model.
            parameter: Parameter fungsi (JSON-serializable, tidak boleh memuat PII).
            ref_id: Id objek sasaran; disimpan di ``masukan`` run.
            dibuat_oleh: Subjek pemicu.

        Returns:
            Job hasil pengajuan (``PENDING`` atau ``MANUAL_REVIEW``).

        Raises:
            FiturNonaktifError: flag atau saklar AI mati, atau mode penyedia ``MATI`` (409);
                tidak ada baris dibuat. Gerbang data sama untuk semua mode penyedia lainnya.
            NotFoundError: ``kode_fungsi`` tidak terdaftar (404).
        """
        if not ai_boleh_jalan(self._s, self._settings, FITUR_AI):
            raise FiturNonaktifError(FITUR_AI)
        penyedia = SqlAiPenyediaService(self._s, self._settings).status()
        if penyedia.mode is AiPenyediaMode.MATI:
            raise FiturNonaktifError(FITUR_AI)
        fungsi = ambil_fungsi(kode_fungsi, self._registri)

        kamus = muat_kamus_nama(self._s)
        alasan: str | None = None
        bersih: list[SumberAi] = []
        if not sumber:
            alasan = "SUMBER_KOSONG"
        for item in sumber:
            hasil = gerbang_masukan(item, kamus, self._settings)
            if not hasil.lolos or hasil.sumber is None:
                alasan = hasil.alasan or "SUMBER_KOSONG"
                break
            bersih.append(hasil.sumber)
        if alasan is None and periksa_pii(json.dumps(parameter, ensure_ascii=False), kamus).temuan:
            alasan = "PII_DITEMUKAN"

        rujukan = [AiSumber(source_id=s.source_id, source_hash=s.source_hash) for s in sumber]
        masukan = {
            "sumber": [
                {
                    "source_id": s.source_id,
                    "source_hash": s.source_hash,
                    "jenis": s.jenis,
                    "teks": s.teks,
                }
                for s in bersih
            ]
            if alasan is None
            else [],
            "parameter": parameter if alasan is None else {},
            "ref_id": ref_id,
        }
        run = self._runs.buka(
            fungsi.kode,
            susun_prompt_version(fungsi.prompt_version),
            hash_instruksi(fungsi.instruksi),
            penyedia.model,
            rujukan,
            masukan,
            dibuat_oleh,
            penyedia=penyedia.mode.value,
        )
        job = self._jobs.create(FITUR_AI, fungsi.kode, run.id, dibuat_oleh)
        if alasan is None:
            return job
        self._jobs.transisi(job.id, StatusJob.RUNNING)
        status = StatusQaAi.EVIDENCE_GAP if alasan in _ALASAN_EVIDENCE_GAP else StatusQaAi.DIBLOKIR
        self._runs.tutup(run.id, status, [alasan], None, None, None, None, None)
        return self._jobs.transisi(job.id, StatusJob.MANUAL_REVIEW, alasan)
