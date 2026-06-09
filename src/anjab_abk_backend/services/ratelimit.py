"""SEAM rate limiting / throttling (429)."""

from __future__ import annotations

from typing import Protocol


class RateLimiter(Protocol):
    def hit(self, key: str) -> bool: ...


class AllowAllRateLimiter:
    """Placeholder no-op — selalu mengizinkan. BUKAN limiter nyata."""

    def hit(self, key: str) -> bool:
        return True
