"""Keamanan: skema OpenAPI (Authorize Swagger) + principal & verifier sebagai seam.

Backend hanya MEMVALIDASI token; tidak menerbitkan token dan tidak terhubung ke
penyimpanan identitas. Seam `TokenVerifier` diisi oleh skill `backend-authentik-skill`.
Jangan ubah signature `TokenVerifier.verify` — kontrak ini stabil.
"""

from __future__ import annotations

from typing import Protocol

from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    auto_error=False,
    description="Bearer token (JWT dari Authentik).",
)


def build_extra_security_schemes(settings) -> dict:
    """Skema OAuth2 interaktif Swagger (doc-only, saat endpoint OAuth2 di-set)."""
    auth_url = getattr(settings, "oauth2_authorization_url", None)
    token_url = getattr(settings, "oauth2_token_url", None)
    if not (auth_url and token_url):
        return {}
    scope_names = (getattr(settings, "oauth2_scopes", "") or "").split()
    return {
        "OAuth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": auth_url,
                    "tokenUrl": token_url,
                    "scopes": {name: name for name in scope_names},
                }
            },
        }
    }


class Principal(BaseModel):
    """Identitas yang sudah terverifikasi dari token."""

    subject: str = Field(description="Subject (sub) token.", examples=["user-123"])
    username: str | None = Field(default=None, description="Nama pengguna.")
    groups: list[str] = Field(default_factory=list, description="Grup Authentik.")
    scopes: list[str] = Field(default_factory=list, description="Scope/izin pada token.")


class TokenVerifier(Protocol):
    """Kontrak verifikasi token menjadi `Principal`.

    Jangan ubah signature ini — diisi oleh skill `backend-authentik-skill`.
    """

    def verify(self, token: str) -> Principal: ...


class PlaceholderVerifier:
    """SEAM — ganti dengan verifier Authentik (via skill backend-authentik-skill).

    Sengaja menolak semua token agar tidak ada celah 'allow-all' tak sengaja.
    """

    def verify(self, token: str) -> Principal:
        raise NotImplementedError(
            "Pasang verifier token Authentik (gunakan skill backend-authentik-skill)."
        )
