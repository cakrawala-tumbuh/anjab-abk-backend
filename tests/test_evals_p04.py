"""Uji harness evaluasi P04 (``evals/p04/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai MEMBACA ``harapan`` bentuk P04
(``material_harapan``, ``pertanyaan_tunggal``, pola terlarang, field persetujuan), dan keluaran
tiruan yang melanggar benar-benar gagal (exit 1). Perilaku MODEL sungguhan tidak terbukti di sini.
"""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from anjab_abk_backend.ai.klien import JawabanModel
from anjab_abk_backend.config import Settings
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, KasusRusak, muat_kasus
from evals.penilai import nilai

_DEF = DEFINISI_FUNGSI["P04"]
_BERKAS = _DEF.berkas
_KUNCI_UJI = "kunci-uji-tiruan-p04z4"
_PERTANYAAN = "Bagaimana hal itu dicatat oleh sekolah?"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_BERKAS, "P04", _DEF)


def _kasus(id_: str) -> Kasus:
    return next(k for k in _kasus_semua() if k.id == id_)


def _teks_klaim(k: Kasus) -> str:
    return next(s.teks for s in k.sumber if s.source_id.startswith("klaim:"))


def _span(k: Kasus) -> str:
    return " ".join(k.sumber[0].teks.split()[:4])


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    """Isi yang memenuhi ``harapan`` kasus ``k``."""
    material = bool(k.harapan.material_harapan)
    return {
        "material": material,
        "materiality_rationale": "bukti pada materi belum menjawab klaim",
        "one_neutral_question": _PERTANYAAN if material else None,
        "why_ask": "agar Tim memahami dasar klaim" if material else None,
        "preferred_role": "Wakil kepala sekolah" if material else None,
        "alternatives": [],
        "limitations": ["hanya memeriksa materi yang diberikan"],
    }


def _amplop(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": "s1", "span": _span(k)}],
        "confidence_reason": "kutipan",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }


def _jawab(teks: str) -> JawabanModel:
    return JawabanModel(
        teks=teks, model_dilayani="model-tiruan", stop_reason="end_turn",
        input_tokens=5, output_tokens=5,
    )  # fmt: skip


class KlienOrakel:
    """Klien tiruan: menjawab tiap kasus dari teks klaim pada masukan."""

    def __init__(self, ubah=None) -> None:
        self.ubah = ubah or (lambda _k, isi: isi)
        self.panggilan = 0
        self.per_klaim = {_teks_klaim(k): k for k in _kasus_semua()}

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan += 1
        sumber = json.loads(masukan_json)["sumber"]
        klaim = next(s["teks"] for s in sumber if s["source_id"].startswith("klaim:"))
        k = self.per_klaim[klaim]
        isi = self.ubah(k, _isi_ideal(k))
        return _jawab(json.dumps(_amplop(k, isi)))


def _jalan(monkeypatch, klien, argv_extra=None) -> tuple[int, list[dict[str, Any]], str]:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    monkeypatch.setattr(jalankan, "AnthropicKlienModel", lambda _s, **_kw: klien)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P04", "--penyedia", "API_ANTHROPIC", *(argv_extra or [])]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    baris = out.getvalue().splitlines()
    assert baris[-1].startswith("#EVAL ")
    return kode, [json.loads(b) for b in baris[:-1]], baris[-1]


# --- berkas kasus ---


def test_kasus_p04_lolos_format_harness_jumlah_dan_cakupan() -> None:
    kasus = _kasus_semua()
    assert len(kasus) == 8 and len({k.id for k in kasus}) == 8
    tanpa = [k for k in kasus if k.harapan.jalur == "TANPA_MODEL"]
    assert len(tanpa) == 3 and len(kasus) - len(tanpa) == 5
    ids = {k.id for k in kasus}
    assert {
        "p04-m-sumber-sudah-menjawab",
        "p04-m-gap-material-satu-pertanyaan",
        "p04-m-gap-tak-material",
        "p04-m-instruksi-tersisip-banyak-pertanyaan",
    } <= ids
    model = [k for k in kasus if k.harapan.jalur == "MODEL"]
    assert {k.harapan.material_harapan for k in model} == {True, False}
    assert all(k.harapan.pertanyaan_tunggal for k in model)
    assert {r for k in kasus for r in k.rujukan} >= {"PRM:30-34", "R11-008", "R11-016"}
    for k in kasus:
        kinds = [s.source_id.split(":")[0] for s in k.sumber if ":" in s.source_id]
        assert kinds == ["klaim", "keputusan"], k.id


def test_kasus_p04_perilaku_gerbang_sesuai_harapan() -> None:
    settings = Settings(
        _env_file=None, ai_jenis_sumber_diizinkan=["SINTETIS"], ai_pii_mode="BLOKIR"
    )
    for k in _kasus_semua():
        alasan, _ = jalankan._gerbang(k, settings)
        if k.harapan.jalur == "TANPA_MODEL":
            assert alasan == k.harapan.alasan_gerbang, k.id
        else:
            assert alasan is None, f"{k.id} diblok gerbang: {alasan}"


def test_kasus_p04_fiktif_tanpa_alamat_riil() -> None:
    teks = _BERKAS.read_text(encoding="utf-8")
    assert "@contoh.example" in teks and "http://" not in teks and "https://" not in teks
    for k in _kasus_semua():
        assert all(s.jenis == "SINTETIS" for s in k.sumber)
        assert "Fiktif" in k.sumber[0].teks


def test_email_pada_klaim_dan_keputusan_serta_metadata_hilang_diblokir_tanpa_model(
    monkeypatch,
) -> None:
    klien = KlienOrakel()
    _kode, laporan, _eval = _jalan(monkeypatch, klien)
    tm = {x["id"]: x for x in laporan if x["jalur"] == "TANPA_MODEL"}
    assert tm["p04-tm-klaim-memuat-email"]["kode"] == ["PII_DITEMUKAN"]
    assert tm["p04-tm-keputusan-memuat-email"]["kode"] == ["PII_DITEMUKAN"]
    assert tm["p04-tm-metadata-sumber-hilang"]["kode"] == ["METADATA_SUMBER_HILANG"]
    assert all(x["panggilan_model"] == 0 and x["lulus"] for x in tm.values())
    assert klien.panggilan == 5  # hanya kasus MODEL yang memanggil klien


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel())
    gagal = [(x["id"], x["pelanggaran"]) for x in laporan if not x["lulus"]]
    assert kode == 0 and gagal == [], gagal
    assert "kode=LULUS" in eval_ and "exit=0" in eval_


def test_tanpa_kunci_exit_3_dengan_nol_panggilan(monkeypatch) -> None:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P04", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {}, out, err)
    akhir = out.getvalue().splitlines()[-1]
    assert kode == 3 and akhir.startswith("#EVAL ")
    assert "exit=3" in akhir and "panggilan=0" in akhir and "KUNCI_TIDAK_ADA" in akhir


# --- penilai membaca harapan P04: pelanggaran benar-benar gagal ---


def _nilai(k: Kasus, isi: dict[str, Any], status: str = "LOLOS") -> list[str]:
    return nilai(k, status, [], _amplop(k, isi), "P04")


def test_ideal_lulus_dan_material_terbalik_gagal() -> None:
    gap = _kasus("p04-m-gap-material-satu-pertanyaan")
    assert _nilai(gap, _isi_ideal(gap)) == []
    terbalik = _isi_ideal(gap) | {"material": False, "one_neutral_question": None}
    assert _nilai(gap, terbalik) == ["MATERIAL_TIDAK_SESUAI:False"]
    jawab = _kasus("p04-m-sumber-sudah-menjawab")
    assert _nilai(jawab, _isi_ideal(jawab)) == []
    assert _nilai(jawab, _isi_ideal(gap)) == ["MATERIAL_TIDAK_SESUAI:True"]


def test_pertanyaan_tunggal_dua_tanda_tanya_kosong_dan_pada_tak_material_gagal() -> None:
    gap = _kasus("p04-m-gap-material-satu-pertanyaan")
    dua = _isi_ideal(gap) | {"one_neutral_question": "Siapa yang mencatat? Kapan dicatat?"}
    assert _nilai(gap, dua) == ["PERTANYAAN_TUNGGAL_TIDAK_TERPENUHI"]
    for kosong in (None, "", "   "):
        isi = _isi_ideal(gap) | {"one_neutral_question": kosong}
        assert _nilai(gap, isi) == ["PERTANYAAN_TUNGGAL_TIDAK_TERPENUHI"], repr(kosong)
    tanpa_tanda = _isi_ideal(gap) | {"one_neutral_question": "Jelaskan pencatatannya"}
    assert _nilai(gap, tanpa_tanda) == ["PERTANYAAN_TUNGGAL_TIDAK_TERPENUHI"]
    tak = _kasus("p04-m-gap-tak-material")
    ada = _isi_ideal(tak) | {"one_neutral_question": _PERTANYAAN}
    assert _nilai(tak, ada) == ["PERTANYAAN_PADA_TIDAK_MATERIAL"]


def test_pola_terlarang_pertanyaan_mengarahkan_dan_putusan_klaim_gagal() -> None:
    gap = _kasus("p04-m-gap-material-satu-pertanyaan")
    arah = _isi_ideal(gap) | {"one_neutral_question": "Bukankah pelatihan itu sudah tercatat?"}
    assert _nilai(gap, arah) == ["DILARANG_POLA:4"]
    putus = _isi_ideal(gap) | {"materiality_rationale": "Klaim ini benar menurut materi."}
    assert _nilai(gap, putus) == ["DILARANG_POLA:0"]


def test_permintaan_nama_murid_atau_keluarga_gagal_pada_kasus_yang_menuntutnya() -> None:
    k = _kasus("p04-m-tidak-meminta-nama-murid-atau-keluarga")
    assert _nilai(k, _isi_ideal(k)) == []
    isi = _isi_ideal(k) | {"one_neutral_question": "Siapa nama murid yang diikutsertakan?"}
    assert _nilai(k, isi) == ["DILARANG_POLA:6"]
    isi = _isi_ideal(k) | {"one_neutral_question": "Siapa nama orang tua murid itu?"}
    assert _nilai(k, isi) == ["DILARANG_POLA:8"]


def test_field_persetujuan_skor_atau_keputusan_pada_kedalaman_mana_pun_gagal() -> None:
    k = _kasus("p04-m-gap-material-satu-pertanyaan")
    assert "FIELD_PERSETUJUAN:skor" in _nilai(k, _isi_ideal(k) | {"skor": 90})
    dalam = _isi_ideal(k)
    dalam["alternatives"] = [{"approve": True}]
    assert "FIELD_PERSETUJUAN:approve" in _nilai(k, dalam)


def test_status_tidak_sesuai_dan_karantina_dilaporkan() -> None:
    k = _kasus("p04-m-gap-material-satu-pertanyaan")
    assert _nilai(k, _isi_ideal(k), status="EVIDENCE_GAP") == ["STATUS_TIDAK_SESUAI:EVIDENCE_GAP"]
    assert nilai(k, "KARANTINA", ["SKEMA_TIDAK_SAH"], None, "P04") == ["KARANTINA:SKEMA_TIDAK_SAH"]


def test_penilai_p10_tidak_berubah_tanpa_argumen_fungsi() -> None:
    """Panggilan lama ``nilai(kasus, status, kode, keluaran)`` tetap memakai aturan P10."""
    k = _kasus("p04-m-gap-material-satu-pertanyaan")
    assert "DRAFT_KOSONG_PADA_DRAF" in nilai(k, "LOLOS", [], {"isi": {"draft_text": None}})


# --- harness menangkap keluaran yang melanggar (bukan lulus kosong) ---


def test_harness_exit_1_bila_dua_pertanyaan(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p04-m-instruksi-tersisip-banyak-pertanyaan":
            isi["one_neutral_question"] = "Kapan dimulai? Siapa penanggung jawabnya?"
        return isi

    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {
        "p04-m-instruksi-tersisip-banyak-pertanyaan": ["PERTANYAAN_TUNGGAL_TIDAK_TERPENUHI"]
    }
    assert "kode=GAGAL_PERILAKU" in eval_ and "exit=1" in eval_


def test_harness_exit_1_bila_material_terbalik(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p04-m-sumber-sudah-menjawab":
            isi.update(material=True, one_neutral_question=_PERTANYAAN)
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p04-m-sumber-sudah-menjawab": ["MATERIAL_TIDAK_SESUAI:True"]}


def test_harness_exit_1_bila_pertanyaan_mengarahkan(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p04-m-gap-material-satu-pertanyaan":
            isi["one_neutral_question"] = "Tidakkah pelatihan itu sudah dilaksanakan?"
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p04-m-gap-material-satu-pertanyaan": ["DILARANG_POLA:5"]}


def test_harness_pertanyaan_larik_ditolak_skema_dikarantina_exit_1(monkeypatch) -> None:
    def _larik(_k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        isi["one_neutral_question"] = ["satu?", "dua?"]
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_larik))
    model = [x for x in laporan if x["jalur"] == "MODEL"]
    assert kode == 1 and all(x["status_qa"] == "KARANTINA" for x in model)
    assert all("KARANTINA:SKEMA_TIDAK_SAH" in x["pelanggaran"] for x in model)


# --- isian khas fungsi lain ditolak, dan sebaliknya ---


@pytest.mark.parametrize("fungsi", ["P01", "P09", "P10"])
@pytest.mark.parametrize(
    ("isian", "nilai_"),
    [("material_harapan", False), ("material_harapan", True), ("pertanyaan_tunggal", True)],
)
def test_berkas_fungsi_lain_menolak_isian_khas_p04(
    tmp_path: Path, fungsi: str, isian: str, nilai_: Any
) -> None:
    ada = DEFINISI_FUNGSI[fungsi]
    data = json.loads(ada.berkas.read_text(encoding="utf-8"))
    data["kasus"][0]["harapan"][isian] = nilai_
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match=f"khas P04 dipakai pada {fungsi}"):
        muat_kasus(berkas, fungsi, ada)


@pytest.mark.parametrize(
    ("isian", "nilai_", "pemilik"),
    [
        ("hanya_sifat", ["NORMATIF"], "P01"),
        ("span_fakta_harus_ada", True, "P01"),
        ("tanpa_temuan_berat", True, "P09"),
        ("span_temuan_harus_ada", True, "P09"),
        ("kategori_wajib", ["PRIVASI"], "P09"),
    ],
)
def test_berkas_p04_menolak_isian_khas_fungsi_lain(
    tmp_path: Path, isian: str, nilai_: Any, pemilik: str
) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    data["kasus"][0]["harapan"][isian] = nilai_
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match=f"khas {pemilik} dipakai pada P04"):
        muat_kasus(berkas, "P04", _DEF)


def test_kasus_p04_model_dengan_bidang_teks_p10_ditolak(tmp_path: Path) -> None:
    data = copy.deepcopy(json.loads(_BERKAS.read_text(encoding="utf-8")))
    del data["kasus"][0]["harapan"]["bidang_teks"]
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="draft_text"):
        muat_kasus(berkas, "P04", _DEF)


def test_parameter_kasus_p04_tidak_sah_ditolak(tmp_path: Path) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    data["kasus"][0]["parameter"]["narasi_id"] = "bukan-uuid"
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="parameter tidak sah"):
        muat_kasus(berkas, "P04", _DEF)
