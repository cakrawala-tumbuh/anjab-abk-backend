"""Implementasi `RingkasanYayasanService` di atas PostgreSQL: query gabungan, tanpa tabel baru."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import (
    RedesainKonteksModel,
    RedesainMasalahModel,
    RedesainPenilaianModel,
    RedesainProsesModel,
    SekolahModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.yayasan import RingkasanYayasanRow
from .penilaian_sql import _peringatan
from .yayasan import SEARCHABLE_FIELDS

_M = RedesainMasalahModel
_P = RedesainPenilaianModel
_K = RedesainKonteksModel


def _field_map() -> FieldMap:
    return {
        "konteks_kode": FieldSpec(column=_K.kode),
        "status_bukti": FieldSpec(column=_P.status_bukti),
        "saran_otomatis": FieldSpec(column=_P.saran_otomatis),
        "prioritas_final": FieldSpec(column=_P.prioritas_final),
        "status_penilaian": FieldSpec(column=_P.status_penilaian),
    }


def _base_select():
    """SELECT gabungan masalah LEFT JOIN penilaian, konteks, dan sekolah."""
    return (
        select(_M, _P, _K.kode, SekolahModel.nama)
        .join(_K, _K.id == _M.konteks_id)
        .outerjoin(_P, _P.masalah_id == _M.id)
        .outerjoin(SekolahModel, SekolahModel.id == _M.sekolah_id)
    )


class SqlRingkasanYayasanService:
    """`RingkasanYayasanService` berbasis PostgreSQL; read-only, satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _proses_kode(self, masalah_ids: list[str]) -> dict[str, list[str]]:
        """Kode proses per masalah (terurut) dalam satu query."""
        hasil: dict[str, list[str]] = {i: [] for i in masalah_ids}
        if not masalah_ids:
            return hasil
        pr = RedesainProsesModel
        rows = self._s.execute(
            select(pr.masalah_id, pr.kode).where(pr.masalah_id.in_(masalah_ids)).order_by(pr.kode)
        ).all()
        for masalah_id, kode in rows:
            hasil[masalah_id].append(kode)
        return hasil

    def _rows(self, rows, proses: dict[str, list[str]]) -> list[RingkasanYayasanRow]:
        out: list[RingkasanYayasanRow] = []
        for m, p, konteks_kode, nama_sekolah in rows:
            pemutus = None
            if p is not None and p.pemutus_kode_orang:
                pemutus = f"{p.pemutus_kode_orang} — {p.pemutus_jabatan or ''}".rstrip(" —")
            out.append(
                RingkasanYayasanRow(
                    masalah_id=m.id,
                    masalah_kode=m.kode,
                    konteks_kode=konteks_kode,
                    sekolah_konteks=nama_sekolah or m.keterangan_sekolah,
                    periode_acuan=m.periode_acuan,
                    rumusan_hipotesis=m.rumusan_hipotesis,
                    sumber_awal_keterbatasan=m.sumber_awal_keterbatasan,
                    status_bukti=p.status_bukti if p else None,  # type: ignore[arg-type]
                    k1=p.k1 if p else None,
                    k2=p.k2 if p else None,
                    k3=p.k3 if p else None,
                    k4=p.k4 if p else None,
                    indikasi_kritis=p.indikasi_kritis if p else None,
                    saran_otomatis=p.saran_otomatis if p else None,
                    prioritas_final=p.prioritas_final if p else None,
                    alasan_final=p.alasan_final if p else None,
                    pemutus=pemutus,
                    tindak_lanjut=p.tindak_lanjut if p else None,
                    proses_kode=proses.get(m.id, []),
                    status_penilaian=p.status_penilaian if p else None,
                    tanggal_keputusan=p.tanggal_keputusan if p else None,
                    diluruskan_sekolah=p.diluruskan_sekolah if p else None,
                    alasan_rentang_beda=p.alasan_rentang_beda if p else None,
                    peringatan=_peringatan(p) if p else [],
                )
            )
        return out

    def _page(self, cond, order_cols, limit: int, offset: int):
        stmt = _base_select()
        count = select(func.count()).select_from(_M).join(_K, _K.id == _M.konteks_id)
        count = count.outerjoin(_P, _P.masalah_id == _M.id)
        if cond is not None:
            stmt = stmt.where(cond)
            count = count.where(cond)
        total = self._s.scalar(count) or 0
        rows = self._s.execute(stmt.order_by(*order_cols).limit(limit).offset(offset)).all()
        proses = self._proses_kode([r[0].id for r in rows])
        return self._rows(rows, proses), total

    def list(self, *, limit: int, offset: int) -> tuple[list[RingkasanYayasanRow], int]:
        """Daftar baris berurutan menurut kode masalah lalu id."""
        return self._page(None, [_M.kode, _M.id], limit, offset)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[RingkasanYayasanRow], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [_M.kode, _M.id]
        return self._page(cond, order_cols, limit, offset)

    def get(self, masalah_id: str) -> RingkasanYayasanRow:
        """Ambil satu baris ringkasan.

        Raises:
            NotFoundError: masalah tidak ada (404).
        """
        rows = self._s.execute(_base_select().where(_M.id == masalah_id)).all()
        if not rows:
            raise NotFoundError(f"Masalah '{masalah_id}' tidak ditemukan.")
        return self._rows(rows, self._proses_kode([masalah_id]))[0]
