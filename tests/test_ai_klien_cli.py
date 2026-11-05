"""Uji driver ``ClaudeCliKlienModel`` (#112) dengan subprocess tiruan; tanpa jaringan/kredensial.

Bentuk JSON keluaran CLI diambil dari dokumentasi resmi dan BELUM terbukti pada akun nyata;
uji memastikan pengurai gagal-tertutup, bukan bahwa bentuknya benar.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import time
from pathlib import Path

import pytest
from _cli_tiruan import SUREL, PopenTiruan, keluaran_cli, pasang

from anjab_abk_backend.ai.klien import (
    BinaryClaudeTidakAda,
    ClaudeCliKlienModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    LanggananBelumMasuk,
)
from anjab_abk_backend.ai.langganan_cli import ENV_CLAUDE_P, env_claude_p
from anjab_abk_backend.config import Settings

_CFG = Settings(_env_file=None)
_SKEMA = {"type": "object", "properties": {"ringkas": {"type": "string"}}}
_INSTRUKSI = "Ringkas sumber."


def _klien(**kw: float) -> ClaudeCliKlienModel:
    return ClaudeCliKlienModel(_CFG, model="claude-opus-5-5", effort="high", **kw)


def _panggil(masukan: str = '{"x": 1}'):
    return _klien().panggil(_INSTRUKSI, masukan, _SKEMA)


# --- positif / negatif keluaran ---------------------------------------------------------


def test_structured_output_menjadi_jawaban(monkeypatch: pytest.MonkeyPatch) -> None:
    pasang(monkeypatch)
    j = _panggil()
    assert j.teks == '{"ringkas": "ok"}'
    assert (j.model_dilayani, j.stop_reason, j.input_tokens, j.output_tokens) == (
        "claude-opus-5-5",
        "end_turn",
        11,
        5,
    )


def test_structured_output_tidak_ada_permanen(monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(keluaran_cli())
    del data["structured_output"]
    pasang(monkeypatch, stdout=json.dumps(data))
    with pytest.raises(KesalahanModelPermanen):
        _panggil()


@pytest.mark.parametrize(
    "stdout",
    [
        f"bukan json {SUREL}",
        "[]",
        "null",
        keluaran_cli(is_error=True),
        keluaran_cli(structured_output="teks"),
        keluaran_cli(usage={"input_tokens": "1", "output_tokens": 2}),
        keluaran_cli(usage=None),
        keluaran_cli(modelUsage={}),
        keluaran_cli(modelUsage={"a": {}, "b": {}}),
    ],
    ids=[
        "bukan-json",
        "daftar",
        "null",
        "is-error",
        "so-bukan-objek",
        "token-bukan-int",
        "tanpa-usage",
        "tanpa-model",
        "dua-model",
    ],
)
def test_bentuk_tak_dikenal_gagal_tertutup_permanen(
    monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    pasang(monkeypatch, stdout=stdout)
    with pytest.raises(KesalahanModelPermanen) as ei:
        _panggil()
    assert SUREL not in str(ei.value)
    assert ei.value.__cause__ is None and ei.value.__context__ is None


# --- kode gagal-tertutup ----------------------------------------------------------------


def test_binary_tidak_ada_nol_proses(monkeypatch: pytest.MonkeyPatch) -> None:
    pasang(monkeypatch, terpasang=False)
    with pytest.raises(BinaryClaudeTidakAda):
        _panggil()
    assert PopenTiruan.daftar == []


def test_belum_masuk_claude_p_tidak_dipanggil(monkeypatch: pytest.MonkeyPatch) -> None:
    pasang(monkeypatch, masuk=False)
    with pytest.raises(LanggananBelumMasuk):
        _panggil()
    assert PopenTiruan.daftar == []


def test_exit_bukan_nol_lalu_tidak_masuk_adalah_belum_masuk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pasang(monkeypatch, masuk=[True, False], kode=1, stdout=SUREL)
    with pytest.raises(LanggananBelumMasuk):
        _panggil()
    assert len(PopenTiruan.daftar) == 1


def test_exit_bukan_nol_tetap_masuk_permanen_tanpa_kebocoran(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pasang(monkeypatch, kode=2, stdout=SUREL)
    with caplog.at_level(logging.DEBUG), pytest.raises(KesalahanModelPermanen) as ei:
        _panggil(f"masukan {SUREL}")
    assert SUREL not in str(ei.value) and SUREL not in caplog.text


# --- argumen & env ----------------------------------------------------------------------


def test_argumen_tools_kosong_tanpa_bare_masukan_lewat_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pasang(monkeypatch)
    masukan = f'{{"sumber": "{SUREL}"}}'
    _panggil(masukan)
    (p,) = PopenTiruan.daftar
    a = p.args
    assert a[:2] == ["/usr/bin/claude", "-p"]
    assert a[a.index("--tools") + 1] == ""
    assert "--no-session-persistence" in a and "--strict-mcp-config" in a
    assert "--bare" not in a
    assert a[a.index("--setting-sources") + 1] == ""
    assert a[a.index("--model") + 1] == "claude-opus-5-5"
    assert a[a.index("--effort") + 1] == "high"
    assert a[a.index("--output-format") + 1] == "json"
    assert a[a.index("--system-prompt") + 1] == _INSTRUKSI
    assert '"ringkas"' in a[a.index("--json-schema") + 1]
    assert p.masukan == masukan
    assert not any(SUREL in x for x in a)  # masukan pengguna tidak ada di argumen proses
    assert p.kw["start_new_session"] is True


def test_model_dan_effort_dari_pengaturan(monkeypatch: pytest.MonkeyPatch) -> None:
    pasang(monkeypatch)
    ClaudeCliKlienModel(_CFG, model="claude-haiku-5", effort="low").panggil("i", "{}", _SKEMA)
    a = PopenTiruan.daftar[0].args
    assert (a[a.index("--model") + 1], a[a.index("--effort") + 1]) == ("claude-haiku-5", "low")


def test_cwd_direktori_sementara_dibuang(monkeypatch: pytest.MonkeyPatch) -> None:
    pasang(monkeypatch)
    _panggil()
    assert not Path(PopenTiruan.daftar[0].kw["cwd"]).exists()


def test_env_subprocess_persis_empat_nama(monkeypatch: pytest.MonkeyPatch) -> None:
    for nama in (
        "ANTHROPIC_API_KEY",
        "AI_KREDENSIAL_KUNCI_INDUK",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_CUSTOM_HEADERS",
        "DATABASE_URL",
    ):
        monkeypatch.setenv(nama, "nilai-rahasia-sintetis")
    monkeypatch.setenv("PATH", "/opt/tiruan")
    monkeypatch.setenv("HOME", "/home/tiruan")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/var/lib/tiruan")
    monkeypatch.setenv("DISABLE_UPDATES", "1")
    pasang(monkeypatch)
    _panggil()
    assert PopenTiruan.daftar[0].kw["env"] == {
        "PATH": "/opt/tiruan",
        "HOME": "/home/tiruan",
        "CLAUDE_CONFIG_DIR": "/var/lib/tiruan",
        "DISABLE_UPDATES": "1",
    }


def test_env_disable_updates_bawaan_satu_dan_tidak_mengarang_lain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nama in ("DISABLE_UPDATES", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(nama, raising=False)
    env = env_claude_p()
    assert env["DISABLE_UPDATES"] == "1" and "CLAUDE_CONFIG_DIR" not in env
    assert set(env) <= set(ENV_CLAUDE_P)


# --- timeout, kebocoran, proses yatim ---------------------------------------------------


def test_timeout_sementara_membunuh_grup_dan_tanpa_kebocoran(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    dibunuh = pasang(monkeypatch, galat_waktu=True)
    with caplog.at_level(logging.DEBUG), pytest.raises(KesalahanModelSementara) as ei:
        _panggil(f"masukan {SUREL}")
    p = PopenTiruan.daftar[0]
    assert dibunuh == [p.pid] and p.dibunuh
    e = ei.value
    assert SUREL not in str(e) and SUREL not in repr(e) and SUREL not in caplog.text
    assert e.__cause__ is None and e.__context__ is None  # TimeoutExpired tak terantai


def _mati(pid: int) -> bool:
    try:
        isi = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return isi.rsplit(")", 1)[1].split()[0] == "Z"


def _tulis_skrip(folder: Path, badan: str) -> None:
    skrip = folder / "claude"
    skrip.write_text("#!/bin/sh\n" + badan)
    skrip.chmod(skrip.stat().st_mode | stat.S_IXUSR)


def test_timeout_nyata_mematikan_proses_dan_anaknya(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Skrip ``claude`` palsu memulai anak ``sleep``; timeout menewaskan keduanya."""
    pid_berkas = tmp_path / "anak.pid"
    _tulis_skrip(
        tmp_path,
        f"""case "$1" in
  --version) echo "2.1.311 (Claude Code)"; exit 0;;
  auth) exit 0;;
esac
sleep 300 &
echo $! > "{pid_berkas}"
wait
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    with pytest.raises(KesalahanModelSementara):
        _klien(batas_waktu_detik=1).panggil(_INSTRUKSI, "{}", _SKEMA)
    pid = int(pid_berkas.read_text())
    for _ in range(40):
        if _mati(pid):
            break
        time.sleep(0.1)
    assert _mati(pid), "anak sleep masih hidup: proses yatim"


def test_proses_nyata_env_cwd_dan_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Skrip palsu merekam env, cwd, dan stdin yang benar-benar diterima proses anak."""
    rekam = tmp_path / "rekam"
    rekam.mkdir()
    (tmp_path / "keluaran.json").write_text(keluaran_cli())
    _tulis_skrip(
        tmp_path,
        f"""case "$1" in
  --version) echo "2.1.311 (Claude Code)"; exit 0;;
  auth) exit 0;;
esac
env > "{rekam}/env"
pwd > "{rekam}/cwd"
cat > "{rekam}/stdin"
cat "{tmp_path}/keluaran.json"
""",
    )
    rahasia = ("ANTHROPIC_API_KEY", "AI_KREDENSIAL_KUNCI_INDUK", "CLAUDE_CODE_OAUTH_TOKEN")
    for nama in rahasia:
        monkeypatch.setenv(nama, "nilai-rahasia-sintetis")
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    j = _klien().panggil(_INSTRUKSI, "masukan-uji", _SKEMA)
    assert j.teks == '{"ringkas": "ok"}'
    nama_env = {b.split("=", 1)[0] for b in (rekam / "env").read_text().splitlines() if "=" in b}
    assert nama_env - {"PWD", "SHLVL", "_", "OLDPWD"} <= set(ENV_CLAUDE_P)
    assert not nama_env & set(rahasia)
    assert (rekam / "stdin").read_text() == "masukan-uji"
    assert os.path.basename((rekam / "cwd").read_text().strip()).startswith("claude-kerja-")
