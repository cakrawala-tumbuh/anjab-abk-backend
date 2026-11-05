"""Uji harness evaluasi P10 (``evals/``) dengan klien tiruan: tanpa jaringan, tanpa kredensial.

Yang dibuktikan di sini adalah PENILAI dan HARNESS (gerbang, perakitan masukan, kode exit,
baris ``#EVAL``). Perilaku MODEL sungguhan tidak dapat dibuktikan tanpa panggilan nyata;
itu langkah operator (``make eval-ai``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from anjab_abk_backend.ai.fungsi_p10 import FUNGSI_P10
from anjab_abk_backend.ai.gateway import AiGateway
from anjab_abk_backend.ai.klien import (
    JawabanModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    LanggananBelumMasuk,
)
from anjab_abk_backend.ai.langganan_cli import StatusCli
from anjab_abk_backend.ai.penyedia import AI_EFFORT_BAWAAN, AI_MODEL_BAWAAN
from anjab_abk_backend.ai.redaksi import SumberAi
from anjab_abk_backend.ai.worker import jalankan_satu
from anjab_abk_backend.config import Settings
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, KasusRusak, muat_kasus
from evals.penilai import nilai

_RAIZ = Path(__file__).resolve().parents[1]
_BERKAS_P10 = DEFINISI_FUNGSI["P10"].berkas
_KUNCI_UJI = "kunci-uji-tiruan-q7x9"
_PARAM = {
    "narrative_kind": "F1_FORMAL",
    "instrument_id": "INS_UJI_01",
    "field_key": "praktik_penyusunan_perangkat",
    "periode": "2026-S1",
}
_TEKS = "Guru menyusun perangkat ajar pada awal setiap semester."
_DRAFT = "Guru menyusun perangkat ajar pada awal setiap semester."

# Rujukan yang WAJIB tercakup kasus P10 (body issue #100).
_RUJUKAN_WAJIB = {
    "PRM:72", "R11-003", "R11-011", "R11-015", "R11-016",
    "PRM:91-2", "PRM:91-3", "PRM:91-4", "PRM:91-5",
}  # fmt: skip


def _sha(teks: str) -> str:
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _kasus_dict(id_: str = "k1", **harapan: Any) -> dict[str, Any]:
    h: dict[str, Any] = {
        "jalur": "MODEL",
        "status_qa": ["LOLOS"],
        "harus_memuat": ["perangkat ajar"],
        "dilarang_pola": ["sudah dilaksanakan"],
        "angka_baru_dilarang": True,
    }
    h.update(harapan)
    return {
        "id": id_,
        "rujukan": ["UJI"],
        "kamus_nama": [],
        "sumber": [{"source_id": "s1", "jenis": "SINTETIS", "teks": _TEKS}],
        "parameter": _PARAM,
        "harapan": h,
    }


def _tulis(tmp_path: Path, kasus: list[dict[str, Any]], fungsi: str = "P10") -> Path:
    p = tmp_path / "kasus.json"
    p.write_text(json.dumps({"fungsi": fungsi, "kasus": kasus}), encoding="utf-8")
    return p


def _keluaran(draft: str | None = _DRAFT, status: str = "AI_DRAFT", **isi_ubah: Any) -> str:
    isi: dict[str, Any] = {
        "narrative_kind": "F1_FORMAL",
        "draft_text": draft,
        "claim_to_source_map": [
            {"claim": "k", "source_id": "s1", "span": "menyusun perangkat ajar"}
        ],
        "missing_facts": [],
        "recommended_review_scope": "seluruh draf",
        "label_dokumenter": "DOCUMENTARY_CANDIDATE",
    }
    isi.update(isi_ubah)
    gap = status == "EVIDENCE_GAP"
    return json.dumps(
        {
            "status": status,
            "source_refs": [{"source_id": "s1", "source_hash": _sha(_TEKS)}],
            "cited_spans": [] if gap else [{"source_id": "s1", "span": "menyusun perangkat ajar"}],
            "confidence_reason": "kutipan langsung",
            "unknowns": ["belum ada bukti"] if gap else [],
            "contradictions": [],
            "human_review_required": True,
            "isi": isi,
        }
    )


def _jawab(teks: str | None, masuk: int = 7, keluar: int = 3, stop: str = "end_turn"):
    return JawabanModel(
        teks=teks,
        model_dilayani="model-tiruan",
        stop_reason=stop,
        input_tokens=masuk,
        output_tokens=keluar,
    )


class KlienRekam:
    """Klien tiruan: mengembalikan/melempar respons berurutan, mencatat tiap panggilan."""

    def __init__(self, *respons: JawabanModel | Exception) -> None:
        self.respons = list(respons)
        self.panggilan: list[tuple[str, str, dict[str, Any]]] = []

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan.append((instruksi, masukan_json, skema))
        r = self.respons.pop(0) if len(self.respons) > 1 else self.respons[0]
        if isinstance(r, Exception):
            raise r
        return r


class EnvCatat(dict):
    """Env tiruan yang mencatat setiap kunci yang dibaca harness."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.diakses: list[str] = []

    def get(self, kunci: str, bawaan: Any = None) -> Any:
        self.diakses.append(kunci)
        return super().get(kunci, bawaan)


@pytest.fixture(autouse=True)
def _tanpa_jeda_dan_basis_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hilangkan jeda ulang dan larang harness menyentuh basis data."""
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)

    def _dilarang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("harness evaluasi tidak boleh membuka sesi basis data")

    for nama in ("get_sessionmaker", "session_scope", "get_engine"):
        monkeypatch.setattr(f"anjab_abk_backend.db.{nama}", _dilarang)


def _pasang_api(monkeypatch: pytest.MonkeyPatch, klien: KlienRekam) -> list[dict[str, Any]]:
    dibuat: list[dict[str, Any]] = []

    def _pabrik(settings: Settings, **kw: Any) -> KlienRekam:
        dibuat.append(kw)
        return klien

    monkeypatch.setattr(jalankan, "AnthropicKlienModel", _pabrik)
    return dibuat


def _pasang_cli(
    monkeypatch: pytest.MonkeyPatch, klien: KlienRekam, terpasang: bool = True, masuk: bool = True
) -> list[dict[str, Any]]:
    dibuat: list[dict[str, Any]] = []

    def _pabrik(settings: Settings, **kw: Any) -> KlienRekam:
        dibuat.append(kw)
        return klien

    monkeypatch.setattr(jalankan, "ClaudeCliKlienModel", _pabrik)
    monkeypatch.setattr(
        jalankan, "baca_status_cli", lambda: StatusCli(terpasang=terpasang, masuk=masuk, versi="t")
    )
    return dibuat


def _jalan(
    berkas: Path | None, penyedia: str = "API_ANTHROPIC", env: dict[str, str] | None = None
) -> tuple[int, str, str, list[dict[str, Any]], str]:
    """Jalankan ``main`` dan kembalikan (exit, baris #EVAL, stdout, baris JSON, stderr)."""
    import io

    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P10", "--penyedia", penyedia]
    if berkas is not None:
        argv += ["--kasus", str(berkas)]
    kode = jalankan.main(argv, EnvCatat({"ANTHROPIC_API_KEY": _KUNCI_UJI, **(env or {})}), out, err)
    baris = out.getvalue().splitlines()
    assert baris[-1].startswith("#EVAL "), "#EVAL harus baris terakhir"
    assert sum(1 for b in baris if b.startswith("#EVAL ")) == 1
    laporan = [json.loads(b) for b in baris[:-1]]
    return kode, baris[-1], out.getvalue(), laporan, err.getvalue()


def _eval(baris: str) -> dict[str, str]:
    return dict(p.split("=", 1) for p in baris.split()[1:])


# --- jalur lulus / gagal ---


def test_kasus_lolos_sesuai_harapan_exit_0(tmp_path, monkeypatch) -> None:
    klien = KlienRekam(_jawab(_keluaran()))
    dibuat = _pasang_api(monkeypatch, klien)
    kode, ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [_kasus_dict()]))
    assert kode == 0 and _eval(ev)["exit"] == "0" and _eval(ev)["penyedia"] == "API_ANTHROPIC"
    assert [b["ulangan"] for b in laporan] == [1, 2, 3] and all(b["lulus"] for b in laporan)
    assert len(klien.panggilan) == 3 and len(dibuat) == 1


def test_keluaran_melanggar_dilarang_pola_gagal_exit_1(tmp_path, monkeypatch) -> None:
    _pasang_api(monkeypatch, KlienRekam(_jawab(_keluaran(draft=_DRAFT + " Sudah dilaksanakan."))))
    kode, ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [_kasus_dict()]))
    assert kode == 1 and _eval(ev)["exit"] == "1" and _eval(ev)["kode"] == "GAGAL_PERILAKU"
    assert "DILARANG_POLA:0" in laporan[0]["pelanggaran"]


def test_ulangan_satu_dari_tiga_gagal_kasus_gagal(tmp_path, monkeypatch) -> None:
    baik, buruk = _jawab(_keluaran()), _jawab(_keluaran(draft=_DRAFT + " Sudah dilaksanakan."))
    klien = KlienRekam(baik, buruk, baik)
    _pasang_api(monkeypatch, klien)
    kode, ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [_kasus_dict()]))
    assert [b["lulus"] for b in laporan] == [True, False, True]
    assert kode == 1 and _eval(ev)["kasus_gagal"] == "1" and _eval(ev)["kasus_lulus"] == "0"


def test_karantina_keluaran_dilaporkan_sebagai_pelanggaran(tmp_path, monkeypatch) -> None:
    _pasang_api(monkeypatch, KlienRekam(_jawab("bukan json")))
    kode, _ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [_kasus_dict()]))
    assert kode == 1 and laporan[0]["pelanggaran"] == ["KARANTINA:JSON_TIDAK_SAH"]


# --- penilai ---


def _k(**harapan: Any) -> Kasus:
    return Kasus.model_validate(_kasus_dict(**harapan))


def _isi(**ubah: Any) -> dict[str, Any]:
    return json.loads(_keluaran(**ubah))


def test_angka_tak_ada_di_sumber_pelanggaran_dan_yang_ada_lolos() -> None:
    k = _k()
    assert nilai(
        k, "LOLOS", [], _isi(draft="Guru menyusun perangkat ajar 3 kali per semester.")
    ) == ["ANGKA_BARU:3"]
    assert (
        nilai(k, "LOLOS", [], _isi(draft="Guru menyusun perangkat ajar pada awal setiap semester."))
        == []
    )
    ada = Kasus.model_validate(
        {
            **_kasus_dict(),
            "sumber": [{**_kasus_dict()["sumber"][0], "teks": _TEKS + " Ada 3 berkas."}],
        }
    )
    assert nilai(ada, "LOLOS", [], _isi(draft="Guru menyusun perangkat ajar; 3 berkas.")) == []


def test_kata_bilangan_baru_pelanggaran() -> None:
    p = nilai(
        _k(), "LOLOS", [], _isi(draft="Guru menyusun perangkat ajar dua kali setiap semester.")
    )
    assert p == ["ANGKA_BARU:dua"]


def test_gap_draft_text_harus_null_dan_missing_facts_terisi() -> None:
    k = _k(status_qa=["EVIDENCE_GAP"], harus_memuat=[], angka_baru_dilarang=False)
    assert nilai(k, "EVIDENCE_GAP", [], _isi(draft=None, missing_facts=["x"])) == []
    p = nilai(k, "EVIDENCE_GAP", [], _isi(draft="ada isi", missing_facts=[]))
    assert p == ["DRAFT_TIDAK_NULL_PADA_GAP", "MISSING_FACTS_KOSONG_PADA_GAP"]
    assert nilai(_k(), "LOLOS", [], _isi(draft=None)) == [
        "DRAFT_KOSONG_PADA_DRAF",
        "HARUS_MEMUAT_HILANG:0",
    ]


def test_status_tidak_sesuai_dan_kontradiksi_wajib() -> None:
    k = _k(status_qa=["EVIDENCE_GAP"], kontradiksi_wajib=True, harus_memuat=[])
    p = nilai(k, "LOLOS", [], _isi())
    assert "STATUS_TIDAK_SESUAI:LOLOS" in p and "KONTRADIKSI_KOSONG" in p


def test_pencocokan_menormalkan_spasi_dan_huruf() -> None:
    k = _k(dilarang_pola=["SUDAH   dilaksanakan"], harus_memuat=["PERANGKAT\n ajar"])
    assert nilai(k, "LOLOS", [], _isi(draft="guru: perangkat ajar, sudah dilaksanakan")) == [
        "DILARANG_POLA:0"
    ]


def test_harus_memuat_alternatif_salah_satu_cukup() -> None:
    k = _k(harus_memuat=[["rombel", "rombongan belajar"]], angka_baru_dilarang=False)
    assert nilai(k, "LOLOS", [], _isi(draft="Ada rombongan belajar.")) == []
    assert nilai(k, "LOLOS", [], _isi(draft="Tidak ada.")) == ["HARUS_MEMUAT_HILANG:0"]


# --- TANPA_MODEL: nol panggilan klien ---


def _kasus_tanpa_model() -> list[dict[str, Any]]:
    data = json.loads(_BERKAS_P10.read_text(encoding="utf-8"))
    return [k for k in data["kasus"] if k["harapan"]["jalur"] == "TANPA_MODEL"]


def test_empat_kasus_tanpa_model_nol_panggilan_klien(tmp_path, monkeypatch) -> None:
    tm = _kasus_tanpa_model()
    assert len(tm) == 4
    klien = KlienRekam(_jawab(_keluaran()))
    _pasang_api(monkeypatch, klien)
    kode, ev, _o, laporan, _e = _jalan(_tulis(tmp_path, tm))
    assert kode == 0 and klien.panggilan == []
    assert {b["id"]: b["kode"] for b in laporan} == {
        "p10-tm-sumber-kosong": ["SUMBER_KOSONG"],
        "p10-tm-pii-sintetis": ["PII_DITEMUKAN"],
        "p10-tm-jenis-wcp": ["JENIS_DITOLAK"],
        "p10-tm-metadata-hilang": ["METADATA_SUMBER_HILANG"],
    }
    assert all(b["panggilan_model"] == 0 for b in laporan) and _eval(ev)["panggilan"] == "0"


def test_kasus_tanpa_model_yang_lolos_gerbang_gagal_tanpa_memanggil(tmp_path, monkeypatch) -> None:
    salah = _kasus_dict(jalur="TANPA_MODEL", status_qa=[], alasan_gerbang="SUMBER_KOSONG")
    for kunci in ("harus_memuat", "dilarang_pola", "angka_baru_dilarang"):
        salah["harapan"].pop(kunci)
    klien = KlienRekam(_jawab(_keluaran()))
    _pasang_api(monkeypatch, klien)
    kode, _ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [salah]))
    assert kode == 1 and klien.panggilan == []
    assert laporan[0]["pelanggaran"] == ["GERBANG_TIDAK_SESUAI:LOLOS"]


# --- prasyarat jalur ---


def test_env_kunci_kosong_exit_3_dan_klien_tak_pernah_dibuat(tmp_path, monkeypatch) -> None:
    def _tak_boleh(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien tidak boleh dibuat tanpa kunci")

    monkeypatch.setattr(jalankan, "AnthropicKlienModel", _tak_boleh)
    for env in ({"ANTHROPIC_API_KEY": ""}, {"ANTHROPIC_API_KEY": "   "}):
        kode, ev, _o, laporan, _e = _jalan(_tulis(tmp_path, [_kasus_dict()]), env=env)
        assert kode == 3 and _eval(ev)["exit"] == "3" and _eval(ev)["kode"] == "KUNCI_TIDAK_ADA"
        assert laporan == []


def test_api_meneruskan_kunci_model_effort_eksplisit_tanpa_basis_data(
    tmp_path, monkeypatch
) -> None:
    dibuat = _pasang_api(monkeypatch, KlienRekam(_jawab(_keluaran())))
    kode, ev, *_ = _jalan(
        _tulis(tmp_path, [_kasus_dict()]),
        env={"EVAL_ULANG": "1", "AI_INFERENCE_GEO": "us", "AI_REFUSAL_FALLBACK": "false"},
    )
    assert kode == 0
    assert dibuat == [
        {"kunci_api": _KUNCI_UJI, "model": AI_MODEL_BAWAAN, "effort": AI_EFFORT_BAWAAN}
    ]
    e = _eval(ev)
    assert (e["geo"], e["fallback"], e["model"], e["effort"]) == (
        "us", "false", AI_MODEL_BAWAAN, AI_EFFORT_BAWAAN,
    )  # fmt: skip


def test_langganan_membuat_klien_cli_dan_tak_pernah_membaca_kunci_api(
    tmp_path, monkeypatch
) -> None:
    dibuat = _pasang_cli(monkeypatch, KlienRekam(_jawab(_keluaran())))
    env = EnvCatat({"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"})
    import io

    out = io.StringIO()
    argv = ["--fungsi", "P10", "--penyedia", "LANGGANAN_CLAUDE", "--kasus"]
    kode = jalankan.main([*argv, str(_tulis(tmp_path, [_kasus_dict()]))], env, out, io.StringIO())
    assert kode == 0
    assert dibuat == [{"model": AI_MODEL_BAWAAN, "effort": AI_EFFORT_BAWAAN}]
    assert "ANTHROPIC_API_KEY" not in env.diakses
    assert "penyedia=LANGGANAN_CLAUDE" in out.getvalue().splitlines()[-1]


def test_langganan_belum_masuk_exit_6_dan_binary_tak_ada_exit_7_nol_panggilan(
    tmp_path, monkeypatch
) -> None:
    klien = KlienRekam(_jawab(_keluaran()))
    berkas = _tulis(tmp_path, [_kasus_dict()])
    dibuat = _pasang_cli(monkeypatch, klien, terpasang=True, masuk=False)
    kode, ev, *_ = _jalan(berkas, "LANGGANAN_CLAUDE")
    assert (kode, _eval(ev)["exit"], _eval(ev)["kode"]) == (6, "6", "LANGGANAN_BELUM_MASUK")
    dibuat = _pasang_cli(monkeypatch, klien, terpasang=False, masuk=False)
    kode, ev, *_ = _jalan(berkas, "LANGGANAN_CLAUDE")
    assert (kode, _eval(ev)["exit"], _eval(ev)["kode"]) == (7, "7", "BINARY_CLAUDE_TIDAK_ADA")
    assert klien.panggilan == [] and dibuat == []


def test_langganan_belum_masuk_di_tengah_evaluasi_exit_6_bukan_1(tmp_path, monkeypatch) -> None:
    klien = KlienRekam(LanggananBelumMasuk("x"))
    _pasang_cli(monkeypatch, klien)
    kode, ev, *_ = _jalan(_tulis(tmp_path, [_kasus_dict()]), "LANGGANAN_CLAUDE")
    assert (kode, _eval(ev)["kode"]) == (6, "LANGGANAN_BELUM_MASUK")


# --- galat model ---


def test_galat_sementara_berulang_exit_4_bukan_1(tmp_path, monkeypatch) -> None:
    klien = KlienRekam(KesalahanModelSementara("x"))
    _pasang_api(monkeypatch, klien)
    kode, ev, *_ = _jalan(_tulis(tmp_path, [_kasus_dict()]))
    assert (kode, _eval(ev)["kode"]) == (4, "TAK_KONKLUSIF")
    assert len(klien.panggilan) == 3  # satu percobaan + dua ulangan


def test_galat_sementara_sekali_lalu_berhasil_tidak_mengganggu(tmp_path, monkeypatch) -> None:
    klien = KlienRekam(KesalahanModelSementara("x"), _jawab(_keluaran()))
    _pasang_api(monkeypatch, klien)
    kode, *_ = _jalan(_tulis(tmp_path, [_kasus_dict()]), env={"EVAL_ULANG": "1"})
    assert kode == 0


@pytest.mark.parametrize(
    ("penyedia", "kode_harapan"),
    [("API_ANTHROPIC", "SKEMA_DITOLAK_API"), ("LANGGANAN_CLAUDE", "CLI_GAGAL_PERMANEN")],
)
def test_galat_permanen_exit_5_dengan_kode_sesuai_jalur(
    tmp_path, monkeypatch, penyedia: str, kode_harapan: str
) -> None:
    klien = KlienRekam(KesalahanModelPermanen("x"))
    _pasang_api(monkeypatch, klien)
    _pasang_cli(monkeypatch, klien)
    kode, ev, *_ = _jalan(_tulis(tmp_path, [_kasus_dict()]), penyedia)
    assert (kode, _eval(ev)["kode"]) == (5, kode_harapan)
    assert len(klien.panggilan) == 1  # tidak diulang


def test_batas_token_tercapai_exit_4_dan_berhenti_memanggil(tmp_path, monkeypatch) -> None:
    klien = KlienRekam(_jawab(_keluaran(), masuk=6, keluar=4))
    _pasang_api(monkeypatch, klien)
    kode, ev, *_ = _jalan(_tulis(tmp_path, [_kasus_dict()]), env={"EVAL_MAKS_TOKEN": "10"})
    assert (kode, _eval(ev)["kode"]) == (4, "BATAS_TOKEN")
    assert len(klien.panggilan) == 1 and _eval(ev)["token"] == "10"


# --- argumen / kasus rusak, #EVAL selalu tercetak ---


def test_jenis_dokumen_resmi_di_kasus_exit_2(tmp_path, monkeypatch) -> None:
    bad = _kasus_dict()
    bad["sumber"][0]["jenis"] = "DOKUMEN_RESMI"
    _pasang_api(monkeypatch, KlienRekam(_jawab(_keluaran())))
    kode, ev, _o, _l, err = _jalan(_tulis(tmp_path, [bad]))
    assert (kode, _eval(ev)["kode"]) == (2, "KASUS_RUSAK") and "DOKUMEN_RESMI" in err


def test_jenis_berawalan_wcp_hanya_sah_untuk_kasus_penolakan_jenis(tmp_path) -> None:
    bad = _kasus_dict()
    bad["sumber"][0]["jenis"] = "WCP_JAWABAN"  # kasus MODEL: tidak diizinkan
    with pytest.raises(KasusRusak):
        muat_kasus(_tulis(tmp_path, [bad]), "P10", DEFINISI_FUNGSI["P10"])


@pytest.mark.parametrize(
    "argv",
    [
        ["--fungsi", "P10", "--penyedia", "NGAWUR"],
        ["--fungsi", "P10"],
        ["--fungsi", "X9", "--penyedia", "API_ANTHROPIC"],
        [],
    ],
)
def test_argumen_rusak_exit_2_dan_eval_tercetak(argv: list[str]) -> None:
    import io

    out = io.StringIO()
    kode = jalankan.main(argv, EnvCatat(), out, io.StringIO())
    assert kode == 2 and out.getvalue().splitlines()[-1].startswith("#EVAL ")
    assert _eval(out.getvalue().splitlines()[-1])["exit"] == "2"


def test_nilai_penyedia_berbahaya_tidak_mengotori_baris_eval() -> None:
    import io

    out = io.StringIO()
    jalankan.main(
        ["--fungsi", "P10", "--penyedia", "A B\n#EVAL exit=0"], EnvCatat(), out, io.StringIO()
    )
    assert out.getvalue().count("#EVAL") == 1


def test_env_ulang_dan_token_tidak_sah_exit_2() -> None:
    for env in ({"EVAL_ULANG": "nol"}, {"EVAL_ULANG": "0"}, {"EVAL_MAKS_TOKEN": "-5"}):
        import io

        out = io.StringIO()
        argv = ["--fungsi", "P10", "--penyedia", "API_ANTHROPIC"]
        assert jalankan.main(argv, EnvCatat(env), out, io.StringIO()) == 2
        assert out.getvalue().splitlines()[-1].startswith("#EVAL ")


def test_galat_tak_terduga_tetap_mencetak_eval(monkeypatch) -> None:
    def _meledak(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("rahasia-yang-tak-boleh-bocor")

    monkeypatch.setattr(jalankan, "muat_kasus", _meledak)
    kode, ev, out, _l, err = _jalan(None)
    assert (kode, _eval(ev)["kode"]) == (2, "GALAT_TAK_TERDUGA")
    assert "rahasia-yang-tak-boleh-bocor" not in out + err and "RuntimeError" in err


def test_kunci_tidak_pernah_muncul_di_stdout_maupun_stderr(tmp_path, monkeypatch, capsys) -> None:
    _pasang_api(monkeypatch, KlienRekam(_jawab(_keluaran())))
    env = EnvCatat({"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"})
    berkas = _tulis(tmp_path, [_kasus_dict()])
    kode = jalankan.main(
        ["--fungsi", "P10", "--penyedia", "API_ANTHROPIC", "--kasus", str(berkas)], env
    )
    cap = capsys.readouterr()
    assert kode == 0 and _KUNCI_UJI not in cap.out + cap.err
    assert re.search(r"^#EVAL penyedia=API_ANTHROPIC ", cap.out.splitlines()[-1])


# --- kasus P10 ---


def test_kasus_p10_memuat_seluruh_rujukan_wajib_dan_jumlah_minimum() -> None:
    kasus = muat_kasus(_BERKAS_P10, "P10", DEFINISI_FUNGSI["P10"])
    rujukan = {r for k in kasus for r in k.rujukan}
    assert _RUJUKAN_WAJIB <= rujukan
    tanpa = [k for k in kasus if k.harapan.jalur == "TANPA_MODEL"]
    assert len(tanpa) == 4 and len(kasus) - len(tanpa) >= 13
    assert len({k.id for k in kasus}) == len(kasus)


def test_kasus_p10_perilaku_gerbang_sesuai_harapan() -> None:
    settings = Settings(
        _env_file=None, ai_jenis_sumber_diizinkan=["SINTETIS"], ai_pii_mode="BLOKIR"
    )
    for k in muat_kasus(_BERKAS_P10, "P10", DEFINISI_FUNGSI["P10"]):
        alasan, _ = jalankan._gerbang(k, settings)
        if k.harapan.jalur == "TANPA_MODEL":
            assert alasan == k.harapan.alasan_gerbang, k.id
        else:
            assert alasan is None, f"{k.id} diblok gerbang: {alasan}"


def test_kasus_p10_fiktif_dan_sintetis_tanpa_alamat_riil() -> None:
    teks = _BERKAS_P10.read_text(encoding="utf-8")
    assert "@contoh.example" in teks and "https://" not in teks and "http://" not in teks
    for k in muat_kasus(_BERKAS_P10, "P10", DEFINISI_FUNGSI["P10"]):
        assert all(s.jenis == "SINTETIS" or k.harapan.jalur == "TANPA_MODEL" for s in k.sumber)


# --- struktur ---


def test_test_di_makefile_tidak_bergantung_pada_eval_ai() -> None:
    mf = (_RAIZ / "Makefile").read_text(encoding="utf-8")
    dep = re.search(r"^test:\s*(.*)$", mf, re.M)
    assert dep is not None and "eval" not in dep.group(1)
    for target in ("lint", "unit", "build"):
        d = re.search(rf"^{target}:\s*(.*)$", mf, re.M)
        assert d is not None and "eval" not in d.group(1)
    assert "eval-ai" in mf


def test_workflow_github_tidak_memanggil_eval_ai() -> None:
    wf = _RAIZ / ".github" / "workflows"
    if not wf.is_dir():  # .github dikecualikan dari image test; dijaga juga lewat git grep
        return
    for berkas in wf.iterdir():
        assert "eval-ai" not in berkas.read_text(encoding="utf-8"), berkas.name


def test_evals_tidak_masuk_paket_produksi() -> None:
    teks = (_RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert 'packages = ["src/anjab_abk_backend"]' in teks
    dockerfile = (_RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "evals" not in dockerfile


# --- paritas perakitan masukan dengan worker (DB) ---


@pytest.mark.usefixtures("penyedia_api")
def test_masukan_harness_identik_dengan_yang_dikirim_worker(
    db_session: Session, tmp_path, monkeypatch
) -> None:
    """Instruksi, masukan JSON, dan skema yang dikirim harness sama dengan worker."""
    kasus_p10 = muat_kasus(_BERKAS_P10, "P10", DEFINISI_FUNGSI["P10"])
    kasus = next(k for k in kasus_p10 if k.id == "p10-m-dua-sumber-bertentangan")
    data = json.loads(_BERKAS_P10.read_text(encoding="utf-8"))
    mentah = next(k for k in data["kasus"] if k["id"] == kasus.id)

    klien_h = KlienRekam(_jawab("bukan json"))
    _pasang_api(monkeypatch, klien_h)
    _jalan(_tulis(tmp_path, [mentah]), env={"EVAL_ULANG": "1"})
    assert len(klien_h.panggilan) == 1

    settings = Settings(_env_file=None, feature_ai_narrative_draft=True)
    sumber = [SumberAi(s.source_id, _sha(s.teks), s.jenis, s.teks) for s in kasus.sumber]
    reg = {"P10": FUNGSI_P10}
    AiGateway(db_session, settings, registri=reg).ajukan(
        "P10", sumber, kasus.parameter, "r1", "uji"
    )
    klien_w = KlienRekam(_jawab("bukan json"))

    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    assert jalankan_satu(_fab, settings, lambda: klien_w, reg) is not None
    assert len(klien_w.panggilan) == 1
    assert klien_h.panggilan[0] == klien_w.panggilan[0]
