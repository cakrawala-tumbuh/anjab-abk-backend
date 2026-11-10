"""Implementasi `KonteksService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.errors import UniqueViolation
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import AiUsulanModel, AiUsulanPutusanModel, RedesainKonteksModel
from ...schemas.ai_usulan import PutusanUsulan, SasaranUsulan
from ...schemas.search import Domain, Order
from ...services.ai_usulan import UsulanBelumDiterimaError
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate, TerapkanKonteks
from .konteks import (
    SEARCHABLE_FIELDS,
    IsianRevisiWajibError,
    KandidatSudahDiterapkanError,
    KandidatTakAdaError,
    UsulanBukanP11Error,
)
from .riwayat import RiwayatService

ENTITAS = "konteks"

KODE_FUNGSI_P11 = "P11"
"""Kode fungsi AI yang kandidatnya boleh diterapkan (literal agar redesain tak mengimpor `ai`)."""

ISIAN_KANDIDAT = ("tema", "ruang_dugaan", "sumber_draft", "batas_pemeriksaan")
"""Isian teks yang disalin dari kandidat P11 (atau ditimpa body) ke konteks baru."""

_UQ_KANDIDAT = "uq_redesain_konteks_ai_usulan_kandidat"

_KOLOM_EDIT = (
    "tema",
    "gelombang",
    "ruang_dugaan",
    "sumber_draft",
    "batas_pemeriksaan",
    "aktif",
)


def _field_map() -> FieldMap:
    m = RedesainKonteksModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "tema": FieldSpec(column=m.tema),
        "gelombang": FieldSpec(column=m.gelombang),
        "aktif": FieldSpec(column=m.aktif),
        "ai_usulan_id": FieldSpec(column=m.ai_usulan_id),
        "created_at": FieldSpec(column=m.created_at, order_column=m.created_at),
        "updated_at": FieldSpec(column=m.updated_at, order_column=m.updated_at),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainKonteksModel) -> KonteksRead:
    return KonteksRead(
        id=rec.id,
        kode=rec.kode,
        tema=rec.tema,
        gelombang=rec.gelombang,  # type: ignore[arg-type]
        ruang_dugaan=rec.ruang_dugaan,
        sumber_draft=rec.sumber_draft,
        batas_pemeriksaan=rec.batas_pemeriksaan,
        aktif=rec.aktif,
        ai_usulan_id=rec.ai_usulan_id,
        ai_kandidat_indeks=rec.ai_kandidat_indeks,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
    )


def snapshot(r: KonteksRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah konteks untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Konteks hasil baca.

    Returns:
        Dict kolom bisnis (tanpa id dan cap waktu).
    """
    return {"kode": r.kode, **{k: getattr(r, k) for k in _KOLOM_EDIT}}


class SqlKonteksService:
    """`KonteksService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def create(self, data: KonteksCreate, *, pelaku_kode_orang: str | None) -> KonteksRead:
        """Buat konteks baru dan catat riwayat.

        Raises:
            ConflictError: `kode` sudah dipakai.
        """
        m = RedesainKonteksModel
        if self._s.scalars(select(m.id).where(m.kode == data.kode)).first() is not None:
            raise ConflictError(f"Konteks '{data.kode}' sudah ada.")
        rec = m(id=str(uuid.uuid4()), **data.model_dump())
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, konteks_id: str) -> RedesainKonteksModel:
        rec = self._s.get(RedesainKonteksModel, konteks_id)
        if rec is None:
            raise NotFoundError(f"Konteks '{konteks_id}' tidak ditemukan.")
        return rec

    def get(self, konteks_id: str) -> KonteksRead:
        """Ambil satu konteks; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(konteks_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[KonteksRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainKonteksModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonteksRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainKonteksModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, konteks_id: str, data: KonteksUpdate, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Ubah parsial konteks (hanya field yang dikirim) dan catat riwayat.

        Raises:
            NotFoundError: Konteks tidak ada.
        """
        rec = self._get_model(konteks_id)
        sebelum = snapshot(_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is not None:
                setattr(rec, nama, nilai)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read

    def terapkan_usulan(
        self, usulan_id: str, data: TerapkanKonteks, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Buat SATU konteks baru dari kandidat usulan P11 yang sudah diterima reviewer.

        Satu transaksi (sesi request): baris `ai_usulan` dibaca `FOR SHARE`, putusan terakhir
        (urut `created_at` lalu `id`, sama dengan `sumber_dari_usulan`) menentukan penerimaan.
        Isian kandidat `indeks_kandidat` disalin; field body yang terisi menimpa. Hasil gabungan
        divalidasi ulang lewat `KonteksCreate` (mis. `tema` > 200 atau isian kosong -> 422).
        Konteks dibuat `aktif=true` dengan `ai_usulan_id`/`ai_kandidat_indeks`, dan riwayat
        `create` dicatat seperti `create` biasa. Usulan dan putusannya tidak diubah.

        Args:
            usulan_id: Id usulan P11 sumber kandidat.
            data: Body aksi (indeks kandidat, kode, gelombang, penimpa isian).
            pelaku_kode_orang: Kode orang pemanggil untuk riwayat.

        Returns:
            Konteks baru.

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBukanP11Error: fungsi bukan P11 / sasaran bukan `REDESAIN_KONTEKS` (422).
            UsulanBelumDiterimaError: tanpa putusan atau putusan terakhir `REJECT` (409).
            KandidatTakAdaError: `isi` null atau indeks di luar rentang (422).
            IsianRevisiWajibError: putusan terakhir `REVISE` tanpa keempat isian (422).
            KandidatSudahDiterapkanError: kandidat sudah menjadi konteks (409), termasuk
                bentrok UNIQUE dari permintaan bersamaan.
            ConflictError: `kode` sudah dipakai konteks lain (409 `conflict`).
            ValidationAppError: isian gabungan tidak lolos `KonteksCreate` (422).
        """
        usulan = self._s.scalar(
            select(AiUsulanModel).where(AiUsulanModel.id == usulan_id).with_for_update(read=True)
        )
        if usulan is None:
            raise NotFoundError(f"Usulan AI '{usulan_id}' tidak ditemukan.")
        if (
            usulan.fungsi != KODE_FUNGSI_P11
            or usulan.sasaran_jenis != SasaranUsulan.REDESAIN_KONTEKS.value
        ):
            raise UsulanBukanP11Error("Usulan bukan usulan P11 untuk katalog konteks.")
        P = AiUsulanPutusanModel
        putusan = self._s.scalar(
            select(P.putusan)
            .where(P.usulan_id == usulan_id)
            .order_by(P.created_at.desc(), P.id.desc())
            .limit(1)
        )
        if putusan not in (PutusanUsulan.APPROVE.value, PutusanUsulan.REVISE.value):
            raise UsulanBelumDiterimaError("Usulan AI ini belum diterima reviewer.")
        kandidat = _kandidat(usulan.isi, data.indeks_kandidat)
        dikirim = {nama: getattr(data, nama) for nama in ISIAN_KANDIDAT}
        if putusan == PutusanUsulan.REVISE.value and any(v is None for v in dikirim.values()):
            raise IsianRevisiWajibError(
                "Putusan terakhir REVISE: tema, ruang_dugaan, sumber_draft, dan "
                "batas_pemeriksaan wajib dikirim."
            )
        m = RedesainKonteksModel
        ada = self._s.scalar(
            select(m.id).where(
                m.ai_usulan_id == usulan_id, m.ai_kandidat_indeks == data.indeks_kandidat
            )
        )
        if ada is not None:
            raise KandidatSudahDiterapkanError(ada)
        try:
            baru = KonteksCreate(
                kode=data.kode,
                gelombang=data.gelombang,
                aktif=True,
                **{
                    nama: dikirim[nama] if dikirim[nama] is not None else kandidat.get(nama)
                    for nama in ISIAN_KANDIDAT
                },
            )
        except ValidationError as exc:
            salah = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
            raise ValidationAppError(
                "Isian kandidat tidak sah untuk konteks: " + ", ".join(salah) + "."
            ) from exc
        if self._s.scalars(select(m.id).where(m.kode == baru.kode)).first() is not None:
            raise ConflictError(f"Konteks '{baru.kode}' sudah ada.")
        rec = m(
            id=str(uuid.uuid4()),
            **baru.model_dump(),
            ai_usulan_id=usulan_id,
            ai_kandidat_indeks=data.indeks_kandidat,
        )
        try:
            with self._s.begin_nested():
                self._s.add(rec)
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                if getattr(exc.orig.diag, "constraint_name", None) == _UQ_KANDIDAT:
                    raise KandidatSudahDiterapkanError(None) from exc
                raise ConflictError(f"Konteks '{baru.kode}' sudah ada.") from exc
            raise
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read


def _kandidat(isi: dict[str, Any] | None, indeks: int) -> dict[str, Any]:
    """Ambil kandidat ke-`indeks` dari `isi.konteks_candidates` usulan P11.

    Raises:
        KandidatTakAdaError: `isi` null, `konteks_candidates` bukan daftar, indeks di luar
            rentang, atau entri bukan objek.
    """
    daftar = (isi or {}).get("konteks_candidates")
    if not isinstance(daftar, list) or not 0 <= indeks < len(daftar):
        raise KandidatTakAdaError(f"Kandidat indeks {indeks} tidak ada pada usulan ini.")
    kandidat = daftar[indeks]
    if not isinstance(kandidat, dict):
        raise KandidatTakAdaError(f"Kandidat indeks {indeks} tidak ada pada usulan ini.")
    return kandidat
