"""Implementasi `AiUsulanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from ..ai.gateway import AiGateway
from ..ai.redaksi import SumberAi
from ..config import Settings
from ..errors import NotFoundError
from ..fitur import FiturNonaktifError, ai_boleh_jalan
from ..models import AiUsulanModel, AiUsulanPutusanModel
from ..schemas.ai_usulan import (
    AiUsulanPutusanCreate,
    AiUsulanPutusanRead,
    AiUsulanPutusanRingkas,
    AiUsulanPutusanTerakhir,
    AiUsulanRead,
    AiUsulanRingkas,
    HasilSerapUsulan,
    PutusanUsulan,
    SasaranUsulan,
)
from ..schemas.common import FiturKode
from ..schemas.search import Domain, Order
from ..security import Principal
from .ai_usulan import (
    SEARCHABLE_FIELDS,
    FungsiAiBelumAktifError,
    PiiModeAiBelumDidukungError,
    UsulanBelumBisaDiputusError,
    UsulanBelumDiterimaError,
    UsulanBerjalanError,
)
from .domain import validate_searchable_fields
from .domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns

__all__ = ["AWALAN_SUMBER_USULAN", "JENIS_SUMBER_USULAN_AI", "SqlAiUsulanService"]

JENIS_SUMBER_USULAN_AI = "USULAN_AI"
"""Jenis sumber untuk usulan AI yang dirangkai menjadi masukan fungsi lain. Baru boleh dikirim
ke model bila operator mencantumkannya di ``AI_JENIS_SUMBER_DIIZINKAN``."""

AWALAN_SUMBER_USULAN = "usulan:"
"""Awalan ``source_id`` sumber rangkaian: ``usulan:<ai_usulan.id>``."""


def _field_map() -> FieldMap:
    m = AiUsulanModel
    return {
        "fungsi": FieldSpec(column=m.fungsi),
        "sasaran_jenis": FieldSpec(column=m.sasaran_jenis),
        "sasaran_id": FieldSpec(column=m.sasaran_id),
        "hasil_serap": FieldSpec(column=m.hasil_serap),
        "created_at": FieldSpec(column=m.created_at),
    }


_BISA_DIPUTUS = frozenset(
    {HasilSerapUsulan.USULAN_DIBUAT.value, HasilSerapUsulan.EVIDENCE_GAP.value}
)
"""Nilai `hasil_serap` yang boleh diputus; `MANUAL` dan belum diserap tidak."""


def _sekarang() -> datetime:
    """Waktu putusan (UTC aware); dipisah agar tes dapat membekukan jam."""
    return datetime.now(UTC)


def _tanpa_isi() -> tuple[Any, ...]:
    """Opsi muat: kolom keluaran model tidak ikut dibaca pada daftar/pencarian."""
    return (
        defer(AiUsulanModel.isi),
        defer(AiUsulanModel.amplop),
        defer(AiUsulanModel.output_hash),
    )


class SqlAiUsulanService:
    """`AiUsulanService` berbasis PostgreSQL; terikat satu `Session`.

    Hanya menulis `ai_usulan` (dan, lewat gateway, `ai_run`/`async_job`); tidak pernah
    menyentuh tabel `narasi_*`. Pemilik sesi yang melakukan commit.
    """

    def __init__(self, session: Session, settings: Settings, gateway: AiGateway) -> None:
        """Siapkan layanan.

        Args:
            session: Sesi basis data.
            settings: Pengaturan aplikasi.
            gateway: Gateway pengajuan job AI di atas sesi yang sama.
        """
        self._s = session
        self._settings = settings
        self._gateway = gateway

    def ajukan(
        self,
        fungsi: str,
        sasaran_jenis: SasaranUsulan,
        sasaran_id: str,
        sumber: list[SumberAi],
        parameter: dict[str, Any],
        principal: Principal,
    ) -> AiUsulanRingkas:
        """Ajukan fungsi AI atas satu sasaran lalu catat usulannya.

        Urutan periksa mengikat, tidak ada baris ditulis sebelum semuanya lolos: flag/saklar
        AI, mode PII, usulan berjalan, lalu pengajuan lewat gateway.

        Args:
            fungsi: Kode fungsi terdaftar.
            sasaran_jenis: Jenis objek sasaran.
            sasaran_id: Id objek sasaran.
            sumber: Sumber data calon masukan model.
            parameter: Parameter fungsi (tanpa PII).
            principal: Pemohon; `subject` dicatat sebagai `diminta_oleh`.

        Returns:
            Proyeksi usulan yang baru dicatat (belum diserap).

        Raises:
            FiturNonaktifError: flag atau saklar AI mati (409 `feature_disabled`).
            PiiModeAiBelumDidukungError: `AI_PII_MODE` bukan `BLOKIR` (409).
            UsulanBerjalanError: usulan `fungsi` + `sasaran_id` sama belum diserap (409).
            FungsiAiBelumAktifError: fungsi belum terdaftar (409).
        """
        if not ai_boleh_jalan(self._s, self._settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        if self._settings.ai_pii_mode != "BLOKIR":
            raise PiiModeAiBelumDidukungError("Hanya AI_PII_MODE=BLOKIR yang didukung.")
        berjalan = self._s.scalar(
            select(AiUsulanModel.id)
            .where(
                AiUsulanModel.fungsi == fungsi,
                AiUsulanModel.sasaran_id == sasaran_id,
                AiUsulanModel.diserap_at.is_(None),
            )
            .limit(1)
        )
        if berjalan is not None:
            raise UsulanBerjalanError("Sasaran ini masih punya usulan AI yang belum diserap.")
        try:
            job = self._gateway.ajukan(fungsi, sumber, parameter, None, principal.subject)
        except NotFoundError as exc:
            raise FungsiAiBelumAktifError(f"Fungsi AI {fungsi} belum diaktifkan.") from exc
        if not job.ref_id:
            raise RuntimeError("Job AI tanpa ref_id run.")
        rec = AiUsulanModel(
            id=str(uuid.uuid4()),
            fungsi=fungsi,
            sasaran_jenis=sasaran_jenis.value,
            sasaran_id=sasaran_id,
            job_id=job.id,
            ai_run_id=job.ref_id,
            sumber_ids=[s.source_id for s in sumber],
            diminta_oleh=principal.subject,
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return AiUsulanRingkas.model_validate(rec)

    def putuskan(
        self, usulan_id: str, data: AiUsulanPutusanCreate, actor_key: str
    ) -> AiUsulanPutusanRead:
        """Tambah satu baris `ai_usulan_putusan`; tidak mengubah usulan maupun tabel `narasi_*`.

        Baris usulan dikunci (`FOR UPDATE`) agar putusan serentak atas usulan yang sama
        berurutan, lalu `created_at` dipaksa naik ketat (minimal satu mikrodetik di atas
        putusan sebelumnya) sehingga "putusan terbaru" tidak pernah bergantung pada jam
        yang bernilai sama dalam satu transaksi.

        Args:
            usulan_id: Id usulan yang diputus.
            data: Putusan tervalidasi (kombinasi sudah diperiksa skema).
            actor_key: Subjek reviewer dari token; aktor pada body tidak dipakai.

        Returns:
            Putusan yang baru dicatat.

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBelumBisaDiputusError: belum diserap atau `hasil_serap` bukan
                `USULAN_DIBUAT`/`EVIDENCE_GAP` (409).
        """
        rec = self._s.scalar(
            select(AiUsulanModel).where(AiUsulanModel.id == usulan_id).with_for_update()
        )
        if rec is None:
            raise NotFoundError(f"Usulan AI '{usulan_id}' tidak ditemukan.")
        if rec.diserap_at is None or rec.hasil_serap not in _BISA_DIPUTUS:
            raise UsulanBelumBisaDiputusError("Usulan ini belum bisa diputus.")
        P = AiUsulanPutusanModel
        terakhir = self._s.scalar(select(func.max(P.created_at)).where(P.usulan_id == usulan_id))
        waktu = _sekarang()
        if terakhir is not None and waktu <= terakhir:
            waktu = terakhir + timedelta(microseconds=1)
        putusan = P(
            id=str(uuid.uuid4()),
            usulan_id=usulan_id,
            putusan=data.putusan.value,
            tingkat_koreksi=data.tingkat_koreksi.value if data.tingkat_koreksi else None,
            catatan=data.catatan,
            teks_koreksi=data.teks_koreksi,
            actor_key=actor_key,
            created_at=waktu,
        )
        self._s.add(putusan)
        self._s.flush()
        return AiUsulanPutusanRead.model_validate(putusan)

    def sumber_dari_usulan(self, usulan_id: str) -> SumberAi:
        """Bungkus usulan yang sudah diterima reviewer sebagai sumber fungsi AI lain.

        Hanya putusan TERAKHIR yang menentukan (urut `created_at`, lalu `id`). `APPROVE`
        memakai JSON kanonik `isi` (kunci terurut, `ensure_ascii=False`, tanpa spasi pemisah);
        `REVISE` memakai `teks_koreksi` reviewer apa adanya. Hasilnya tetap melewati gerbang
        jenis dan PII gateway seperti sumber lain; helper ini tidak melonggarkannya.

        Args:
            usulan_id: Id usulan yang dirangkai.

        Returns:
            Sumber berjenis `USULAN_AI` dengan `source_id` `usulan:<id>` dan `source_hash`
            SHA-256 teksnya.

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBelumDiterimaError: tanpa putusan, putusan terakhir `REJECT`, atau `APPROVE`
                atas usulan tanpa `isi` (409 `USULAN_BELUM_DITERIMA`).
        """
        rec = self._s.get(AiUsulanModel, usulan_id)
        if rec is None:
            raise NotFoundError(f"Usulan AI '{usulan_id}' tidak ditemukan.")
        P = AiUsulanPutusanModel
        terakhir = self._s.scalars(
            select(P).where(P.usulan_id == usulan_id).order_by(P.created_at.desc(), P.id.desc())
        ).first()
        teks: str | None = None
        if terakhir is not None and terakhir.putusan == PutusanUsulan.APPROVE.value:
            if rec.isi is not None:
                teks = json.dumps(
                    rec.isi, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
        elif terakhir is not None and terakhir.putusan == PutusanUsulan.REVISE.value:
            teks = terakhir.teks_koreksi
        if not teks:
            raise UsulanBelumDiterimaError("Usulan AI ini belum diterima reviewer.")
        return SumberAi(
            source_id=f"{AWALAN_SUMBER_USULAN}{rec.id}",
            source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
            jenis=JENIS_SUMBER_USULAN_AI,
            teks=teks,
        )

    def _putusan_terakhir(self, usulan_ids: Sequence[str]) -> dict[str, AiUsulanPutusanRingkas]:
        """Putusan terbaru per usulan dalam SATU kueri (`DISTINCT ON`), untuk daftar dan pencarian.

        Kolom `catatan`, `teks_koreksi`, dan `actor_key` tidak dipilih dari basis data;
        `actor_key` hanya keluar lewat `get` (`AiUsulanPutusanTerakhir`).
        """
        if not usulan_ids:
            return {}
        P = AiUsulanPutusanModel
        rows = self._s.execute(
            select(P.usulan_id, P.id, P.putusan, P.tingkat_koreksi, P.created_at)
            .where(P.usulan_id.in_(usulan_ids))
            .distinct(P.usulan_id)
            .order_by(P.usulan_id, P.created_at.desc(), P.id.desc())
        ).all()
        return {
            r.usulan_id: AiUsulanPutusanRingkas(
                id=r.id,
                putusan=r.putusan,
                tingkat_koreksi=r.tingkat_koreksi,
                created_at=r.created_at,
            )
            for r in rows
        }

    def _ringkas(self, rows: Sequence[AiUsulanModel]) -> list[AiUsulanRingkas]:
        """Proyeksi ringkas halaman ini dengan `putusan_terakhir` (satu kueri tambahan)."""
        terakhir = self._putusan_terakhir([r.id for r in rows])
        return [
            AiUsulanRingkas.model_validate(r).model_copy(
                update={"putusan_terakhir": terakhir.get(r.id)}
            )
            for r in rows
        ]

    def get(self, usulan_id: str) -> AiUsulanRead:
        """Ambil satu usulan lengkap dengan `isi`, `amplop`, dan `output_hash`.

        Args:
            usulan_id: Id usulan.

        Returns:
            Usulan lengkap.

        Raises:
            NotFoundError: usulan tidak ada (404).
        """
        rec = self._s.get(AiUsulanModel, usulan_id)
        if rec is None:
            raise NotFoundError(f"Usulan AI '{usulan_id}' tidak ditemukan.")
        P = AiUsulanPutusanModel
        daftar = self._s.scalars(
            select(P).where(P.usulan_id == usulan_id).order_by(P.created_at, P.id)
        ).all()
        putusan = [AiUsulanPutusanRead.model_validate(p) for p in daftar]
        return AiUsulanRead.model_validate(rec).model_copy(
            update={
                "putusan": putusan,
                "putusan_terakhir": (
                    AiUsulanPutusanTerakhir.model_validate(daftar[-1]) if daftar else None
                ),
            }
        )

    def list(
        self,
        *,
        fungsi: str | None,
        sasaran_jenis: str | None,
        sasaran_id: str | None,
        hasil_serap: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Daftar ringkas terbaru dulu; paging dan filter dijalankan di SQL.

        Args:
            fungsi: Filter kode fungsi.
            sasaran_jenis: Filter jenis sasaran.
            sasaran_id: Filter id sasaran.
            hasil_serap: Filter hasil serap.
            limit: Ukuran halaman.
            offset: Geser halaman.

        Returns:
            Pasangan (baris tanpa `isi`/`amplop`, total sebelum paging).
        """
        m = AiUsulanModel
        conds = []
        for kolom, nilai in (
            (m.fungsi, fungsi),
            (m.sasaran_jenis, sasaran_jenis),
            (m.sasaran_id, sasaran_id),
            (m.hasil_serap, hasil_serap),
        ):
            if nilai is not None:
                conds.append(kolom == nilai)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m)
            .options(*_tanpa_isi())
            .where(*conds)
            .order_by(m.created_at.desc(), m.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return self._ringkas(rows), total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Cari memakai domain ala Odoo; field di-whitelist, nilai bound parameter.

        Args:
            domain: Domain pencarian.
            order: Urutan.
            limit: Ukuran halaman.
            offset: Geser halaman.

        Returns:
            Pasangan (baris tanpa `isi`/`amplop`, total).

        Raises:
            ValidationAppError: field di luar `SEARCHABLE_FIELDS` atau domain tak sah (422).
        """
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = AiUsulanModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.created_at.desc(), m.id]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m)
            .options(*_tanpa_isi())
            .where(cond)
            .order_by(*order_cols)
            .limit(limit)
            .offset(offset)
        ).all()
        return self._ringkas(rows), total
