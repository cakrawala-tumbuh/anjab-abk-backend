"""SEAM readiness check (kesiapan menerima trafik)."""

from __future__ import annotations

from typing import Protocol


class ReadinessCheck(Protocol):
    name: str

    async def check(self) -> bool: ...
