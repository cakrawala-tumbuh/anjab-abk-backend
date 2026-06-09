"""Util ETag untuk concurrency control opsional (optimistic locking)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def compute_etag(payload: BaseModel | dict[str, Any]) -> str:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'
