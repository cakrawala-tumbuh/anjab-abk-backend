"""Penilai deterministik keluaran model: tanpa model penilai, tanpa jaringan.

Menilai hasil ``cek_keluaran`` terhadap ``HarapanKasus``. Pencocokan frasa menormalkan
spasi dan huruf besar-kecil. Yang TIDAK dapat dinilai di sini (makna parafrasa, kelayakan
isi bagi reviewer) tetap tugas manusia.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .kasus import Kasus

__all__ = ["KATA_BILANGAN", "bilangan_dalam", "nilai", "normalkan"]

_RE_SPASI = re.compile(r"\s+")
_RE_ANGKA = re.compile(r"\d+(?:[.,]\d+)*")
_RE_KATA = re.compile(r"[a-z]+")

KATA_BILANGAN = frozenset(
    {
        "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh",
        "sebelas", "belas", "puluh", "ratus", "ribu", "juta",
    }
)  # fmt: skip
"""Kata bilangan Indonesia yang diperiksa sebagai "angka baru". ``satu`` sengaja tidak
termasuk: terlalu sering berarti "sebuah" (mis. "satu semester") dan menimbulkan
positif palsu."""


def normalkan(teks: str) -> str:
    """Normalkan untuk pencocokan: huruf kecil, spasi beruntun menjadi satu, tepi dipangkas."""
    return _RE_SPASI.sub(" ", teks).strip().casefold()


def bilangan_dalam(teks: str) -> set[str]:
    """Kumpulkan token bilangan (angka dan kata bilangan) dari ``teks`` ternormalisasi.

    Args:
        teks: Teks bebas.

    Returns:
        Himpunan token: deret angka (``30``, ``2,5``) dan kata di ``KATA_BILANGAN``.
    """
    n = normalkan(teks)
    return set(_RE_ANGKA.findall(n)) | {k for k in _RE_KATA.findall(n) if k in KATA_BILANGAN}


def _ambil(keluaran: dict[str, Any], jalur: str) -> str:
    """Ambil teks pada jalur titik; daftar digabung spasi; hilang/``None`` menjadi ``""``."""
    nilai_: Any = keluaran
    for bagian in jalur.split("."):
        if not isinstance(nilai_, dict) or bagian not in nilai_:
            return ""
        nilai_ = nilai_[bagian]
    if nilai_ is None:
        return ""
    if isinstance(nilai_, list):
        return " ".join(str(x) for x in nilai_)
    return str(nilai_)


def _ada(frasa: str, teks_norm: str) -> bool:
    """Apakah ``frasa`` (dinormalkan) merupakan potongan ``teks_norm``."""
    return normalkan(frasa) in teks_norm


def _sumber_bilangan(kasus: Kasus) -> set[str]:
    """Bilangan yang sah muncul: dari teks sumber dan nilai parameter."""
    bahan: Iterable[str] = [s.teks for s in kasus.sumber]
    param = [str(v) for v in kasus.parameter.values()]
    sah: set[str] = set()
    for t in [*bahan, *param]:
        sah |= bilangan_dalam(t)
    return sah


KATA_FIELD_TERLARANG_P09 = ("approve", "setuju", "skor")
"""Potongan nama field yang tidak boleh ada di ``isi`` P09 pada kedalaman mana pun."""


def _nama_field(obj: Any):
    """Telusuri nama kunci objek secara rekursif (kamus dan daftar bersarang)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _nama_field(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _nama_field(v)


def _temuan(isi: dict[str, Any]) -> list[dict[str, Any]]:
    """Gabungkan ``blocking_findings`` dan ``major_findings`` yang berbentuk objek."""
    hasil: list[dict[str, Any]] = []
    for kunci in ("blocking_findings", "major_findings"):
        daftar = isi.get(kunci)
        if isinstance(daftar, list):
            hasil.extend(x for x in daftar if isinstance(x, dict))
    return hasil


def _nilai_p09(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P09: peran, tanpa field persetujuan, kategori, draf bersih, dan span."""
    h = kasus.harapan
    pel: list[str] = []
    if status_qa not in h.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    if isi.get("peran") != "REVIEWER_OTOMATIS_PEMBANTU":
        pel.append("PERAN_SALAH")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    temuan = _temuan(isi)
    if h.tanpa_temuan_berat and temuan:
        pel.append("TEMUAN_PADA_DRAF_BERSIH")
    kategori = {str(t.get("kategori")) for t in temuan}
    for i, pilihan in enumerate(h.kategori_wajib):
        alternatif = [pilihan] if isinstance(pilihan, str) else pilihan
        if not kategori & set(alternatif):
            pel.append(f"KATEGORI_WAJIB_HILANG:{i}")
    if h.span_temuan_harus_ada:
        teks_sumber = {s.source_id: normalkan(s.teks) for s in kasus.sumber}
        for i, t in enumerate(temuan):
            span = normalkan(str(t.get("span", "")))
            asal = teks_sumber.get(str(t.get("source_id")))
            if not span or asal is None or span not in asal:
                pel.append(f"SPAN_TEMUAN_TIDAK_DITEMUKAN:{i}")
    return pel


def nilai(
    kasus: Kasus,
    status_qa: str,
    kode: list[str],
    keluaran: dict[str, Any] | None,
    kode_fungsi: str = "P10",
) -> list[str]:
    """Nilai satu keluaran model untuk kasus berjalur ``MODEL``.

    Args:
        kasus: Kasus yang dinilai.
        status_qa: ``LOLOS``, ``EVIDENCE_GAP``, atau ``KARANTINA`` (dari evaluasi worker).
        kode: Kode karantina bila ``KARANTINA``.
        keluaran: Keluaran hasil parse; ``None`` bila karantina.
        kode_fungsi: ``P10`` (bawaan, perilaku lama tak berubah) atau ``P09``.

    Returns:
        Daftar kode pelanggaran; kosong berarti lulus. Kode tidak memuat teks keluaran,
        kecuali token bilangan pada ``ANGKA_BARU``.
    """
    h = kasus.harapan
    if status_qa == "KARANTINA" or keluaran is None:
        return [f"KARANTINA:{k}" for k in kode] or ["KARANTINA"]
    pelanggaran: list[str] = []
    isi = keluaran.get("isi", {})
    if kode_fungsi == "P09":
        pelanggaran.extend(_nilai_p09(kasus, status_qa, isi))
    else:
        if status_qa not in h.status_qa:
            pelanggaran.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
        draft = isi.get("draft_text")
        if status_qa == "LOLOS" and not (isinstance(draft, str) and draft.strip()):
            pelanggaran.append("DRAFT_KOSONG_PADA_DRAF")
        if status_qa == "EVIDENCE_GAP":
            if draft is not None:
                pelanggaran.append("DRAFT_TIDAK_NULL_PADA_GAP")
            if not any(str(x).strip() for x in isi.get("missing_facts", [])):
                pelanggaran.append("MISSING_FACTS_KOSONG_PADA_GAP")

    teks = normalkan(" ".join(_ambil(keluaran, b) for b in h.bidang_teks))
    for i, pola in enumerate(h.dilarang_pola):
        if _ada(pola, teks):
            pelanggaran.append(f"DILARANG_POLA:{i}")
    for i, pilihan in enumerate(h.harus_memuat):
        alternatif = [pilihan] if isinstance(pilihan, str) else pilihan
        if not any(_ada(a, teks) for a in alternatif):
            pelanggaran.append(f"HARUS_MEMUAT_HILANG:{i}")
    if h.angka_baru_dilarang:
        baru = sorted(bilangan_dalam(teks) - _sumber_bilangan(kasus))
        pelanggaran.extend(f"ANGKA_BARU:{b}" for b in baru)
    if h.kontradiksi_wajib and not any(str(c).strip() for c in keluaran.get("contradictions", [])):
        pelanggaran.append("KONTRADIKSI_KOSONG")
    return pelanggaran
