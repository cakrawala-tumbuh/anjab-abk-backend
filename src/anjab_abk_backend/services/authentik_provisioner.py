"""Seam provisioning akun pengguna Authentik.

`AuthentikProvisioner` adalah kontrak (Protocol).
`HttpAuthentikProvisioner` memanggil Authentik Admin REST API untuk membuat user
dan memasukkannya ke grup partisipan.
`PlaceholderAuthentikProvisioner` adalah standin yang dipakai saat Authentik belum
  dikonfigurasi (set env AUTHENTIK_API_URL, AUTHENTIK_API_TOKEN,
  AUTHENTIK_PARTISIPAN_GROUP_ID untuk mengaktifkan implementasi nyata).

Subject yang dikembalikan
-------------------------
`create_partisipan_user` mengembalikan **subject OIDC (`sub`)** yang akan muncul di
token saat partisipan login — yaitu nilai yang dicocokkan backend ke
`partisipan.authentik_user_id` (`PartisipanService.get_by_subject`). Kedua provider
OAuth2 ANJAB-ABK (web & backend) memakai `sub_mode = user_email`, sehingga `sub` =
**email**. Karena itu provisioner mengembalikan email, bukan pk numerik Authentik:
pk tidak pernah sama dengan `sub` pada konfigurasi ini sehingga menyimpannya membuat
tautan identitas meleset (hanya tertolong fallback email di `get_by_subject`).
"""

from __future__ import annotations

from typing import Protocol

import httpx

from ..errors import ConflictError, ServiceUnavailableError


class AuthentikProvisioner(Protocol):
    """Kontrak provisioning akun pengguna Authentik."""

    def create_partisipan_user(self, *, nama: str, email: str) -> str:
        """Buat pengguna di Authentik dan tambah ke grup partisipan.

        Returns:
            Subject OIDC (`sub`) pengguna — dengan `sub_mode=user_email` ini adalah
            email. Nilai ini disimpan ke `partisipan.authentik_user_id` dan dicocokkan
            saat login.

        Raises:
            ConflictError: bila email/username sudah terdaftar di Authentik.
            ServerError: bila Authentik tidak dapat dijangkau atau mengembalikan error.
        """
        ...


class PlaceholderAuthentikProvisioner:
    """Standin saat Authentik belum dikonfigurasi.

    Aktif bila env AUTHENTIK_API_URL/AUTHENTIK_API_TOKEN/AUTHENTIK_PARTISIPAN_GROUP_ID
    belum di-set. TIDAK membuat akun Authentik sungguhan; ia hanya mengembalikan subject
    yang konsisten dengan `sub_mode=user_email` (email) agar tautan identitas tetap benar
    di lingkungan dev/test. Ganti dengan HttpAuthentikProvisioner via konfigurasi env.
    """

    def create_partisipan_user(self, *, nama: str, email: str) -> str:
        return email


class HttpAuthentikProvisioner:
    """Provisioner yang memanggil Authentik Admin REST API."""

    def __init__(self, *, api_url: str, api_token: str, partisipan_group_id: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self._group_id = partisipan_group_id

    def create_partisipan_user(self, *, nama: str, email: str) -> str:
        username = email.lower()
        payload = {
            "username": username,
            "name": nama,
            "email": email,
            "type": "internal",
            "groups": [self._group_id],
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._api_url}/api/v3/core/users/",
                    json=payload,
                    headers=self._headers,
                )
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(f"Tidak dapat menghubungi Authentik: {exc}") from exc

        if resp.status_code == 400:
            body = resp.json()
            if "username" in body or "email" in body:
                raise ConflictError(f"Email '{email}' sudah terdaftar di Authentik.")
            raise ServiceUnavailableError(f"Authentik menolak permintaan: {body}")

        if not resp.is_success:
            raise ServiceUnavailableError(
                f"Authentik mengembalikan status {resp.status_code}: {resp.text}"
            )

        # Pastikan user benar-benar terbuat (memvalidasi respons), tetapi kembalikan
        # SUBJECT OIDC (email) — bukan pk — agar cocok dengan `sub_mode=user_email`.
        _ = resp.json()["pk"]
        return email
