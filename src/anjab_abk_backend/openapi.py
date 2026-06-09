"""Metadata & kustomisasi OpenAPI (Swagger WAJIB)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from . import __version__
from .config import Settings
from .security import build_extra_security_schemes

TAGS_METADATA = [
    {"name": "system", "description": "Health, readiness, dan informasi versi service."},
    {
        "name": "core.jenjang-pendidikan",
        "description": "Jenjang/tingkat pendidikan (PAUD, TK, SD, SMP, SMA, SMK, dll.).",
    },
    {
        "name": "core.sekolah",
        "description": "Sekolah / satuan pendidikan yang dikelola yayasan.",
    },
    {
        "name": "core.mata-pelajaran",
        "description": "Mata pelajaran.",
    },
    {
        "name": "core.partisipan",
        "description": "Partisipan — pegawai yang dianalisis dalam ANJAB/ABK.",
    },
    {
        "name": "anjab.jabatan",
        "description": "Jabatan — entitas utama Analisis Jabatan (ANJAB).",
    },
    {
        "name": "wcp.dimensi",
        "description": "Master data 12 dimensi WCP dan 72 item pernyataan (read-only).",
    },
    {
        "name": "wcp.sesi",
        "description": (
            "Sesi survei WCP per jabatan — CRUD dan transisi status"
            " (DRAFT→OPEN→CLOSED→ANALYZED)."
        ),
    },
    {
        "name": "wcp.responden",
        "description": "Responden dalam sesi WCP dan submit jawaban.",
    },
    {
        "name": "wcp.hasil",
        "description": (
            "Analisis WCP: jalankan kalkulasi dan ambil hasil per sesi maupun per responden."
        ),
    },
]

DESCRIPTION = (
    "## Ringkasan\n"
    "Backend REST API untuk **ANJAB** (Analisis Jabatan) dan **ABK** (Analisis Beban Kerja) "
    "pada yayasan pendidikan.\n\n"
    "- Format error seragam (lihat skema `ErrorResponse`).\n"
    "- Autentikasi via Bearer token Authentik — gunakan tombol **Authorize**.\n"
    "- Paginasi konsisten lewat amplop `Page`.\n"
    "- Search memakai domain bergaya Odoo via `POST .../search`.\n"
)


def openapi_kwargs(settings: Settings) -> dict:
    kwargs: dict = {
        "title": settings.app_title,
        "version": __version__,
        "summary": "Backend REST API ANJAB & ABK yayasan pendidikan.",
        "description": DESCRIPTION,
        "contact": {"name": "Tim Pengembang", "email": "dev@example.com"},
        "license_info": {"name": "MIT", "identifier": "MIT"},
        "openapi_tags": TAGS_METADATA,
        "docs_url": "/docs" if settings.docs_enabled else None,
        "redoc_url": "/redoc" if settings.docs_enabled else None,
        "openapi_url": "/openapi.json" if settings.docs_enabled else None,
        "swagger_ui_parameters": {
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "docExpansion": "none",
            "filter": True,
        },
    }
    if settings.oauth2_client_id:
        init_oauth = {"clientId": settings.oauth2_client_id, "scopes": settings.oauth2_scopes}
        kwargs["swagger_ui_init_oauth"] = init_oauth
        kwargs["swagger_ui_parameters"]["initOAuth"] = init_oauth
    return kwargs


def install_openapi(app: FastAPI, settings: Settings) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        if settings.public_base_url:
            schema["servers"] = [{"url": settings.public_base_url, "description": "Server"}]
        extra_schemes = build_extra_security_schemes(settings)
        if extra_schemes:
            components = schema.setdefault("components", {})
            components.setdefault("securitySchemes", {}).update(extra_schemes)
            oauth_scopes = (settings.oauth2_scopes or "").split()
            for methods in schema.get("paths", {}).values():
                for op in methods.values():
                    if not isinstance(op, dict):
                        continue
                    reqs = op.get("security")
                    if not reqs or any("OAuth2" in r for r in reqs):
                        continue
                    if any("BearerAuth" in r for r in reqs):
                        reqs.append({"OAuth2": oauth_scopes})
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
