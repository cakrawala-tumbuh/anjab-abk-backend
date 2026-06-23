"""Terjemahkan domain bergaya Odoo → ekspresi SQL (SQLAlchemy) yang AMAN.

Ini melengkapi `app/services/domain.py` milik backend-skill (evaluator in-memory
untuk placeholder). Modul ini TIDAK menduplikasi validasi: ia **memakai ulang**
`validate_domain_structure` dan `normalize_domain` dari sana, lalu membangun
ekspresi boolean SQLAlchemy alih-alih mengevaluasi dict in-memory.

Keamanan injeksi:
- Semua *value* menjadi **bound parameter** otomatis (SQLAlchemy), tidak pernah
  di-string-interpolate ke SQL.
- Nama *field* tidak pernah masuk SQL sebagai teks bebas: hanya field yang ada di
  `field_map` (whitelist per-resource) yang dapat dipetakan ke kolom; field asing
  → `ValidationAppError` (422). Operator sudah di-whitelist oleh `Literal` di
  `schemas/search.py` dan dipetakan lewat tabel tetap di sini.

Kesetaraan semantik dengan evaluator in-memory (lihat catatan NULL & case di
references/domain-ke-sql.md):
- `like`/`ilike` = pencocokan substring (autoescape `%`/`_` pada nilai user).
  Di PostgreSQL `LIKE` **case-sensitive** (sesuai Odoo) dan `ILIKE` adalah operator
  **native** case-insensitive — tanpa gotcha collation seperti MySQL.
- `=like`/`=ilike` = pola wildcard apa adanya (`%`, `_`).
- `in`/`not in` pada field daftar (mis. `tags`) = keanggotaan via subquery EXISTS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, not_, or_, select, true

from ..errors import ValidationAppError
from ..schemas.common import ErrorDetail
from ..schemas.search import Domain, Order

# Memakai ulang validator backend-skill (anti-redundansi) — JANGAN tulis ulang.
from .domain import normalize_domain, validate_domain_structure

# Builder leaf untuk field "virtual"/relasi (mis. tags): (operator, value) -> ekspresi bool.
LeafBuilder = Callable[[str, Any], ColumnElement[bool]]


@dataclass(frozen=True)
class FieldSpec:
    """Pemetaan satu field search → cara membentuk predikat & pengurutan SQL.

    Tepat salah satu dari `column` atau `leaf` harus diisi:
    - `column`: kolom skalar biasa (string/angka/tanggal).
    - `leaf`: builder kustom untuk field non-skalar/relasi (mis. `tags` → EXISTS).

    `order_column` dipakai untuk `ORDER BY` (default = `column`). Field tanpa
    target pengurutan (mis. virtual) → menolak `order` dengan 422.
    """

    column: ColumnElement[Any] | None = None
    leaf: LeafBuilder | None = None
    order_column: ColumnElement[Any] | None = None


FieldMap = dict[str, FieldSpec]


def _as_list(value: Any) -> list[Any]:
    """Normalkan value `in`/`not in` menjadi list."""
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _scalar_predicate(col: ColumnElement[Any], op: str, value: Any) -> ColumnElement[bool]:
    """Bangun predikat untuk kolom skalar. Semua value jadi bound parameter."""
    if op == "=":
        return col.is_(None) if value is None else col == value
    if op == "!=":
        return col.is_not(None) if value is None else col != value
    if op == ">":
        return col > value
    if op == ">=":
        return col >= value
    if op == "<":
        return col < value
    if op == "<=":
        return col <= value
    if op == "in":
        return col.in_(_as_list(value))
    if op == "not in":
        return col.not_in(_as_list(value))
    if op == "like":  # substring; autoescape memperlakukan %/_ pada value sebagai literal
        return col.contains(value, autoescape=True)
    if op == "ilike":  # PostgreSQL: ILIKE native (case-insensitive)
        return col.icontains(value, autoescape=True)
    if op == "not like":
        return not_(col.contains(value, autoescape=True))
    if op == "not ilike":
        return not_(col.icontains(value, autoescape=True))
    if op == "=like":  # pola wildcard apa adanya (%/_ dari user dipertahankan)
        return col.like(value)
    if op == "=ilike":
        return col.ilike(value)
    raise ValidationAppError(f"Operator '{op}' tidak didukung.")


def make_membership_leaf(
    tag_column: ColumnElement[Any], correlate_predicate: ColumnElement[bool]
) -> LeafBuilder:
    """Bangun LeafBuilder untuk field daftar berbasis relasi (mis. `tags`).

    `tag_column` adalah kolom nilai pada tabel relasi (mis. `ItemTagModel.tag`),
    `correlate_predicate` mengkorelasikan baris relasi dengan baris induk
    (mis. `ItemTagModel.item_id == ItemModel.id`). Operator positif (`in`/`=`/
    `like`/`ilike`) → `EXISTS(... predikat ...)`; operator negatif → `NOT EXISTS`.
    """
    _NEG = {"not in": "in", "!=": "=", "not like": "like", "not ilike": "ilike"}

    def build(op: str, value: Any) -> ColumnElement[bool]:
        negate = op in _NEG
        pos_op = _NEG.get(op, op)
        inner = _scalar_predicate(tag_column, pos_op, value)
        exists_q = select(1).where(and_(correlate_predicate, inner)).exists()
        return not_(exists_q) if negate else exists_q

    return build


def _leaf(field: str, op: str, value: Any, field_map: FieldMap) -> ColumnElement[bool]:
    spec = field_map.get(field)
    if spec is None:  # pertahanan berlapis (service sudah memanggil validate_searchable_fields)
        raise ValidationAppError(
            "Field tidak diizinkan untuk pencarian.",
            details=[
                ErrorDetail(
                    loc=["domain", field],
                    msg="Field tidak diizinkan.",
                    type="not_allowed",
                    code="not_allowed",
                )
            ],
        )
    if spec.leaf is not None:
        return spec.leaf(op, value)
    assert spec.column is not None
    return _scalar_predicate(spec.column, op, value)


def compile_domain(domain: Domain, field_map: FieldMap) -> ColumnElement[bool]:
    """Kompilasi domain Odoo → ekspresi boolean SQLAlchemy (untuk klausa WHERE).

    Memvalidasi keseimbangan aritas lebih dulu (`validate_domain_structure` →
    422 bila tak seimbang), lalu menormalkan AND implisit, lalu mengonsumsi token
    notasi prefix (sama urutan dengan evaluator in-memory). Domain kosong → `TRUE`.
    """
    validate_domain_structure(domain)
    if not domain:
        return true()
    tokens = iter(normalize_domain(list(domain)))

    def consume() -> ColumnElement[bool]:
        token = next(tokens)
        if token == "!":
            return not_(consume())
        if token == "&":
            left = consume()
            right = consume()
            return and_(left, right)
        if token == "|":
            left = consume()
            right = consume()
            return or_(left, right)
        field, op, value = token
        return _leaf(field, op, value, field_map)

    return consume()


def order_by_columns(order: Order, field_map: FieldMap) -> list[ColumnElement[Any]]:
    """Bentuk daftar ekspresi `ORDER BY` dari `order` (field, 'asc'|'desc').

    Field tanpa `order_column` (mis. virtual `tags`) ditolak 422 — tidak ada kolom
    deterministik untuk diurutkan.
    """
    clauses: list[ColumnElement[Any]] = []
    for field, direction in order:
        spec = field_map.get(field)
        # JANGAN pakai `or` pada ColumnElement: truthiness-nya tak terdefinisi
        # (SQLAlchemy melempar TypeError). Pilih eksplisit dengan `is not None`.
        target: ColumnElement[Any] | None = None
        if spec is not None:
            target = spec.order_column if spec.order_column is not None else spec.column
        if target is None:
            raise ValidationAppError(
                "Field tidak bisa dipakai untuk pengurutan.",
                details=[
                    ErrorDetail(
                        loc=["order", field],
                        msg="Field tidak dapat diurutkan.",
                        type="not_sortable",
                        code="not_sortable",
                    )
                ],
            )
        clauses.append(target.desc() if direction == "desc" else target.asc())
    return clauses


__all__ = [
    "FieldSpec",
    "FieldMap",
    "compile_domain",
    "order_by_columns",
    "make_membership_leaf",
]
