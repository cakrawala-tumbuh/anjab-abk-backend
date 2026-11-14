"""Penilai deterministik keluaran model: tanpa model penilai, tanpa jaringan.

Menilai hasil ``cek_keluaran`` terhadap ``HarapanKasus``. Pencocokan frasa menormalkan
spasi dan huruf besar-kecil. Yang TIDAK dapat dinilai di sini (makna parafrasa, kelayakan
isi bagi reviewer) tetap tugas manusia.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from anjab_abk_backend.ai.fungsi_p06 import KODE_ANGKA_FTE, KODE_STATUS_TERLARANG, aturan_p06
from anjab_abk_backend.ai.fungsi_p07 import aturan_p07
from anjab_abk_backend.ai.fungsi_p08 import aturan_p08
from anjab_abk_backend.ai.fungsi_p11 import aturan_p11

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


def _kumpul(nilai_: Any, bagian: list[str]) -> list[str]:
    """Kumpulkan teks pada jalur ``bagian``; daftar di tengah jalur dijelajahi per elemen."""
    if nilai_ is None:
        return []
    if not bagian:
        return [str(x) for x in nilai_] if isinstance(nilai_, list) else [str(nilai_)]
    if isinstance(nilai_, list):
        return [t for x in nilai_ for t in _kumpul(x, bagian)]
    if not isinstance(nilai_, dict) or bagian[0] not in nilai_:
        return []
    return _kumpul(nilai_[bagian[0]], bagian[1:])


def _ambil(keluaran: dict[str, Any], jalur: str) -> str:
    """Ambil teks pada jalur titik; daftar digabung spasi; hilang/``None`` menjadi ``""``.

    Bila ada daftar objek di tengah jalur (mis. ``isi.factual_extracts.fakta``), bidang itu
    diambil dari setiap elemen.
    """
    return " ".join(_kumpul(keluaran, jalur.split(".")))


def _ada(frasa: str, teks_norm: str) -> bool:
    """Apakah ``frasa`` (dinormalkan) merupakan potongan ``teks_norm``."""
    return normalkan(frasa) in teks_norm


def _tanpa_dikecualikan(teks_norm: str, dikecualikan: list[str]) -> str:
    """Hapus setiap kemunculan frasa sah (``pola_dikecualikan``) dari ``teks_norm``.

    Args:
        teks_norm: Teks ternormalisasi.
        dikecualikan: Frasa sah; dinormalkan sebelum dicari. Kosong = teks tak berubah.

    Returns:
        Teks sisa, tempat ``dilarang_pola`` dicocokkan; tiap kemunculan diganti satu spasi
        agar kata di kiri-kanannya tak menyatu.
    """
    for frasa in dikecualikan:
        norm = normalkan(frasa)
        if norm:
            teks_norm = teks_norm.replace(norm, " ")
    return teks_norm


_BATAS_KATA_PENYANGKAL = 15
_KATA_PEMUTUS = frozenset({"tetapi", "namun", "melainkan", "sedangkan", "padahal"})
_RE_BATAS_KALIMAT = re.compile(r"[.!?;\n]")
_RE_BILANGAN_PENGHITUNG = re.compile(
    r"(?:\b(?:" + "|".join(sorted(KATA_BILANGAN)) + r")\b\s+)+(?=(?:sumber|kalimat)\b)"
)


def _tersangkal(kalimat: str, awal: int, penyangkal: list[str]) -> bool:
    """Apakah pola yang dimulai pada ``awal`` disangkal dalam ``kalimat`` (ternormalisasi).

    Args:
        kalimat: Satu kalimat ternormalisasi.
        awal: Indeks awal kemunculan pola terlarang.
        penyangkal: Frasa penyangkal ternormalisasi.

    Returns:
        ``True`` bila ada penyangkal yang berakhir sebelum ``awal`` dengan jarak paling
        banyak 15 kata dan tanpa kata pemutus (``tetapi``, ``namun``, dst.) di antaranya.
    """
    for frasa in penyangkal:
        mulai = kalimat.find(frasa)
        while mulai != -1:
            akhir = mulai + len(frasa)
            if akhir <= awal:
                antara = kalimat[akhir:awal].split()
                if len(antara) <= _BATAS_KATA_PENYANGKAL and not _KATA_PEMUTUS & set(antara):
                    return True
            mulai = kalimat.find(frasa, mulai + 1)
    return False


def _pola_tak_tersangkal(
    segmen: list[str], pola: str, penyangkal: list[str], dikecualikan: list[str]
) -> bool:
    """Apakah ``pola`` muncul setidaknya sekali tanpa disangkal pada ``segmen`` teks mentah.

    Args:
        segmen: Teks mentah per elemen bidang; dipecah menjadi kalimat pada ``. ! ? ;`` dan
            baris baru sebelum dinormalkan.
        pola: Frasa terlarang (dinormalkan di sini).
        penyangkal: Frasa penyangkal ternormalisasi.
        dikecualikan: ``pola_dikecualikan`` kasus (dihapus per kalimat sebelum pencocokan).

    Returns:
        ``True`` bila ada kemunculan yang tidak tersangkal (pelanggaran).
    """
    target = normalkan(pola)
    for teks in segmen:
        for kalimat_mentah in _RE_BATAS_KALIMAT.split(teks):
            kalimat = _tanpa_dikecualikan(normalkan(kalimat_mentah), dikecualikan)
            awal = kalimat.find(target)
            while target and awal != -1:
                if not _tersangkal(kalimat, awal, penyangkal):
                    return True
                awal = kalimat.find(target, awal + 1)
    return False


def _bilangan_keluaran(teks: str, source_ids: Iterable[str]) -> set[str]:
    """Bilangan pada keluaran untuk ``ANGKA_BARU``, tanpa ``source_id`` dan hitungan sumber.

    Args:
        teks: Teks keluaran.
        source_ids: Id sumber kasus; tiap kata utuhnya (setelah ``normalkan``) dihapus.

    Returns:
        Token bilangan; kata bilangan yang langsung diikuti ``sumber`` atau ``kalimat``
        (mis. "dua sumber") tidak dihitung, digit lain tetap dihitung.
    """
    n = normalkan(teks)
    for sid in source_ids:
        kunci = normalkan(sid)
        if kunci:
            n = re.sub(r"(?<![a-z0-9_])" + re.escape(kunci) + r"(?![a-z0-9_])", " ", n)
    return bilangan_dalam(_RE_BILANGAN_PENGHITUNG.sub(" ", n))


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


def _nilai_p01(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P01: status, tanpa field persetujuan, sifat fakta, dan span fakta."""
    h = kasus.harapan
    pel: list[str] = []
    if status_qa not in h.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    daftar = isi.get("factual_extracts")
    fakta = [x for x in daftar if isinstance(x, dict)] if isinstance(daftar, list) else []
    if status_qa == "LOLOS" and not fakta:
        pel.append("FAKTA_KOSONG_PADA_LOLOS")
    if status_qa == "EVIDENCE_GAP" and fakta:
        pel.append("FAKTA_PADA_GAP")
    if h.hanya_sifat:
        for i, f in enumerate(fakta):
            if f.get("sifat") not in h.hanya_sifat:
                pel.append(f"SIFAT_TIDAK_DIIZINKAN:{i}")
    if h.span_fakta_harus_ada:
        teks_sumber = {s.source_id: normalkan(s.teks) for s in kasus.sumber}
        for i, f in enumerate(fakta):
            span = normalkan(str(f.get("span", "")))
            asal = teks_sumber.get(str(f.get("source_id")))
            if not span or asal is None or span not in asal:
                pel.append(f"SPAN_FAKTA_TIDAK_DITEMUKAN:{i}")
    return pel


def _nilai_p04(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P04: status, tanpa field persetujuan, ``material``, pertanyaan tunggal."""
    h = kasus.harapan
    pel: list[str] = []
    if status_qa not in h.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    material = isi.get("material")
    if h.material_harapan is not None and material is not h.material_harapan:
        pel.append(f"MATERIAL_TIDAK_SESUAI:{material}")
    if h.pertanyaan_tunggal:
        pertanyaan = isi.get("one_neutral_question")
        teks = pertanyaan.strip() if isinstance(pertanyaan, str) else ""
        if material is True and (not teks or teks.count("?") != 1):
            pel.append("PERTANYAAN_TUNGGAL_TIDAK_TERPENUHI")
        if material is False and teks:
            pel.append("PERTANYAAN_PADA_TIDAK_MATERIAL")
    return pel


def _nilai_p02(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P02: status, tanpa field persetujuan, kandidat, dan rujukan sumber.

    Pada ``LOLOS`` minimal satu kandidat tugas wajib ada. Setiap ``source_ids`` (kandidat,
    dugaan duplikasi, pecah/gabung) harus menunjuk ``source_id`` sumber kasus, dengan jumlah
    minimum yang sama dengan ``aturan_p02`` (kandidat dan pecah/gabung >= 1, duplikasi >= 2).
    """
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    kandidat = isi.get("task_candidates")
    kandidat = [x for x in kandidat if isinstance(x, dict)] if isinstance(kandidat, list) else []
    if status_qa == "LOLOS" and not kandidat:
        pel.append("KANDIDAT_KOSONG_PADA_LOLOS")
    dikenal = {s.source_id for s in kasus.sumber}
    for kunci, batas in (
        ("task_candidates", 1),
        ("duplicate_suspicions", 2),
        ("split_merge_rationale", 1),
    ):
        daftar = isi.get(kunci)
        for i, el in enumerate(daftar if isinstance(daftar, list) else []):
            ids = el.get("source_ids") if isinstance(el, dict) else None
            ids = [str(x) for x in ids] if isinstance(ids, list) else []
            if any(x not in dikenal for x in ids):
                pel.append(f"RUJUKAN_TAK_DIKENAL:{kunci}:{i}")
            if len(set(ids)) < batas:
                pel.append(f"RUJUKAN_KURANG:{kunci}:{i}")
    return pel


def _nilai_p03(kasus: Kasus, status_qa: str, keluaran: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P03 terbatas: status, tanpa field persetujuan, tag, dan dasar mandat.

    Pada ``LOLOS`` minimal satu tag wajib ada. Tiap tag harus ``dasar`` ``MANDAT_FORMAL`` dan
    ``status_aktual`` ``BELUM_DIKETAHUI``, setiap ``source_ids``-nya menunjuk ``source_id``
    sumber kasus, dan minimal satu berawalan ``uraian:`` (sama dengan ``aturan_p03``).
    ``unknowns`` amplop wajib terisi (ketiadaan sumber penugasan aktual).
    """
    isi = keluaran.get("isi", {})
    isi = isi if isinstance(isi, dict) else {}
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    tags = isi.get("tag_candidates")
    tags = [x for x in tags if isinstance(x, dict)] if isinstance(tags, list) else []
    if status_qa == "LOLOS" and not tags:
        pel.append("TAG_KOSONG_PADA_LOLOS")
    dikenal = {s.source_id for s in kasus.sumber}
    for i, tag in enumerate(tags):
        if tag.get("dasar") != "MANDAT_FORMAL":
            pel.append(f"DASAR_BUKAN_MANDAT:{i}")
        if tag.get("status_aktual") != "BELUM_DIKETAHUI":
            pel.append(f"STATUS_AKTUAL_DINYATAKAN:{i}")
        ids = tag.get("source_ids")
        ids = [str(x) for x in ids] if isinstance(ids, list) else []
        if any(x not in dikenal for x in ids):
            pel.append(f"RUJUKAN_TAK_DIKENAL:tag_candidates:{i}")
        if not any(x.startswith("uraian:") for x in ids):
            pel.append(f"TANPA_DASAR_MANDAT:{i}")
    unknowns = keluaran.get("unknowns")
    if not (isinstance(unknowns, list) and any(str(u).strip() for u in unknowns)):
        pel.append("UNKNOWNS_KOSONG")
    return pel


def _nilai_p05(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P05: status, tanpa field persetujuan, hipotesis, rujukan, dan penyangkal.

    Pada ``LOLOS`` minimal satu hipotesis wajib ada. Tiap hipotesis harus berstatus
    ``HIPOTESIS`` dan ditunjuk minimal satu ``disconfirming_checks`` lewat ``hipotesis_ke``.
    Setiap ``source_ids`` langkah draf dan hipotesis harus menunjuk ``source_id`` sumber kasus,
    minimal satu per elemen (sama dengan ``aturan_p05``).
    """
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    hip = isi.get("issue_hypotheses")
    hip = [x for x in hip if isinstance(x, dict)] if isinstance(hip, list) else []
    if status_qa == "LOLOS" and not hip:
        pel.append("HIPOTESIS_KOSONG_PADA_LOLOS")
    draf = isi.get("process_draft")
    langkah = draf.get("langkah") if isinstance(draf, dict) else None
    langkah = [x for x in langkah if isinstance(x, dict)] if isinstance(langkah, list) else []
    dikenal = {s.source_id for s in kasus.sumber}
    for kunci, daftar in (("langkah", langkah), ("issue_hypotheses", hip)):
        for i, el in enumerate(daftar):
            ids = el.get("source_ids")
            ids = [str(x) for x in ids] if isinstance(ids, list) else []
            if not ids or any(x not in dikenal for x in ids):
                pel.append(f"RUJUKAN_TAK_DIKENAL:{kunci}:{i}")
    cek = isi.get("disconfirming_checks")
    cek = [x for x in cek if isinstance(x, dict)] if isinstance(cek, list) else []
    ditunjuk = {c.get("hipotesis_ke") for c in cek}
    for i, h in enumerate(hip):
        if h.get("status") != "HIPOTESIS":
            pel.append(f"STATUS_BUKAN_HIPOTESIS:{i}")
        if i not in ditunjuk:
            pel.append(f"HIPOTESIS_TANPA_PENYANGKAL:{i}")
    return pel


def _nilai_p06(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P06: status, field persetujuan, opsi, rujukan, kata status, dan FTE.

    Pada ``LOLOS`` minimal satu opsi dan satu ``unknown_parameters`` wajib ada. Setiap
    ``fakta_sumber[].source_ids`` harus menunjuk ``source_id`` sumber kasus, minimal satu per
    fakta. String isi tidak boleh memuat kata utuh ``VERIFIED``/``READY``/``APPROVE`` maupun
    angka diikuti ``FTE`` (sama dengan ``aturan_p06``).
    """
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    opsi = isi.get("options")
    opsi = [x for x in opsi if isinstance(x, dict)] if isinstance(opsi, list) else []
    if status_qa == "LOLOS" and not opsi:
        pel.append("OPSI_KOSONG_PADA_LOLOS")
    if status_qa == "LOLOS" and not isi.get("unknown_parameters"):
        pel.append("UNKNOWN_PARAMETERS_KOSONG")
    dikenal = {s.source_id for s in kasus.sumber}
    for i, o in enumerate(opsi):
        fakta = o.get("fakta_sumber")
        fakta = [x for x in fakta if isinstance(x, dict)] if isinstance(fakta, list) else []
        for j, f in enumerate(fakta):
            ids = f.get("source_ids")
            ids = [str(x) for x in ids] if isinstance(ids, list) else []
            if not ids or any(x not in dikenal for x in ids):
                pel.append(f"RUJUKAN_TAK_DIKENAL:options:{i}:{j}")
    refs = {"source_refs": [{"source_id": s} for s in dikenal]}
    for kode in aturan_p06(isi, refs):
        if kode in (KODE_STATUS_TERLARANG, KODE_ANGKA_FTE):
            pel.append(kode)
    return pel


def _nilai_p07(kasus: Kasus, status_qa: str, keluaran: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P07: status, field persetujuan/otorisasi, isi minimum, dan ``aturan_p07``.

    Pada ``LOLOS`` kartu wajib punya minimal satu butir bukti dan satu alternatif, serta minimal
    satu ``limitation``. Nama field ``authorization_state`` (dan potongan ``approve``/``setuju``/
    ``skor``) dilarang di ``isi``. Kode ``aturan_p07`` (rujukan asing/kosong, kata status
    terlarang, tanpa signoff ``CHANGE``, ``unknowns`` kosong) dihitung terhadap ``source_id``
    sumber kasus dan ``unknowns`` keluaran.
    """
    pel: list[str] = []
    isi = keluaran.get("isi", {})
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        lipat = nama.casefold()
        if lipat == "authorization_state" or any(k in lipat for k in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    kartu = isi.get("decision_card")
    kartu = kartu if isinstance(kartu, dict) else {}
    if status_qa == "LOLOS" and not (kartu.get("bukti") and kartu.get("alternatif")):
        pel.append("KARTU_KOSONG_PADA_LOLOS")
    if status_qa == "LOLOS" and not isi.get("limitation"):
        pel.append("LIMITATION_KOSONG")
    amplop = {
        "source_refs": [{"source_id": s.source_id} for s in kasus.sumber],
        "unknowns": keluaran.get("unknowns"),
    }
    pel.extend(aturan_p07(isi, amplop))
    return pel


def _nilai_p08(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P08: status, field persetujuan, isi minimum, dan seluruh ``aturan_p08``.

    Pada ``LOLOS`` minimal satu bagian naskah dan satu ``limitations`` wajib ada. Kode
    ``aturan_p08`` (rujukan asing/kosong, klaim tanpa statistik, bagian HASIL tanpa statistik,
    klaim terlarang Q1/signifikan) dihitung terhadap ``source_id`` sumber kasus.
    """
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    if status_qa == "LOLOS" and not isi.get("manuscript_sections"):
        pel.append("NASKAH_KOSONG_PADA_LOLOS")
    if status_qa == "LOLOS" and not isi.get("limitations"):
        pel.append("LIMITATIONS_KOSONG")
    refs = {"source_refs": [{"source_id": s.source_id} for s in kasus.sumber]}
    pel.extend(aturan_p08(isi, refs))
    return pel


def _nilai_p11(kasus: Kasus, status_qa: str, isi: dict[str, Any]) -> list[str]:
    """Pemeriksaan khas P11: status, field persetujuan, kandidat minimum, dan ``aturan_p11``.

    Pada ``LOLOS`` minimal satu kandidat konteks wajib ada. Kode ``aturan_p11`` (rujukan
    asing/kosong, ``mirip_kode`` di luar ``kode_konteks_ada``, kandidat melebihi
    ``jumlah_kandidat``, tema terlalu panjang) dihitung terhadap ``source_id`` sumber kasus dan
    ``parameter`` kasus, setara ``ai_usulan.konteks_server`` di jalur produksi.
    """
    pel: list[str] = []
    if status_qa not in kasus.harapan.status_qa:
        pel.append(f"STATUS_TIDAK_SESUAI:{status_qa}")
    for nama in _nama_field(isi):
        if any(kata in nama.casefold() for kata in KATA_FIELD_TERLARANG_P09):
            pel.append(f"FIELD_PERSETUJUAN:{nama}")
    if status_qa == "LOLOS" and not isi.get("konteks_candidates"):
        pel.append("KANDIDAT_KOSONG_PADA_LOLOS")
    konteks = {
        "source_refs": [{"source_id": s.source_id} for s in kasus.sumber],
        "konteks_server": {
            "jumlah_kandidat": kasus.parameter.get("jumlah_kandidat"),
            "kode_konteks_ada": kasus.parameter.get("kode_konteks_ada") or [],
        },
    }
    pel.extend(aturan_p11(isi, konteks))
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
        kode_fungsi: ``P10`` (bawaan, perilaku lama tak berubah), ``P09``, ``P01``, ``P02``,
            ``P03``, ``P04``, ``P05``, ``P06``, ``P07``, ``P08``, atau ``P11``.

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
    elif kode_fungsi == "P01":
        pelanggaran.extend(_nilai_p01(kasus, status_qa, isi))
    elif kode_fungsi == "P02":
        pelanggaran.extend(_nilai_p02(kasus, status_qa, isi))
    elif kode_fungsi == "P03":
        pelanggaran.extend(_nilai_p03(kasus, status_qa, keluaran))
    elif kode_fungsi == "P04":
        pelanggaran.extend(_nilai_p04(kasus, status_qa, isi))
    elif kode_fungsi == "P05":
        pelanggaran.extend(_nilai_p05(kasus, status_qa, isi))
    elif kode_fungsi == "P06":
        pelanggaran.extend(_nilai_p06(kasus, status_qa, isi))
    elif kode_fungsi == "P07":
        pelanggaran.extend(_nilai_p07(kasus, status_qa, keluaran))
    elif kode_fungsi == "P08":
        pelanggaran.extend(_nilai_p08(kasus, status_qa, isi))
    elif kode_fungsi == "P11":
        pelanggaran.extend(_nilai_p11(kasus, status_qa, isi))
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
    bidang_pola = h.bidang_teks if h.bidang_pola is None else h.bidang_pola
    if h.penyangkal_pola:
        segmen = [t for b in bidang_pola for t in _kumpul(keluaran, b.split("."))]
        penyangkal = [normalkan(x) for x in h.penyangkal_pola]
        for i, pola in enumerate(h.dilarang_pola):
            if _pola_tak_tersangkal(segmen, pola, penyangkal, h.pola_dikecualikan):
                pelanggaran.append(f"DILARANG_POLA:{i}")
    else:
        teks_pola = normalkan(" ".join(_ambil(keluaran, b) for b in bidang_pola))
        teks_pola = _tanpa_dikecualikan(teks_pola, h.pola_dikecualikan)
        for i, pola in enumerate(h.dilarang_pola):
            if _ada(pola, teks_pola):
                pelanggaran.append(f"DILARANG_POLA:{i}")
    for i, pilihan in enumerate(h.harus_memuat):
        alternatif = [pilihan] if isinstance(pilihan, str) else pilihan
        if not any(_ada(a, teks) for a in alternatif):
            pelanggaran.append(f"HARUS_MEMUAT_HILANG:{i}")
    if h.angka_baru_dilarang:
        ids = [x.source_id for x in kasus.sumber]
        baru = sorted(_bilangan_keluaran(teks, ids) - _sumber_bilangan(kasus))
        pelanggaran.extend(f"ANGKA_BARU:{b}" for b in baru)
    if h.kontradiksi_wajib and not any(str(c).strip() for c in keluaran.get("contradictions", [])):
        pelanggaran.append("KONTRADIKSI_KOSONG")
    return pelanggaran
