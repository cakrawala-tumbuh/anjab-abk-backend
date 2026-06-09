"""Seam observability lanjutan: tracing (OTel) & metrics — no-op default."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import Settings

logger = logging.getLogger("anjab_abk_backend.observability")


def install_observability(app: FastAPI, settings: Settings) -> None:
    if settings.tracing_enabled:
        logger.info("tracing_seam_enabled_but_not_installed")
    return None
