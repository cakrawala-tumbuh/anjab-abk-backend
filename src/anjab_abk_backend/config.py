"""Konfigurasi runtime via pydantic-settings (12-factor).

Semua nilai dibaca dari environment / file `.env` dan di-cache sebagai singleton
lewat `get_settings()`. TIDAK ada variabel sumber data (DSN/URL database/kredensial) —
akses data adalah seam dependency injection (lihat services/ dan CLAUDE.md aturan #3).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_ENV_LAMA_DIABAIKAN = frozenset({"ai_model", "ai_effort", "anthropic_api_key"})
"""Kunci berkas `.env` lama yang kini diabaikan (kini berasal dari pengaturan penyedia di DB).

`Settings` menolak kunci tak dikenal (`extra="forbid"` bawaan); tanpa daftar ini, `.env` lama
yang masih memuatnya gagal start. Hanya tiga kunci ini yang dilonggarkan."""


class _DotEnvTanpaKunciLama:
    """Pembungkus sumber `.env` yang membuang `_ENV_LAMA_DIABAIKAN` sebelum validasi."""

    def __init__(self, dasar: PydanticBaseSettingsSource) -> None:
        self._dasar = dasar

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in self._dasar().items() if k.lower() not in _ENV_LAMA_DIABAIKAN}

    def __getattr__(self, nama: str) -> Any:
        return getattr(self._dasar, nama)

    def __repr__(self) -> str:
        return repr(self._dasar)


class Settings(BaseSettings):
    """Pengaturan aplikasi ANJAB-ABK."""

    app_title: str = "ANJAB-ABK Backend"
    app_build_commit: str = "unknown"
    """SHA commit (40 hex) tempat image dibangun; env ``APP_BUILD_COMMIT``, diisi
    ``release.yml`` lewat build-arg ``GIT_COMMIT``. ``unknown`` = image dibangun di luar
    ``release.yml`` dan TIDAK boleh dipakai sebagai bukti baseline."""
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
    # Batas khusus `POST /api/v1/system/restore` (unggah dump basis data) — jauh lebih
    # besar dari batas umum karena berkas dump bisa berukuran ratusan MB. Middleware
    # `BodySizeLimitMiddleware` memakai nilai ini HANYA untuk path itu (lihat middleware.py).
    restore_max_body_bytes: int = 536_870_912  # 512 MiB
    request_timeout_seconds: float = 0
    enable_security_headers: bool = True
    enable_hsts: bool = False
    enable_coop: bool = True
    gzip_min_size: int = 1024
    access_log_excludes: list[str] = ["/api/v1/health", "/api/v1/ready"]
    require_if_match: bool = False

    # Observability
    tracing_enabled: bool = False

    # Feature flag fungsional (fail-closed: default mati). Berubah hanya lewat env +
    # restart. Diperiksa lewat `fitur.fitur_aktif` / `fitur.require_fitur`, bukan
    # dibaca langsung oleh service/router lain.
    feature_ai_narrative_draft: bool = False
    feature_participant_validation: bool = False
    feature_wcp_dcs_scoring: bool = False
    feature_research_export: bool = False
    feature_change_authorization: bool = False
    feature_prebank_freeze: bool = False

    # Register run AI (lihat services/ai_run.py)
    ai_protocol_arm: str = "TANPA_ARM"
    """Arm/prosedur pada ``Protocol_ID``; env ``AI_PROTOCOL_ARM``."""
    ai_simpan_masukan: bool = False
    """Bila true, ``masukan`` run dipertahankan setelah ``tutup``; env ``AI_SIMPAN_MASUKAN``."""

    # Gerbang redaksi PII (lihat ai/redaksi.py); bawaan paling ketat (fail-closed).
    ai_jenis_sumber_diizinkan: list[str] = ["SINTETIS"]
    """Jenis sumber yang boleh dikirim ke model; env ``AI_JENIS_SUMBER_DIIZINKAN`` (JSON).
    Jenis berawalan WCP/DCS/KONSELING/MURID selalu ditolak."""
    ai_pii_mode: Literal["BLOKIR", "SAMARKAN"] = "BLOKIR"
    """``BLOKIR`` menolak masukan bila ada PII; ``SAMARKAN`` mengganti dengan penanda
    (kecuali nama murid/keluarga); env ``AI_PII_MODE``."""

    # Klien model (lihat ai/klien.py). Mode, model, effort, dan kunci API berasal dari
    # pengaturan penyedia di basis data (UI admin), bukan dari env.
    ai_max_tokens: int = 16000
    """Batas token keluaran; env ``AI_MAX_TOKENS``."""
    ai_timeout_detik: int = 300
    """Batas waktu permintaan (detik); env ``AI_TIMEOUT_DETIK``."""
    ai_inference_geo: str = ""
    """Lokasi pemrosesan; kosong = ``inference_geo`` tidak dikirim; env ``AI_INFERENCE_GEO``."""
    ai_refusal_fallback: bool = True
    """Aktifkan fallback server-side saat penolakan; env ``AI_REFUSAL_FALLBACK``."""

    # Pendaftaran fungsi AI (lihat ai/katalog.py).
    ai_fungsi_aktif: list[str] = []
    """Kode fungsi AI yang didaftarkan; bawaan kosong; env ``AI_FUNGSI_AKTIF`` (JSON)."""

    # Worker job AI (lihat ai/worker.py).
    ai_kredensial_kunci_induk: SecretStr = SecretStr("")
    """Kunci Fernet pengenkripsi kunci API penyedia AI; env ``AI_KREDENSIAL_KUNCI_INDUK``.
    Kosong = tulis kunci API ditolak (gagal-tertutup). Tidak boleh disimpan di basis data."""
    ai_worker_poll_detik: int = 5
    """Jeda polling worker saat tidak ada job (detik); env ``AI_WORKER_POLL_DETIK``."""
    ai_job_maks_percobaan: int = 3
    """Total percobaan job sebelum ``MANUAL_REVIEW``; env ``AI_JOB_MAKS_PERCOBAAN``."""

    # Auth Authentik — parameter validasi token (seam; bukan koneksi ke IdP).
    # Diisi oleh skill backend-authentik-skill.
    authentik_issuer: str | None = None
    authentik_jwks_uri: str | None = None
    api_audience: str | None = None

    # Authentik Admin API — untuk provisioning akun partisipan.
    # Diisi agar backend dapat membuat user Authentik saat menambah partisipan.
    authentik_api_url: str | None = None
    authentik_api_token: str | None = None
    authentik_partisipan_group_id: str | None = None

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[Any, ...]:
        """Urutan sumber bawaan, dengan `.env` yang tidak memuat kunci lama (`AI_MODEL` dll)."""
        return (
            init_settings,
            env_settings,
            _DotEnvTanpaKunciLama(dotenv_settings),
            file_secret_settings,
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
