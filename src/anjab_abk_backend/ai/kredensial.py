"""Enkripsi kredensial penyedia AI dengan Fernet.

Kunci induk berasal dari env `AI_KREDENSIAL_KUNCI_INDUK` dan tidak pernah disimpan di
basis data. Tak satu pun pesan galat di sini memuat kunci, ciphertext, atau teks asli.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from ..errors import ServiceUnavailableError

__all__ = [
    "KredensialTakTerbaca",
    "KunciIndukTidakAda",
    "dekripsi_kredensial",
    "enkripsi_kredensial",
    "fernet_dari",
]


class KunciIndukTidakAda(ServiceUnavailableError):
    """503: kunci induk kosong atau bukan kunci Fernet yang sah (gagal-tertutup)."""

    error_code = "KUNCI_INDUK_TIDAK_ADA"


class KredensialTakTerbaca(Exception):
    """Ciphertext tidak bisa didekripsi dengan kunci induk saat ini."""


def fernet_dari(kunci_induk: SecretStr) -> Fernet:
    """Bangun `Fernet` dari kunci induk.

    Raises:
        KunciIndukTidakAda: Kunci kosong atau formatnya salah.
    """
    nilai = kunci_induk.get_secret_value().strip()
    if not nilai:
        raise KunciIndukTidakAda("Kunci induk enkripsi kredensial belum diatur.")
    try:
        return Fernet(nilai.encode())
    except (ValueError, TypeError):
        raise KunciIndukTidakAda("Kunci induk enkripsi kredensial tidak sah.") from None


def enkripsi_kredensial(kunci_induk: SecretStr, teks: str) -> str:
    """Enkripsi ``teks`` menjadi token Fernet (str).

    Raises:
        KunciIndukTidakAda: Kunci induk kosong atau tidak sah.
    """
    return fernet_dari(kunci_induk).encrypt(teks.encode()).decode()


def dekripsi_kredensial(kunci_induk: SecretStr, ciphertext: str) -> str:
    """Dekripsi token Fernet.

    Raises:
        KunciIndukTidakAda: Kunci induk kosong atau tidak sah.
        KredensialTakTerbaca: Token rusak atau dibuat dengan kunci induk lain.
    """
    try:
        return fernet_dari(kunci_induk).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise KredensialTakTerbaca("Kredensial tidak dapat didekripsi.") from None
