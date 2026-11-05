"""Uji kering gerbang PII: mengukur berapa sumber akan ditolak, tanpa model dan tanpa tulis."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...ai.redaksi import SumberAi, gerbang_masukan, muat_kamus_nama
from ...config import Settings
from ...errors import ValidationAppError
from ...models import NarasiSumberModel
from ..schemas.uji_kering import (
    BATAS_SUMBER_UJI_KERING,
    UjiKeringItem,
    UjiKeringRead,
)


class UjiKeringTerlaluBanyakError(ValidationAppError):
    """Jumlah sumber yang diuji melebihi `BATAS_SUMBER_UJI_KERING` (422)."""

    error_code = "uji_kering_terlalu_banyak"


def jalankan_uji_kering(
    session: Session, settings: Settings, sumber_ids: list[str] | None
) -> UjiKeringRead:
    """Jalankan `gerbang_masukan` mode `BLOKIR` atas sumber narasi tersimpan.

    Tiap sumber diperiksa dengan salinan lokal settings (`ai_pii_mode=BLOKIR`,
    `ai_jenis_sumber_diizinkan=[jenis sumber]`) agar daftar izin jenis bawaan tidak
    menolak sebelum PII diperiksa. Settings global tidak diubah, tidak ada tulisan,
    dan model tidak dipanggil.

    Args:
        session: Sesi SQLAlchemy (hanya dibaca).
        settings: Settings aplikasi; hanya disalin.
        sumber_ids: Id yang diuji; `None` = semua sumber.

    Returns:
        `UjiKeringRead` berisi hitungan; tanpa teks dan tanpa nilai PII.

    Raises:
        UjiKeringTerlaluBanyakError: lebih dari 500 sumber (422).
        ValidationAppError: ada id yang tak dikenal (422).
    """
    m = NarasiSumberModel
    if sumber_ids is None:
        jumlah = session.scalar(select(func.count()).select_from(m)) or 0
        if jumlah > BATAS_SUMBER_UJI_KERING:
            raise UjiKeringTerlaluBanyakError(
                f"Sumber melebihi {BATAS_SUMBER_UJI_KERING}; sebutkan sumber_ids."
            )
        rows = list(session.scalars(select(m).order_by(m.created_at, m.id)).all())
    else:
        unik = list(dict.fromkeys(sumber_ids))
        if len(unik) > BATAS_SUMBER_UJI_KERING:
            raise UjiKeringTerlaluBanyakError(
                f"Sumber melebihi {BATAS_SUMBER_UJI_KERING}; kurangi sumber_ids."
            )
        peta = {r.id: r for r in session.scalars(select(m).where(m.id.in_(unik))).all()}
        hilang = [i for i in unik if i not in peta]
        if hilang:
            raise ValidationAppError(
                f"Sumber tidak ditemukan: {', '.join(h[:40] for h in hilang[:5])}"
                f"{'...' if len(hilang) > 5 else ''}."
            )
        rows = [peta[i] for i in unik]

    kamus = muat_kamus_nama(session)
    items: list[UjiKeringItem] = []
    per_alasan: Counter[str] = Counter()
    per_kategori: Counter[str] = Counter()
    for rec in rows:
        lokal = settings.model_copy(
            update={"ai_pii_mode": "BLOKIR", "ai_jenis_sumber_diizinkan": [rec.jenis]}
        )
        hasil = gerbang_masukan(
            SumberAi(source_id=rec.id, source_hash=rec.teks_hash, jenis=rec.jenis, teks=rec.teks),
            kamus,
            lokal,
        )
        if not hasil.lolos:
            per_alasan[hasil.alasan or "SUMBER_KOSONG"] += 1
            per_kategori.update(hasil.temuan.keys())
        items.append(
            UjiKeringItem(
                sumber_id=rec.id,
                jenis=rec.jenis,
                lolos=hasil.lolos,
                alasan=hasil.alasan,
                temuan=dict(hasil.temuan),
            )
        )
    lolos = sum(1 for i in items if i.lolos)
    return UjiKeringRead(
        total=len(items),
        lolos=lolos,
        ditolak=len(items) - lolos,
        per_alasan=dict(per_alasan),
        per_kategori=dict(per_kategori),
        items=items,
    )
