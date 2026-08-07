"""Unit test murni `compute_hasil_sesi` (`taskinv/services/analisis.py`) — tanpa DB/HTTP.

Fokus: perilaku pengabaian entri detail parsial (backlog `anjab-abk-backend#38`), yang
sulit ditegaskan presisi lewat test HTTP saja karena melibatkan angka `fmean` eksak.
"""

from __future__ import annotations

from anjab_abk_backend.taskinv.schemas.detail import TiDetailRead
from anjab_abk_backend.taskinv.schemas.sesi import TiSesiRead
from anjab_abk_backend.taskinv.services.analisis import compute_hasil_sesi


def _sesi_read(**over: object) -> TiSesiRead:
    base = {
        "id": "tises_test",
        "jabatan_id": "jbt_test",
        "cabang": "Bandung",
        "status": "ANALYZED",
        "created_at": "2026-06-01T00:00:00Z",
    }
    base.update(over)
    return TiSesiRead.model_validate(base)


def _detail(
    id_: str,
    responden_id: str,
    task_kode: str,
    *,
    durasi_per_kali: int | None = 30,
    jam_per_minggu: float = 1.0,
    va_type: str | None = "VA-Core",
) -> TiDetailRead:
    return TiDetailRead.model_validate(
        {
            "id": id_,
            "responden_id": responden_id,
            "sesi_id": "tises_test",
            "task_kode": task_kode,
            "sumber_bukti": "Aktual",
            "kondisi": "Baseline",
            "frekuensi_teks": "Harian",
            "durasi_per_kali": durasi_per_kali,
            "jam_per_minggu": jam_per_minggu,
            "peak4w_hours": 0.0,
            "va_type": va_type,
            "setuju_standar": True,
            "catatan": None,
        }
    )


def test_compute_hasil_sesi_entri_parsial_diabaikan_dari_agregasi() -> None:
    """3 entri untuk task yang sama (2 lengkap, 1 parsial: `durasi_per_kali`/`va_type`
    `None`) → `n_detail=2`, rata-rata jam/durasi dihitung hanya dari 2 entri lengkap,
    `va_type_dist` tidak menghitung entri parsial, tanpa exception."""
    sesi = _sesi_read()
    detail_records = [
        _detail("tdet_1", "r1", "K001", durasi_per_kali=30, jam_per_minggu=2.0),
        _detail("tdet_2", "r2", "K001", durasi_per_kali=10, jam_per_minggu=4.0),
        _detail(
            "tdet_3",
            "r3",
            "K001",
            durasi_per_kali=None,
            jam_per_minggu=0.0,
            va_type=None,
        ),
    ]

    hasil = compute_hasil_sesi(
        sesi=sesi,
        kodes=["K001"],
        catalog_map={},
        relevan_counts={"K001": 3},
        n_tahap1=3,
        detail_records=detail_records,
        n_tahap3=3,
    )

    task = hasil.tasks[0]
    assert task.n_detail == 2
    assert task.jam_per_minggu_mean == 3.0  # fmean(2.0, 4.0)
    assert task.durasi_per_kali_mean == 20.0  # fmean(30, 10)
    assert task.va_type_dist == {"VA-Core": 2}


def test_compute_hasil_sesi_seluruh_entri_parsial_tidak_meruntuhkan_fmean() -> None:
    """Seluruh entri sebuah task parsial (tak ada satu pun lengkap) → task tetap
    muncul dengan `n_detail=0` dan mean `0.0`, bukan `StatisticsError` dari `fmean([])`."""
    sesi = _sesi_read()
    detail_records = [
        _detail("tdet_1", "r1", "K001", durasi_per_kali=None, jam_per_minggu=0.0, va_type=None),
    ]

    hasil = compute_hasil_sesi(
        sesi=sesi,
        kodes=["K001"],
        catalog_map={},
        relevan_counts={"K001": 1},
        n_tahap1=1,
        detail_records=detail_records,
        n_tahap3=1,
    )

    task = hasil.tasks[0]
    assert task.n_detail == 0
    assert task.jam_per_minggu_mean == 0.0
    assert task.va_type_dist == {}
