"""Test API admin penyedia AI: kontrak lima rute, status CLI, dan larangan bocor kredensial."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

import anjab_abk_backend
from anjab_abk_backend.ai import langganan_cli
from anjab_abk_backend.ai.langganan_cli import baca_status_cli
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.fitur import ai_boleh_jalan
from anjab_abk_backend.models import (
    AiPenyediaEventModel,
    AiPenyediaPengaturanModel,
    IdempotencyRecord,
)
from anjab_abk_backend.schemas.ai_penyedia import AiPenyediaKredensialPasang

_U = "/api/v1/system/ai/penyedia"
_KUNCI = "kunci-api-sintetis-uji-panjang-7890"
_KUNCI_LAIN = "kunci-api-sintetis-lain-panjang-4321"
_SUREL = "akun-uji-sintetis@example.test"
_ALASAN = "Alasan uji penyedia"
_PASANG = {"kunci_api": _KUNCI, "alasan": _ALASAN}
_MODE_API = {"mode": "API_ANTHROPIC", "alasan": _ALASAN}
_MODEL = {"model": "claude-sonnet-4-6", "effort": "low", "alasan": _ALASAN}
_HAPUS = {"alasan": _ALASAN}
_POST = [
    (f"{_U}/mode", _MODE_API),
    (f"{_U}/model", _MODEL),
    (f"{_U}/kredensial", _PASANG),
    (f"{_U}/kredensial/hapus", _HAPUS),
]


def _atur(app, kunci_induk: str = "", **lain) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, ai_kredensial_kunci_induk=SecretStr(kunci_induk), **lain
    )


@pytest.fixture
def siap(app) -> None:
    """Kunci induk sah dan setelan baca-saja yang berbeda dari bawaan."""
    _atur(
        app,
        Fernet.generate_key().decode(),
        ai_inference_geo="us",
        ai_refusal_fallback=False,
    )


@pytest.fixture
def log_terbuka(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Buka logger yang dimatikan `fileConfig` Alembic agar uji `caplog` tidak vakum."""
    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            monkeypatch.setattr(logger, "disabled", False)
    caplog.set_level(logging.DEBUG)


def _log(caplog: pytest.LogCaptureFixture) -> str:
    return caplog.text + " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)


class _SubprocessTiruan:
    """Peniru `subprocess.run`: mencatat argumen dan membalas per subperintah."""

    def __init__(
        self,
        *,
        kode_auth: int = 0,
        stdout_versi: str = "2.1.0 (Claude Code)",
        kode_versi: int = 0,
        galat_auth: Exception | None = None,
        galat_versi: Exception | None = None,
    ) -> None:
        self.kode_auth = kode_auth
        self.stdout_versi = stdout_versi
        self.kode_versi = kode_versi
        self.galat_auth = galat_auth
        self.galat_versi = galat_versi
        self.panggilan: list[tuple[list[str], dict]] = []

    def __call__(self, args: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.panggilan.append((args, kwargs))
        if "--version" in args:
            if self.galat_versi:
                raise self.galat_versi
            return subprocess.CompletedProcess(args, self.kode_versi, stdout=self.stdout_versi)
        if self.galat_auth:
            raise self.galat_auth
        return subprocess.CompletedProcess(args, self.kode_auth, stdout=_SUREL, stderr=_SUREL)


def _pasang_tiruan(monkeypatch: pytest.MonkeyPatch, tiruan: _SubprocessTiruan) -> None:
    monkeypatch.setattr(langganan_cli.shutil, "which", lambda _nama: "/opt/tiruan/claude")
    monkeypatch.setattr(langganan_cli.subprocess, "run", tiruan)


# --- Kontrak rute ---


def test_get_tanpa_baris_cocok_contoh_kontrak(client: TestClient, siap: None) -> None:
    r = client.get(_U)
    assert r.status_code == 200
    assert r.json() == {
        "mode": "MATI",
        "mode_tersedia": ["MATI", "API_ANTHROPIC", "LANGGANAN_CLAUDE"],
        "kredensial_terpasang": False,
        "kredensial_akhiran": None,
        "kredensial_terbaca": False,
        "enkripsi_siap": True,
        "model": "claude-opus-5-5",
        "effort": "high",
        "effort_tersedia": ["low", "medium", "high", "xhigh", "max"],
        "model_bawaan": "claude-opus-5-5",
        "effort_bawaan": "high",
        "diperbarui_oleh": None,
        "diperbarui_pada": None,
        "langganan_cli_terpasang": False,
        "langganan_cli_masuk": False,
        "langganan_cli_versi": None,
        "inference_geo": "us",
        "refusal_fallback": False,
    }


def test_alur_pasang_status_hapus(client: TestClient, siap: None) -> None:
    r = client.post(f"{_U}/kredensial", json=_PASANG)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["kredensial_terpasang"] is True and b["kredensial_terbaca"] is True
    assert b["kredensial_akhiran"] == _KUNCI[-4:] and _KUNCI not in r.text
    assert b["diperbarui_oleh"] and b["diperbarui_pada"]
    g = client.get(_U)
    assert g.json()["kredensial_akhiran"] == _KUNCI[-4:] and _KUNCI not in g.text
    h = client.post(f"{_U}/kredensial/hapus", json=_HAPUS)
    assert h.status_code == 200
    assert h.json()["kredensial_terpasang"] is False and h.json()["kredensial_akhiran"] is None
    assert h.json()["kredensial_terbaca"] is False


def test_kunci_tepat_dua_puluh_karakter_diterima(client: TestClient, siap: None) -> None:
    r = client.post(f"{_U}/kredensial", json={"kunci_api": "a" * 20, "alasan": _ALASAN})
    assert r.status_code == 200, r.text


def test_mode_api_lalu_langganan_tersimpan_walau_cli_belum_masuk_tanpa_menyalakan_ai(
    client: TestClient, siap: None, db_session: Session
) -> None:
    assert client.post(f"{_U}/mode", json=_MODE_API).json()["mode"] == "API_ANTHROPIC"
    r = client.post(f"{_U}/mode", json={"mode": "LANGGANAN_CLAUDE", "alasan": _ALASAN})
    assert r.status_code == 200
    assert r.json()["mode"] == "LANGGANAN_CLAUDE" and r.json()["langganan_cli_masuk"] is False
    assert client.get(_U).json()["mode"] == "LANGGANAN_CLAUDE"
    assert ai_boleh_jalan(db_session, Settings(_env_file=None)) is False


def test_ubah_model_effort_dan_baca_saja_tetap_dari_env(client: TestClient, siap: None) -> None:
    r = client.post(f"{_U}/model", json=_MODEL)
    assert r.status_code == 200, r.text
    g = client.get(_U).json()
    assert (g["model"], g["effort"]) == ("claude-sonnet-4-6", "low")
    assert (g["model_bawaan"], g["effort_bawaan"]) == ("claude-opus-5-5", "high")
    assert g["inference_geo"] == "us" and g["refusal_fallback"] is False
    b = client.post(f"{_U}/model", json={"model": None, "effort": None, "alasan": _ALASAN})
    assert (b.json()["model"], b.json()["effort"]) == ("claude-opus-5-5", "high")


@pytest.mark.parametrize(
    "payload",
    [{"model": "claude-sonnet-4-6", "alasan": _ALASAN}, {"effort": "low", "alasan": _ALASAN}],
)
def test_field_model_effort_yang_tak_dikirim_422_tidak_mereset(
    client: TestClient, siap: None, payload: dict
) -> None:
    assert client.post(f"{_U}/model", json=payload).status_code == 422


def test_negatif_konflik(client: TestClient, siap: None) -> None:
    r = client.post(f"{_U}/mode", json={"mode": "MATI", "alasan": _ALASAN})
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    assert client.post(f"{_U}/kredensial/hapus", json=_HAPUS).status_code == 409
    sama = {"model": "claude-opus-5-5", "effort": "high", "alasan": _ALASAN}
    assert client.post(f"{_U}/model", json=sama).status_code == 409


@pytest.mark.parametrize("nama", ["claude-fable-x", "claude-mythos-1", "gpt-4", ""])
def test_model_ditolak_kode_envelope(client: TestClient, siap: None, nama: str) -> None:
    r = client.post(f"{_U}/model", json={"model": nama, "effort": None, "alasan": _ALASAN})
    assert r.status_code == 422
    assert r.json()["error"] == "MODEL_DITOLAK" and r.json()["request_id"]


def test_mode_dan_effort_tak_dikenal_422(client: TestClient, siap: None) -> None:
    assert client.post(f"{_U}/mode", json={"mode": "LAIN", "alasan": _ALASAN}).status_code == 422
    r = client.post(f"{_U}/model", json={"model": None, "effort": "ekstrem", "alasan": _ALASAN})
    assert r.status_code == 422


@pytest.mark.parametrize(("url", "body"), _POST)
def test_alasan_pendek_422(client: TestClient, siap: None, url: str, body: dict) -> None:
    assert client.post(url, json={**body, "alasan": "abc"}).status_code == 422


@pytest.mark.parametrize(
    "kasus",
    [{"kunci_api": "x", "alasan": _ALASAN}, {"model": None}],
    ids=["kunci-pendek", "bukan-body-sah"],
)
def test_non_admin_dengan_body_salah_tetap_403(client_as, siap: None, kasus: dict) -> None:
    pengguna = client_as("bukan-admin", groups=["partisipan"])
    assert pengguna.post(f"{_U}/kredensial", json=kasus).status_code == 403


def test_non_admin_403_dan_tanpa_token_401_kelima_rute(
    anon_client: TestClient, client_as, siap: None, db_session: Session
) -> None:
    assert anon_client.get(_U).status_code == 401
    for url, body in _POST:
        assert anon_client.post(url, json=body).status_code == 401, url
    pengguna = client_as("bukan-admin", groups=["partisipan"])
    assert pengguna.get(_U).status_code == 403
    for url, body in _POST:
        assert pengguna.post(url, json=body).status_code == 403, url
    assert db_session.query(AiPenyediaPengaturanModel).count() == 0
    assert db_session.query(AiPenyediaEventModel).count() == 0


def test_openapi_lima_rute_tanpa_field_kredensial_langganan(app) -> None:
    skema = app.openapi()
    ops = {
        f"{m.upper()} {p}": op["operationId"]
        for p, item in skema["paths"].items()
        if "/system/ai/penyedia" in p
        for m, op in item.items()
    }
    assert ops == {
        f"GET {_U}": "system_ai_penyedia_get",
        f"POST {_U}/mode": "system_ai_penyedia_mode",
        f"POST {_U}/model": "system_ai_penyedia_model",
        f"POST {_U}/kredensial": "system_ai_penyedia_kredensial_pasang",
        f"POST {_U}/kredensial/hapus": "system_ai_penyedia_kredensial_hapus",
    }
    komponen = skema["components"]["schemas"]
    kunci = komponen["AiPenyediaKredensialPasang"]["properties"]["kunci_api"]
    assert kunci["writeOnly"] is True and kunci["format"] == "password"
    assert kunci["minLength"] == 20
    keluaran = set(komponen["AiPenyediaRead"]["properties"])
    assert not {"kunci_api", "kredensial", "email", "surel", "akun", "token"} & keluaran
    for nama in (
        "AiPenyediaModeUbah",
        "AiPenyediaModelUbah",
        "AiPenyediaKredensialPasang",
        "AiPenyediaKredensialHapus",
    ):
        masukan = set(komponen[nama]["properties"])
        assert masukan <= {"mode", "model", "effort", "kunci_api", "alasan"}


def test_rute_tidak_pernah_memanggil_baca_kunci_api() -> None:
    akar = Path(anjab_abk_backend.__file__).parent / "api"
    berkas = list(akar.rglob("*.py"))
    assert len(berkas) > 10
    assert not [p for p in berkas if "baca_kunci_api" in p.read_text(encoding="utf-8")]


# --- Larangan bocor kunci ---


@pytest.mark.parametrize(
    "kunci",
    ["k" * 19, "  pendek-stlh-strip  ", " " * 30],
    ids=["19-karakter", "spasi-pengapit", "hanya-spasi"],
)
def test_kunci_pendek_422_tidak_menggemakan_nilai(
    client: TestClient,
    siap: None,
    db_session: Session,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
    kunci: str,
) -> None:
    r = client.post(f"{_U}/kredensial", json={"kunci_api": kunci, "alasan": _ALASAN})
    assert r.status_code == 422
    b = r.json()
    assert b["error"] == "validation_error" and b["request_id"]
    assert b["details"] and all(set(d) <= {"loc", "msg", "type", "code"} for d in b["details"])
    assert kunci not in r.text and kunci not in _log(caplog)
    if kunci.strip():
        assert kunci.strip() not in r.text
    assert db_session.query(AiPenyediaPengaturanModel).count() == 0


@pytest.mark.parametrize(
    "mentah",
    [
        f'{{"kunci_api": "{_KUNCI}", "alasan": "abc"}}',
        f'{{"kunci_api": ["{_KUNCI}"], "alasan": "{_ALASAN}"}}',
        f'{{"kunci_api": {{"nilai": "{_KUNCI}"}}, "alasan": "{_ALASAN}"}}',
        f'{{"kunci_api": "{_KUNCI}", "alasan": "{_ALASAN}", "lain": "{_KUNCI}"}}',
        f'{{"kunci_api": "{_KUNCI}", "alasan": ',
    ],
    ids=["alasan-pendek", "bentuk-list", "bentuk-objek", "field-asing", "json-rusak"],
)
def test_422_lain_pada_permintaan_berkunci_tidak_menggemakan_kunci(
    client: TestClient,
    siap: None,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
    mentah: str,
) -> None:
    r = client.post(
        f"{_U}/kredensial", content=mentah, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422
    assert _KUNCI not in r.text and _KUNCI not in _log(caplog)


@pytest.mark.parametrize("induk", ["", "bukan-kunci-fernet"], ids=["kosong", "salah"])
def test_kunci_induk_tidak_ada_503_tanpa_baris_dan_tanpa_bocor(
    client: TestClient,
    app,
    db_session: Session,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
    induk: str,
) -> None:
    _atur(app, induk)
    assert client.get(_U).json()["enkripsi_siap"] is False
    r = client.post(f"{_U}/kredensial", json=_PASANG, headers={"Idempotency-Key": "uji-503"})
    assert r.status_code == 503
    assert r.json()["error"] == "KUNCI_INDUK_TIDAK_ADA" and r.json()["request_id"]
    assert _KUNCI not in r.text and _KUNCI not in _log(caplog)
    assert db_session.query(AiPenyediaPengaturanModel).count() == 0
    assert db_session.query(AiPenyediaEventModel).count() == 0
    assert db_session.query(IdempotencyRecord).count() == 0


def test_alur_penuh_kunci_tak_muncul_di_caplog_kontrol_positif(
    client: TestClient,
    siap: None,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert client.post(f"{_U}/kredensial", json=_PASANG).status_code == 200
    assert client.post(f"{_U}/kredensial/hapus", json=_HAPUS).status_code == 200
    log = _log(caplog)
    assert "ai_penyedia" in log, "log audit tak tertangkap: uji ini vakum"
    assert _KUNCI not in log


# --- Idempotensi ---


def test_catatan_idempotensi_tanpa_kunci_dan_tanpa_turunan_body(
    client: TestClient, siap: None, db_session: Session
) -> None:
    kolom = set(IdempotencyRecord.__table__.columns.keys())
    assert kolom == {"key", "response", "completed", "created_at", "expires_at"}
    r = client.post(f"{_U}/kredensial", json=_PASANG, headers={"Idempotency-Key": "uji-rahasia"})
    assert r.status_code == 200
    baris = db_session.execute(
        text("select key, response::text, completed from idempotency_keys")
    ).all()
    assert len(baris) == 1
    pk, respons, selesai = baris[0]
    assert selesai is True
    assert pk == hashlib.sha256(f"POST:{_U}/kredensial:uji-rahasia".encode()).hexdigest()
    assert _KUNCI not in respons
    assert hashlib.sha256(_KUNCI.encode()).hexdigest() not in pk + respons
    assert f'"kredensial_akhiran": "{_KUNCI[-4:]}"' in respons


def test_secretstr_serialisasi_tertopeng() -> None:
    m = AiPenyediaKredensialPasang(kunci_api=_KUNCI, alasan=_ALASAN)
    for keluaran in (repr(m), str(m), m.model_dump_json(), str(m.model_dump())):
        assert _KUNCI not in keluaran


@pytest.mark.parametrize(
    ("url", "body", "konflik_tanpa_key"),
    [
        (f"{_U}/mode", _MODE_API, True),
        (f"{_U}/model", _MODEL, True),
        (f"{_U}/kredensial", _PASANG, False),
        (f"{_U}/kredensial/hapus", _HAPUS, True),
    ],
    ids=["mode", "model", "kredensial", "hapus"],
)
def test_retry_key_sama_mengembalikan_respons_tersimpan_bukan_409(
    client: TestClient,
    siap: None,
    db_session: Session,
    url: str,
    body: dict,
    konflik_tanpa_key: bool,
) -> None:
    if url.endswith("/hapus"):
        assert client.post(f"{_U}/kredensial", json=_PASANG).status_code == 200
    awal = db_session.query(AiPenyediaEventModel).count()
    kepala = {"Idempotency-Key": "uji-retry"}
    a = client.post(url, json=body, headers=kepala)
    b = client.post(url, json=body, headers=kepala)
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert a.json() == b.json()
    assert db_session.query(AiPenyediaEventModel).count() == awal + 1
    if konflik_tanpa_key:
        assert client.post(url, json=body).status_code == 409


def test_key_sama_kunci_berbeda_membalas_respons_lama_tanpa_memasang(
    client: TestClient, siap: None
) -> None:
    kepala = {"Idempotency-Key": "uji-ganti"}
    assert client.post(f"{_U}/kredensial", json=_PASANG, headers=kepala).status_code == 200
    lain = {"kunci_api": _KUNCI_LAIN, "alasan": _ALASAN}
    r = client.post(f"{_U}/kredensial", json=lain, headers=kepala)
    assert r.status_code == 200 and r.json()["kredensial_akhiran"] == _KUNCI[-4:]
    assert client.get(_U).json()["kredensial_akhiran"] == _KUNCI[-4:]
    assert _KUNCI_LAIN not in r.text


def test_konflik_melepas_key_agar_dapat_dicoba_lagi(client: TestClient, siap: None) -> None:
    kepala = {"Idempotency-Key": "uji-lepas"}
    assert client.post(f"{_U}/kredensial/hapus", json=_HAPUS, headers=kepala).status_code == 409
    assert client.post(f"{_U}/kredensial", json=_PASANG).status_code == 200
    assert client.post(f"{_U}/kredensial/hapus", json=_HAPUS, headers=kepala).status_code == 200


# --- Status CLI ---


def test_cli_binary_tidak_ada(monkeypatch: pytest.MonkeyPatch) -> None:
    tiruan = _SubprocessTiruan()
    monkeypatch.setattr(langganan_cli.shutil, "which", lambda _nama: None)
    monkeypatch.setattr(langganan_cli.subprocess, "run", tiruan)
    st = baca_status_cli()
    assert (st.terpasang, st.masuk, st.versi) == (False, False, None)
    assert tiruan.panggilan == []


def test_cli_exit_nol_masuk(monkeypatch: pytest.MonkeyPatch) -> None:
    _pasang_tiruan(monkeypatch, _SubprocessTiruan())
    st = baca_status_cli()
    assert (st.terpasang, st.masuk, st.versi) == (True, True, "2.1.0 (Claude Code)")


def test_cli_exit_satu_belum_masuk(monkeypatch: pytest.MonkeyPatch) -> None:
    _pasang_tiruan(monkeypatch, _SubprocessTiruan(kode_auth=1))
    st = baca_status_cli()
    assert (st.terpasang, st.masuk) == (True, False)


@pytest.mark.parametrize(
    "galat",
    [subprocess.TimeoutExpired(["claude"], 10, output=_SUREL), OSError("gagal"), ValueError("x")],
    ids=["timeout", "oserror", "valueerror"],
)
def test_cli_galat_gagal_tertutup_tanpa_melempar(
    monkeypatch: pytest.MonkeyPatch, galat: Exception
) -> None:
    _pasang_tiruan(monkeypatch, _SubprocessTiruan(galat_auth=galat, galat_versi=galat))
    st = baca_status_cli()
    assert (st.terpasang, st.masuk, st.versi) == (True, False, None)


def test_cli_batas_waktu_sepuluh_detik(monkeypatch: pytest.MonkeyPatch) -> None:
    tiruan = _SubprocessTiruan()
    _pasang_tiruan(monkeypatch, tiruan)
    baca_status_cli()
    assert len(tiruan.panggilan) == 2
    assert all(kw["timeout"] == 10 for _, kw in tiruan.panggilan)


@pytest.mark.parametrize(
    ("stdout", "kode", "harap"),
    [("", 0, None), ("  \n", 0, None), ("2.1.0", 1, None), (f"2.1.0\n{_SUREL}\n", 0, "2.1.0")],
    ids=["kosong", "spasi", "kode-bukan-nol", "hanya-baris-pertama"],
)
def test_cli_versi(
    monkeypatch: pytest.MonkeyPatch, stdout: str, kode: int, harap: str | None
) -> None:
    _pasang_tiruan(monkeypatch, _SubprocessTiruan(stdout_versi=stdout, kode_versi=kode))
    assert baca_status_cli().versi == harap


def test_cli_env_daftar_putih_persis_dari_argumen_tiruan(monkeypatch: pytest.MonkeyPatch) -> None:
    rahasia = "nilai-rahasia-sintetis"
    for nama in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_CUSTOM_HEADERS",
        "AI_KREDENSIAL_KUNCI_INDUK",
        "DATABASE_URL",
        "LAIN",
    ):
        monkeypatch.setenv(nama, rahasia)
    monkeypatch.setenv("PATH", "/opt/tiruan")
    monkeypatch.setenv("HOME", "/home/tiruan")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/tiruan/.claude")
    tiruan = _SubprocessTiruan()
    _pasang_tiruan(monkeypatch, tiruan)
    baca_status_cli()
    assert len(tiruan.panggilan) == 2
    for _args, kw in tiruan.panggilan:
        assert kw["env"] == {
            "PATH": "/opt/tiruan",
            "HOME": "/home/tiruan",
            "CLAUDE_CONFIG_DIR": "/home/tiruan/.claude",
        }


def test_cli_env_tidak_mengarang_variabel_yang_tak_diset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    tiruan = _SubprocessTiruan()
    _pasang_tiruan(monkeypatch, tiruan)
    baca_status_cli()
    assert all("CLAUDE_CONFIG_DIR" not in kw["env"] for _, kw in tiruan.panggilan)


def test_cli_auth_status_keluarannya_dibuang_di_tingkat_proses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tiruan = _SubprocessTiruan()
    _pasang_tiruan(monkeypatch, tiruan)
    baca_status_cli()
    args, kw = next(p for p in tiruan.panggilan if "auth" in p[0])
    assert args[-2:] == ["auth", "status"]
    assert kw["stdout"] == subprocess.DEVNULL and kw["stderr"] == subprocess.DEVNULL


def test_surel_stdout_auth_status_tak_muncul_di_respons_maupun_caplog(
    client: TestClient,
    siap: None,
    monkeypatch: pytest.MonkeyPatch,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _pasang_tiruan(monkeypatch, _SubprocessTiruan())
    r = client.get(_U)
    assert r.status_code == 200
    b = r.json()
    assert b["langganan_cli_terpasang"] is True and b["langganan_cli_masuk"] is True
    assert b["langganan_cli_versi"] == "2.1.0 (Claude Code)"
    assert _SUREL not in r.text and _SUREL not in _log(caplog)
    p = client.post(f"{_U}/mode", json=_MODE_API)
    assert p.status_code == 200 and _SUREL not in p.text and _SUREL not in _log(caplog)


def test_timeout_auth_status_memuat_surel_tak_bocor_ke_log(
    client: TestClient,
    siap: None,
    monkeypatch: pytest.MonkeyPatch,
    log_terbuka: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    galat = subprocess.TimeoutExpired(["claude", "auth", "status"], 10, output=_SUREL)
    _pasang_tiruan(monkeypatch, _SubprocessTiruan(galat_auth=galat))
    r = client.get(_U)
    assert r.status_code == 200 and r.json()["langganan_cli_masuk"] is False
    log = _log(caplog)
    assert "ai_cli_gagal" in log and "TimeoutExpired" in log, "log tak tertangkap: uji vakum"
    assert _SUREL not in r.text and _SUREL not in log
