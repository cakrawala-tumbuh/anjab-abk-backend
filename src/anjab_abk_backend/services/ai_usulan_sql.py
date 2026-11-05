"""Implementasi `AiUsulanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from ..ai.gateway import AiGateway
from ..ai.redaksi import SumberAi
from ..config import Settings
from ..errors import NotFoundError
from ..fitur import FiturNonaktifError, ai_boleh_jalan
from ..models import AiUsulanModel
from ..schemas.ai_usulan import AiUsulanRead, AiUsulanRingkas, SasaranUsulan
from ..schemas.common import FiturKode
from ..schemas.search import Domain, Order
from ..security import Principal
from .ai_usulan import (
    SEARCHABLE_FIELDS,
    FungsiAiBelumAktifError,
    PiiModeAiBelumDidukungError,
    UsulanBerjalanError,
)
from .domain import validate_searchable_fields
from .domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns

__all__ = ["SqlAiUsulanService"]


def _field_map() -> FieldMap:
    m = AiUsulanModel
    return {
        "fungsi": FieldSpec(column=m.fungsi),
        "sasaran_jenis": FieldSpec(column=m.sasaran_jenis),
        "sasaran_id": FieldSpec(column=m.sasaran_id),
        "hasil_serap": FieldSpec(column=m.hasil_serap),
        "created_at": FieldSpec(column=m.created_at),
    }


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
        return AiUsulanRead.model_validate(rec)

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
        return [AiUsulanRingkas.model_validate(r) for r in rows], total

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
        return [AiUsulanRingkas.model_validate(r) for r in rows], total
