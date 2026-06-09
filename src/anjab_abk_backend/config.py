"""Konfigurasi runtime via pydantic-settings (12-factor).

Semua nilai dibaca dari environment / file `.env` dan di-cache sebagai singleton
lewat `get_settings()`. TIDAK ada variabel sumber data (DSN/URL database/kredensial) —
akses data adalah seam dependency injection (lihat services/ dan CLAUDE.md aturan #3).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pengaturan aplikasi ANJAB-ABK."""

    app_title: str = "ANJAB-ABK Backend"
    log_level: str = "INFO"

    host: str = "0.0.0.0"
    port: int = 8000

    docs_enabled: bool = True
    public_base_url: str | None = None
    cors_origins: list[str] = []
    cors_allow_credentials: bool = False
    allowed_hosts: list[str] = ["*"]

    # Hardening HTTP
    max_request_body_bytes: int = 1_048_576  # 1 MiB
    request_timeout_seconds: float = 0
    enable_security_headers: bool = True
    enable_hsts: bool = False
    enable_coop: bool = True
    gzip_min_size: int = 1024
    access_log_excludes: list[str] = ["/api/v1/health", "/api/v1/ready"]
    require_if_match: bool = False

    # Observability
    tracing_enabled: bool = False

    # Auth Authentik — parameter validasi token (seam; bukan koneksi ke IdP).
    # Diisi oleh skill backend-authentik-skill.
    authentik_issuer: str | None = None
    authentik_jwks_uri: str | None = None
    api_audience: str | None = None

    # OAuth2 interaktif Swagger (opsional, doc-only)
    oauth2_authorization_url: str | None = None
    oauth2_token_url: str | None = None
    oauth2_client_id: str | None = None
    oauth2_scopes: str = "openid profile email"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def _reject_wildcard_origin_with_credentials(self) -> Settings:
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS tidak boleh memuat '*' saat CORS_ALLOW_CREDENTIALS=true."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Kembalikan instance Settings yang di-cache (singleton proses)."""
    return Settings()
