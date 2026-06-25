"""Unit test seam provisioner Authentik.

Memastikan provisioner mengembalikan **subject OIDC (`sub`)** yang dipakai backend untuk
mencocokkan partisipan saat login. Karena provider memakai `sub_mode=user_email`, subject
itu adalah email — bukan pk numerik Authentik.
"""

from __future__ import annotations

import httpx
import pytest

from anjab_abk_backend.errors import ConflictError
from anjab_abk_backend.services.authentik_provisioner import (
    HttpAuthentikProvisioner,
    PlaceholderAuthentikProvisioner,
)

EMAIL = "guru.contoh@ypii.sch.id"


def test_placeholder_mengembalikan_email_sebagai_subject() -> None:
    prov = PlaceholderAuthentikProvisioner()
    assert prov.create_partisipan_user(nama="Guru Contoh", email=EMAIL) == EMAIL


def _http_provisioner_with(handler, monkeypatch: pytest.MonkeyPatch) -> HttpAuthentikProvisioner:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)
    return HttpAuthentikProvisioner(
        api_url="https://authentik.example", api_token="tok", partisipan_group_id="grp"
    )


def test_http_mengembalikan_email_bukan_pk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Walau Authentik mengembalikan pk numerik, subject yang dipakai adalah email."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/v3/core/users/")
        return httpx.Response(201, json={"pk": 4242, "username": EMAIL})

    prov = _http_provisioner_with(handler, monkeypatch)
    assert prov.create_partisipan_user(nama="Guru Contoh", email=EMAIL) == EMAIL


def test_http_email_duplikat_jadi_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"email": ["sudah ada"]})

    prov = _http_provisioner_with(handler, monkeypatch)
    with pytest.raises(ConflictError):
        prov.create_partisipan_user(nama="Guru Contoh", email=EMAIL)
