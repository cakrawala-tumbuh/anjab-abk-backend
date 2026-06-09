"""Skema pencarian bergaya domain Odoo."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DomainOperator = Literal[
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "like",
    "ilike",
    "not like",
    "not ilike",
    "=like",
    "=ilike",
    "in",
    "not in",
]

LogicOperator = Literal["&", "|", "!"]
Condition = tuple[str, DomainOperator, Any]
DomainTerm = LogicOperator | Condition
Domain = list[DomainTerm]
OrderTerm = tuple[str, Literal["asc", "desc"]]
Order = list[OrderTerm]


class SearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "domain": [["nama", "ilike", "dasar"]],
                    "order": [["nama", "asc"]],
                    "limit": 20,
                    "offset": 0,
                }
            ]
        },
    )

    domain: Domain = Field(
        default_factory=list,
        max_length=50,
        description="Kriteria pencarian bergaya domain Odoo (notasi prefix). Maks 50 term.",
    )
    order: Order = Field(
        default_factory=list,
        max_length=10,
        description="Urutan hasil: daftar (field, 'asc'|'desc'). Maks 10 kunci.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Maks item per halaman.")
    offset: int = Field(default=0, ge=0, description="Jumlah item yang dilewati.")
