"""Evaluator domain bergaya Odoo untuk placeholder in-memory."""

from __future__ import annotations

import fnmatch
import operator
from collections.abc import Iterable
from typing import Any

from ..errors import ValidationAppError
from ..schemas.common import ErrorDetail
from ..schemas.search import Domain, Order

_ARITY = {"!": 1, "&": 2, "|": 2}


def validate_searchable_fields(domain: Domain, order: Order, allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    bad: set[str] = set()
    for term in domain:
        if isinstance(term, list | tuple) and len(term) == 3:
            field = term[0]
            if field not in allowed_set:
                bad.add(str(field))
    for term in order:
        if isinstance(term, list | tuple) and term and term[0] not in allowed_set:
            bad.add(str(term[0]))
    if bad:
        raise ValidationAppError(
            "Field tidak diizinkan untuk pencarian/pengurutan.",
            details=[
                ErrorDetail(
                    loc=["domain", f],
                    msg="Field tidak diizinkan.",
                    type="not_allowed",
                    code="not_allowed",
                )
                for f in sorted(bad)
            ],
        )


def validate_domain_structure(domain: Domain) -> None:
    tokens = normalize_domain(list(domain))
    idx = 0

    def consume() -> None:
        nonlocal idx
        if idx >= len(tokens):
            raise ValidationAppError("Domain tidak seimbang: operand kurang untuk operator logika.")
        token = tokens[idx]
        idx += 1
        if token == "!":
            consume()
        elif token in ("&", "|"):
            consume()
            consume()
        elif isinstance(token, list | tuple) and len(token) == 3:
            return
        else:
            raise ValidationAppError(f"Term domain tidak valid: {token!r}.")

    if not tokens:
        return
    consume()
    if idx != len(tokens):
        raise ValidationAppError("Domain tidak seimbang: ada term berlebih.")


def normalize_domain(domain: list) -> list:
    result: list = []
    expected = 1
    for token in domain:
        if expected == 0:
            result.insert(0, "&")
            expected = 1
        if isinstance(token, list | tuple):
            expected -= 1
        else:
            expected += _ARITY.get(token, 0) - 1
        result.append(token)
    return result


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        return " ".join(str(v) for v in value)
    return str(value)


def _cmp(field_value: Any, value: Any, fn) -> bool:
    try:
        return field_value is not None and fn(field_value, value)
    except TypeError:
        return False


def _match_leaf(field_value: Any, op: str, value: Any) -> bool:
    if op == "=":
        return field_value == value
    if op == "!=":
        return field_value != value
    if op == ">":
        return _cmp(field_value, value, operator.gt)
    if op == ">=":
        return _cmp(field_value, value, operator.ge)
    if op == "<":
        return _cmp(field_value, value, operator.lt)
    if op == "<=":
        return _cmp(field_value, value, operator.le)
    if op in ("in", "not in"):
        values = value if isinstance(value, list | tuple | set) else [value]
        if isinstance(field_value, list | tuple | set):
            hit = any(item in values for item in field_value)
        else:
            hit = field_value in values
        return hit if op == "in" else not hit
    if op in ("like", "ilike", "not like", "not ilike"):
        hay, needle = _as_text(field_value), str(value)
        if op.endswith("ilike"):
            hay, needle = hay.lower(), needle.lower()
        contained = needle in hay
        return (not contained) if op.startswith("not") else contained
    if op in ("=like", "=ilike"):
        hay, pattern = _as_text(field_value), str(value)
        if op == "=ilike":
            hay, pattern = hay.lower(), pattern.lower()
        return fnmatch.fnmatchcase(hay, pattern.replace("%", "*").replace("_", "?"))
    return False


def evaluate_domain(record: dict, domain: Domain) -> bool:
    if not domain:
        return True
    tokens = iter(normalize_domain(list(domain)))

    def consume() -> bool:
        token = next(tokens)
        if token == "!":
            return not consume()
        if token == "&":
            left, right = consume(), consume()
            return left and right
        if token == "|":
            left, right = consume(), consume()
            return left or right
        field, op, value = token
        return _match_leaf(record.get(field), op, value)

    return consume()


def sort_records(records: list[dict], order: Order) -> list[dict]:
    result = list(records)
    for field, direction in reversed(order):
        result.sort(
            key=lambda r, f=field: (r.get(f) is None, r.get(f) if r.get(f) is not None else ""),
            reverse=(direction == "desc"),
        )
    return result


def run_search(
    records: list[dict], domain: Domain, order: Order, limit: int, offset: int
) -> tuple[list[dict], int]:
    validate_domain_structure(domain)
    matched = [r for r in records if evaluate_domain(r, domain)]
    matched = sort_records(matched, order)
    return matched[offset : offset + limit], len(matched)
