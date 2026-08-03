"""Test mekanisme migrasi Alembic — penjaga disiplin migrasi gaya Odoo.

Yang dijamin:

1. ``test_single_head`` — hanya ada SATU head (tidak ada cabang divergen yang lupa
   di-merge). Lebih dari satu head = rantai migrasi pecah.
2. ``test_revision_graph_integrity`` — graf revisi utuh: tidak ada ``revision`` id
   duplikat dan ada tepat satu titik awal (``down_revision is None``).
3. ``test_setiap_revisi_satu_berkas`` — tiap revisi tinggal di berkasnya sendiri
   (satu perubahan struktur = satu berkas), bukan ditumpuk dalam satu berkas.
4. ``test_schema_matches_models`` — schema hasil ``upgrade head`` SAMA PERSIS dengan
   model ORM. Inilah penjaga utama: bila model berubah tanpa revisi baru, test ini
   gagal sehingga developer dipaksa membuat migrasi.
5. ``test_upgrade_downgrade_roundtrip`` — seluruh rantai bisa dijalankan maju lalu
   mundur sampai ``base`` lalu maju lagi (downgrade benar-benar terdefinisi).
6. ``test_uraian_sederhana_v2_19_r1_*`` — revisi data `cdd92c950f19` (backlog `#30`)
   mengganti `ti_uraian_tugas.uraian` lama->baru per kode HANYA bila teksnya masih
   persis nilai lama yang diharapkan; baris yang sudah diedit manual tidak tersentuh.
7. ``test_uraian_klon_koordinator_*`` — revisi data `3889bd9af66e` menerapkan aturan
   yang sama pada 75 baris klon `KOEKS-`/`KOHUM-`/`KOSAR-` (di luar `task_catalog.json`)
   agar redaksinya sama dengan kembarannya di katalog.
8. ``test_opm_std_*`` — revisi data `ad595b80d3d1` (backlog `#33`) mem-backfill tiga
   kolom `std_opm_importance`/`std_opm_frequency`/`std_opm_criticality` pada
   `ti_uraian_tugas_jabatan` dari berkas beku
   `migrations/data/20260729_opm_std_values_v2_19.json`, hanya untuk baris yang
   ketiga kolomnya masih `NULL`.
9. ``test_opm_sesi_cabang_*`` — revisi DDL `981b2e1945b0` (tambah `opm_sesi.cabang`,
   lepas `unique=True` `jabatan_id`) + revisi data `5f9c20955d88` (backfill `cabang`
   dari `ti_sesi.cabang` sumber, backlog `#37`) TIDAK mengurangi baris `opm_sesi`/
   `opm_responden`/`opm_jawaban`, idempoten, dan tidak menimpa `cabang` yang sudah
   terisi.

Test berbasis-DB membangun **database sekali-pakai** terpisah dari DB test utama agar
tidak mengganggu fixtur ``engine`` (yang sudah di-seed). Database itu dibuat & dihapus
di dalam fixtur ``fresh_db_url``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, make_url, select, text
from sqlalchemy.orm import Session

from anjab_abk_backend.db import get_db_settings
from anjab_abk_backend.migrate import current_heads, downgrade, make_alembic_config, upgrade
from anjab_abk_backend.models import Base, DcsSubSkalaModel
from anjab_abk_backend.seed_db import seed_all


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(make_alembic_config())


# --- Test murni (tanpa DB): integritas graf revisi -------------------------------


def test_single_head() -> None:
    heads = current_heads()
    assert len(heads) == 1, (
        f"Harus tepat SATU head migrasi, ditemukan {len(heads)}: {heads}. "
        "Cabang divergen harus di-merge: `alembic merge -m '...' <head1> <head2>`."
    )


def test_revision_graph_integrity() -> None:
    revisions = list(_script().walk_revisions())
    ids = [r.revision for r in revisions]
    assert len(ids) == len(set(ids)), f"Ada revision id duplikat: {ids}"
    bases = [r.revision for r in revisions if r.down_revision is None]
    assert len(bases) == 1, f"Harus tepat satu revisi awal (base), ditemukan: {bases}"


def test_setiap_revisi_satu_berkas() -> None:
    """Satu perubahan struktur = satu berkas revisi (tidak menumpuk di satu berkas)."""
    revisions = list(_script().walk_revisions())
    paths = [r.path for r in revisions]
    assert len(paths) == len(set(paths)), (
        "Setiap revisi harus berada di berkasnya sendiri; "
        f"ada berkas yang memuat >1 revisi: {paths}"
    )


# --- Test berbasis DB sekali-pakai -----------------------------------------------


@pytest.fixture
def fresh_db_url() -> str:
    """Buat database PostgreSQL kosong sekali-pakai, kembalikan URL-nya, hapus di akhir."""
    admin_url = make_url(str(get_db_settings().sqlalchemy_url()))
    new_name = f"mig_test_{uuid.uuid4().hex[:12]}"

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{new_name}"'))
    admin_engine.dispose()

    fresh_url = admin_url.set(database=new_name)
    try:
        yield fresh_url.render_as_string(hide_password=False)
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": new_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{new_name}"'))
        admin_engine.dispose()


def test_schema_matches_models(fresh_db_url: str) -> None:
    """Setelah `upgrade head`, schema DB harus identik dengan model ORM.

    Bila gagal: ada perubahan di ``models.py`` yang belum dibuatkan revisi. Jalankan
    `make migration m="..."`, review berkasnya, lalu commit revisi tersebut.
    """
    upgrade(fresh_db_url, "head")
    engine = create_engine(fresh_db_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert (
        diff == []
    ), f"Model ORM tidak sinkron dengan migrasi (perlu revisi baru). Selisih terdeteksi: {diff}"


def test_upgrade_downgrade_roundtrip(fresh_db_url: str) -> None:
    """Rantai migrasi bisa maju → mundur ke base → maju lagi tanpa error."""
    upgrade(fresh_db_url, "head")
    engine = create_engine(fresh_db_url)
    try:
        tabel_setelah_upgrade = set(inspect(engine).get_table_names())
        assert "dcs_item" in tabel_setelah_upgrade, "tabel domain harus ada setelah upgrade"

        downgrade(fresh_db_url, "base")
        tabel_setelah_downgrade = set(inspect(engine).get_table_names())
        assert (
            "dcs_item" not in tabel_setelah_downgrade
        ), "downgrade base harus menghapus tabel domain"

        upgrade(fresh_db_url, "head")
        assert "dcs_item" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_init_idempoten_simulasi_up_d(fresh_db_url: str) -> None:
    """Init deploy (migrasi + seed) aman dijalankan berkali-kali — simulasi `up -d` ulang.

    Mereplikasi yang dilakukan entrypoint container (`initdb`): `upgrade head` + `seed_all`.
    Dijalankan dua kali pada DB yang sama; tidak boleh error dan jumlah baris master data
    harus stabil (seed tidak menggandakan, migrasi tidak dijalankan ulang).
    """

    def init_and_count() -> int:
        upgrade(fresh_db_url, "head")  # idempoten via tabel alembic_version
        engine = create_engine(fresh_db_url)
        try:
            with Session(engine) as session:
                seed_all(session)
                session.commit()
                return session.scalar(select(func.count()).select_from(DcsSubSkalaModel))
        finally:
            engine.dispose()

    pertama = init_and_count()
    kedua = init_and_count()  # deploy / `up -d` kedua
    assert pertama > 0, "seed harus mengisi master data pada init pertama"
    assert pertama == kedua, "init tidak idempoten: jumlah baris master data berubah saat diulang"


def test_backfill_authentik_user_id_ke_email(fresh_db_url: str) -> None:
    """Revisi backfill mengganti placeholder/pk pada `authentik_user_id` menjadi email.

    Bangun schema sampai revisi SEBELUM backfill, sisipkan baris dengan
    `authentik_user_id` placeholder dan pk numerik (+ email panjang >64 char yang tak
    muat di kolom lama), lalu `upgrade head` (menjalankan revisi backfill) dan pastikan
    `authentik_user_id` setiap baris menjadi sama dengan email-nya.
    """
    upgrade(fresh_db_url, "b2bbd3afbe65")  # revisi tepat sebelum backfill
    engine = create_engine(fresh_db_url)
    email_panjang = "nama.yang.sangat.panjang.sekali.untuk.uji.kolom@subdomain.ypii.sch.id"
    assert len(email_panjang) > 64
    baris = [
        ("par_mig01", "Placeholder", "placeholder@x.id", "placeholder_abcd1234"),
        ("par_mig02", "Pk Numerik", "pknumerik@x.id", "4242"),
        ("par_mig03", "Sudah Benar", "sudahbenar@x.id", "sudahbenar@x.id"),
        ("par_mig04", "Email Panjang", email_panjang, "placeholder_ffff0000"),
    ]
    try:
        with engine.begin() as conn:
            for pid, nama, email, auth in baris:
                conn.execute(
                    text(
                        "INSERT INTO partisipan "
                        "(id, nama, email, sekolah_id, jabatan_utama_id, masa_kerja_tahun, "
                        " masa_kerja_bulan, aktif, authentik_user_id, created_at) "
                        "VALUES (:id, :nama, :email, 'skl_x', 'jbt_x', 0, 0, true, :auth, now())"
                    ),
                    {"id": pid, "nama": nama, "email": email, "auth": auth},
                )

        upgrade(fresh_db_url, "head")  # jalankan revisi backfill

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT email, authentik_user_id FROM partisipan ORDER BY id")
            ).all()
        assert rows, "baris uji harus tetap ada setelah migrasi"
        for email, auth in rows:
            assert auth == email, f"authentik_user_id harus = email, dapat {auth!r} vs {email!r}"
    finally:
        engine.dispose()


def test_fk_cascade_membersihkan_baris_yatim(fresh_db_url: str) -> None:
    """Revisi FK cascade (`a4aeb5bcbe81`) membersihkan baris yatim SEBELUM membuat FK.

    Menyisipkan tiga jenis baris yatim pada revisi tepat sebelumnya (`0a58616358f4`):
    responden yatim (sesi induk hilang), jawaban yatim MURNI (responden induk tak
    pernah ada), dan `ti_seleksi` yatim lewat `sesi_id` (responden induk masih valid,
    tapi sesi-nya hilang) — menjaring jalur pembersihan langkah 1 & 2 sekaligus kasus
    dua-parent Task Inventory. `upgrade(head)` TIDAK BOLEH raise (yang berarti FK
    berhasil dibuat) dan seluruh baris yatim harus lenyap.
    """
    upgrade(fresh_db_url, "0a58616358f4")  # revisi tepat sebelum FK cascade
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            # Responden DCS yatim (sesi_id menunjuk sesi yang tidak pernah ada).
            conn.execute(
                text(
                    "INSERT INTO dcs_responden"
                    " (id, sesi_id, jabatan_label, sudah_submit, created_at) "
                    "VALUES ('drsp_yatim01', 'dses_tidakada', 'Guru', false, now())"
                )
            )
            # Jawaban DCS anak dari responden yatim di atas (harus ikut lenyap di langkah 2).
            conn.execute(
                text(
                    "INSERT INTO dcs_jawaban (id, responden_id, item_id, skor_raw) "
                    "VALUES ('djwb_yatim01', 'drsp_yatim01', 'D01', 3)"
                )
            )
            # Jawaban DCS yatim MURNI (responden induk tak pernah ada sama sekali).
            conn.execute(
                text(
                    "INSERT INTO dcs_jawaban (id, responden_id, item_id, skor_raw) "
                    "VALUES ('djwb_yatim02', 'drsp_tidakada', 'D02', 4)"
                )
            )
            # ti_seleksi yatim lewat sesi_id: responden induk VALID, sesi induk hilang.
            conn.execute(
                text(
                    "INSERT INTO ti_sesi (id, jabatan_id, periode, status, min_responden, "
                    " max_responden, task_frozen, created_at) "
                    "VALUES ('tises_valid01', 'jbt_x', '2026-01', 'DRAFT', 1, 10, false, now())"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO ti_responden"
                    " (id, sesi_id, tahap1_submit, tahap3_submit, created_at) "
                    "VALUES ('tirs_valid01', 'tises_valid01', false, false, now())"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO ti_seleksi (id, responden_id, sesi_id, task_kode, created_at) "
                    "VALUES ('tisl_yatim01', 'tirs_valid01', 'tises_tidakada', 'TI001', now())"
                )
            )

        upgrade(fresh_db_url, "head")  # jalankan revisi FK cascade — tidak boleh raise

        with engine.connect() as conn:
            sisa_responden = conn.execute(
                text("SELECT count(*) FROM dcs_responden WHERE id = 'drsp_yatim01'")
            ).scalar_one()
            sisa_jawaban = conn.execute(
                text(
                    "SELECT count(*) FROM dcs_jawaban WHERE id IN ('djwb_yatim01', 'djwb_yatim02')"
                )
            ).scalar_one()
            sisa_seleksi = conn.execute(
                text("SELECT count(*) FROM ti_seleksi WHERE id = 'tisl_yatim01'")
            ).scalar_one()
            responden_valid_tetap_ada = conn.execute(
                text("SELECT count(*) FROM ti_responden WHERE id = 'tirs_valid01'")
            ).scalar_one()
        assert sisa_responden == 0, "responden yatim harus terhapus sebelum FK dibuat"
        assert sisa_jawaban == 0, "jawaban yatim (langsung & turunan) harus terhapus"
        assert sisa_seleksi == 0, "ti_seleksi yatim lewat sesi_id harus terhapus"
        assert responden_valid_tetap_ada == 1, "responden VALID tidak boleh ikut terhapus"
    finally:
        engine.dispose()


def _insert_ti_sesi_dan_partisipan_dasar(conn) -> tuple[str, str]:
    """Sisipkan satu baris `ti_sesi` + satu `partisipan` minimal; kembalikan `(sesi_id, par_id)`.

    Dipakai bersama oleh test duplikat `ti_responden` (`79edf4fa66b1`) agar tiap test
    tidak mengulang boilerplate FK induk (`ti_sesi`, `partisipan`).
    """
    sesi_id = f"tises_mig_{uuid.uuid4().hex[:8]}"
    par_id = f"par_mig_{uuid.uuid4().hex[:8]}"
    conn.execute(
        text(
            "INSERT INTO ti_sesi (id, jabatan_id, cabang, status, task_frozen, created_at) "
            "VALUES (:sid, 'jbt_mig_x', 'Bandung', 'DRAFT', false, now())"
        ),
        {"sid": sesi_id},
    )
    conn.execute(
        text(
            "INSERT INTO partisipan"
            " (id, nama, email, sekolah_id, jabatan_utama_id, masa_kerja_tahun,"
            "  masa_kerja_bulan, aktif, authentik_user_id, created_at) "
            "VALUES (:pid, 'Par Migrasi', :email, 'skl_mig_x', 'jbt_mig_x', 0, 0, true,"
            "        :pid, now())"
        ),
        {"pid": par_id, "email": f"{par_id}@test.id"},
    )
    return sesi_id, par_id


def test_bersihkan_duplikat_ti_responden_tanpa_submit_tanpa_anak(fresh_db_url: str) -> None:
    """Revisi `79edf4fa66b1` menghapus duplikat aman & menyisakan baris yang submit.

    Dua baris `ti_responden` untuk `(sesi_id, partisipan_id)` yang sama: satu sudah
    `tahap1_submit`, satu belum & tanpa baris anak. `upgrade(head)` harus menyisakan
    hanya baris yang submit, dan constraint unique berhasil dipasang.
    """
    upgrade(fresh_db_url, "92f6851d040c")  # revisi tepat sebelum penambahan constraint
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            sesi_id, par_id = _insert_ti_sesi_dan_partisipan_dasar(conn)
            conn.execute(
                text(
                    "INSERT INTO ti_responden"
                    " (id, sesi_id, partisipan_id, tahap1_submit, tahap3_submit, created_at) "
                    "VALUES ('trsp_migA', :sid, :pid, true, false, now())"
                ),
                {"sid": sesi_id, "pid": par_id},
            )
            conn.execute(
                text(
                    "INSERT INTO ti_responden"
                    " (id, sesi_id, partisipan_id, tahap1_submit, tahap3_submit, created_at) "
                    "VALUES ('trsp_migB', :sid, :pid, false, false, now() + interval '1 second')"
                ),
                {"sid": sesi_id, "pid": par_id},
            )

        upgrade(fresh_db_url, "head")  # jalankan revisi pembersihan + constraint

        with engine.connect() as conn:
            sisa = conn.execute(
                text("SELECT id FROM ti_responden WHERE sesi_id = :sid AND partisipan_id = :pid"),
                {"sid": sesi_id, "pid": par_id},
            ).all()
            constraint_ada = conn.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'uq_ti_responden_sesi_partisipan'"
                )
            ).scalar_one()
        assert [r.id for r in sisa] == ["trsp_migA"], "hanya baris yang submit boleh tersisa"
        assert constraint_ada == 1, "constraint unik harus terpasang setelah pembersihan"
    finally:
        engine.dispose()


def test_bersihkan_duplikat_ti_responden_dengan_baris_anak_gagal(fresh_db_url: str) -> None:
    """Duplikat yang baris keduanya punya `ti_seleksi` membatalkan migrasi dengan pesan jelas.

    Baris anak berarti ada jawaban tersimpan yang tidak boleh hilang diam-diam —
    migrasi harus `raise` dan menyebut `id` responden yang bentrok, BUKAN menghapusnya.
    """
    upgrade(fresh_db_url, "92f6851d040c")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            sesi_id, par_id = _insert_ti_sesi_dan_partisipan_dasar(conn)
            conn.execute(
                text(
                    "INSERT INTO ti_responden"
                    " (id, sesi_id, partisipan_id, tahap1_submit, tahap3_submit, created_at) "
                    "VALUES ('trsp_migC', :sid, :pid, false, false, now())"
                ),
                {"sid": sesi_id, "pid": par_id},
            )
            conn.execute(
                text(
                    "INSERT INTO ti_responden"
                    " (id, sesi_id, partisipan_id, tahap1_submit, tahap3_submit, created_at) "
                    "VALUES ('trsp_migD', :sid, :pid, false, false, now() + interval '1 second')"
                ),
                {"sid": sesi_id, "pid": par_id},
            )
            # trsp_migC (baris paling awal, kandidat "keeper") tetap punya baris anak —
            # trsp_migD (loser) yang harus diperiksa & menggagalkan migrasi.
            conn.execute(
                text(
                    "INSERT INTO ti_seleksi (id, responden_id, sesi_id, task_kode, created_at) "
                    "VALUES ('tisl_mig01', 'trsp_migD', :sid, 'TI001', now())"
                ),
                {"sid": sesi_id},
            )

        with pytest.raises(RuntimeError, match="trsp_migD"):
            upgrade(fresh_db_url, "head")
    finally:
        engine.dispose()


_FROZEN_REDAKSI_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "data"
    / "20260728_uraian_sederhana_v2_19_r1.json"
)


def _entri_redaksi_kontrol() -> dict[str, str]:
    """Entri beku berkode `KS-ALL-ADMIN-001`, dipakai bersama oleh test redaksi sederhana."""
    with _FROZEN_REDAKSI_PATH.open(encoding="utf-8") as f:
        frozen: list[dict[str, str]] = json.load(f)
    return next(e for e in frozen if e["kode"] == "KS-ALL-ADMIN-001")


def _insert_ti_uraian_tugas_kontrol(conn, *, kode: str, uraian: str) -> str:
    """Sisipkan satu baris `ti_uraian_tugas` + `ti_uraian_tugas_jabatan` minimal; kembalikan `id`.

    `jabatan_id`/`tugas_pokok_id` tidak punya FK (lihat `models.py::TiUraianTugasJabatanModel`)
    sehingga nilai dummy aman dipakai tanpa perlu menyisipkan baris `jabatan`/`ti_tugas_pokok`.
    """
    ut_id = f"tiut_mig_{uuid.uuid4().hex[:8]}"
    conn.execute(
        text("INSERT INTO ti_uraian_tugas (id, uraian, created_at) VALUES (:id, :uraian, now())"),
        {"id": ut_id, "uraian": uraian},
    )
    conn.execute(
        text(
            "INSERT INTO ti_uraian_tugas_jabatan "
            "(uraian_tugas_id, kode, jabatan_id, unit, urutan, tugas_pokok_id) "
            "VALUES (:uid, :kode, 'jbt_mig_x', 'ALL', 1, 'tp_mig_x')"
        ),
        {"uid": ut_id, "kode": kode},
    )
    return ut_id


def _baca_uraian(engine, ut_id: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT uraian FROM ti_uraian_tugas WHERE id = :id"), {"id": ut_id}
        ).scalar_one()


def test_uraian_sederhana_v2_19_r1_upgrade_mengganti_lama_jadi_baru(fresh_db_url: str) -> None:
    """Revisi `cdd92c950f19`: baris berkode ELIGIBLE bertext `lama` berubah jadi `baru`."""
    entry = _entri_redaksi_kontrol()
    upgrade(fresh_db_url, "79edf4fa66b1")  # revisi tepat sebelum redaksi sederhana
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=entry["lama"])

        upgrade(fresh_db_url, "head")  # jalankan revisi redaksi sederhana

        assert _baca_uraian(engine, ut_id) == entry["baru"]
    finally:
        engine.dispose()


def test_uraian_sederhana_v2_19_r1_downgrade_mengembalikan_baru_jadi_lama(
    fresh_db_url: str,
) -> None:
    """`downgrade()` satu langkah dari head mengembalikan teks `baru` menjadi `lama` semula."""
    entry = _entri_redaksi_kontrol()
    upgrade(fresh_db_url, "79edf4fa66b1")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=entry["lama"])

        upgrade(fresh_db_url, "head")
        assert _baca_uraian(engine, ut_id) == entry["baru"]

        downgrade(fresh_db_url, "79edf4fa66b1")
        assert _baca_uraian(engine, ut_id) == entry["lama"]
    finally:
        engine.dispose()


def test_uraian_sederhana_v2_19_r1_tidak_menimpa_baris_yang_sudah_diedit_manual(
    fresh_db_url: str,
) -> None:
    """Baris berkode ELIGIBLE tapi teksnya sudah diedit manual (≠ `lama`) tidak ikut berubah."""
    entry = _entri_redaksi_kontrol()
    teks_manual = "Sudah diedit manual oleh koordinator sebelum migrasi berjalan."
    upgrade(fresh_db_url, "79edf4fa66b1")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=teks_manual)

        upgrade(fresh_db_url, "head")

        assert _baca_uraian(engine, ut_id) == teks_manual
    finally:
        engine.dispose()


def test_uraian_sederhana_v2_19_r1_database_kosong_tanpa_error(fresh_db_url: str) -> None:
    """Upgrade & downgrade revisi `cdd92c950f19` pada database TANPA baris `ti_uraian_tugas`
    manapun selesai tanpa error (0 baris terpengaruh)."""
    upgrade(fresh_db_url, "79edf4fa66b1")
    upgrade(fresh_db_url, "head")  # tidak boleh raise walau tabel ti_uraian_tugas kosong
    downgrade(fresh_db_url, "79edf4fa66b1")  # idem untuk arah sebaliknya


_FROZEN_KLON_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "data"
    / "20260729_uraian_klon_koordinator_v2_19_r1.json"
)


def _entri_klon_kontrol() -> dict[str, str]:
    """Entri beku berkode `KOEKS-ALL-ADMIN-005`, dipakai bersama oleh test klon Koordinator."""
    with _FROZEN_KLON_PATH.open(encoding="utf-8") as f:
        frozen: list[dict[str, str]] = json.load(f)
    return next(e for e in frozen if e["kode"] == "KOEKS-ALL-ADMIN-005")


def test_uraian_klon_koordinator_upgrade_menyamakan_dengan_kembaran(fresh_db_url: str) -> None:
    """Revisi `3889bd9af66e`: baris klon bertext `lama` berubah jadi redaksi kembarannya."""
    entry = _entri_klon_kontrol()
    upgrade(fresh_db_url, "cdd92c950f19")  # revisi tepat sebelum penyamaan klon
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=entry["lama"])

        upgrade(fresh_db_url, "head")

        assert _baca_uraian(engine, ut_id) == entry["baru"]
    finally:
        engine.dispose()


def test_uraian_klon_koordinator_downgrade_mengembalikan_baru_jadi_lama(fresh_db_url: str) -> None:
    """`downgrade()` satu langkah dari head mengembalikan teks klon menjadi `lama` semula."""
    entry = _entri_klon_kontrol()
    upgrade(fresh_db_url, "cdd92c950f19")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=entry["lama"])

        upgrade(fresh_db_url, "head")
        assert _baca_uraian(engine, ut_id) == entry["baru"]

        downgrade(fresh_db_url, "cdd92c950f19")
        assert _baca_uraian(engine, ut_id) == entry["lama"]
    finally:
        engine.dispose()


def test_uraian_klon_koordinator_tidak_menimpa_baris_yang_sudah_diedit_manual(
    fresh_db_url: str,
) -> None:
    """Baris klon yang teksnya sudah diedit manual (≠ `lama`) tidak ikut berubah."""
    entry = _entri_klon_kontrol()
    teks_manual = "Redaksi klon yang sudah disesuaikan manual untuk cabang Bandung."
    upgrade(fresh_db_url, "cdd92c950f19")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(conn, kode=entry["kode"], uraian=teks_manual)

        upgrade(fresh_db_url, "head")

        assert _baca_uraian(engine, ut_id) == teks_manual
    finally:
        engine.dispose()


def test_uraian_klon_koordinator_tidak_menyentuh_kembarannya(fresh_db_url: str) -> None:
    """Baris kembaran (`PEK-*`) yang sudah bertext `baru` tidak ikut di-UPDATE lagi."""
    entry = _entri_klon_kontrol()
    upgrade(fresh_db_url, "cdd92c950f19")
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_kontrol(
                conn, kode=entry["kembaran"], uraian=entry["baru"]
            )

        upgrade(fresh_db_url, "head")
        assert _baca_uraian(engine, ut_id) == entry["baru"]

        # downgrade klon TIDAK boleh menarik mundur redaksi kembarannya
        downgrade(fresh_db_url, "cdd92c950f19")
        assert _baca_uraian(engine, ut_id) == entry["baru"]
    finally:
        engine.dispose()


def test_uraian_klon_koordinator_database_kosong_tanpa_error(fresh_db_url: str) -> None:
    """Upgrade & downgrade revisi `3889bd9af66e` pada database tanpa baris klon selesai tanpa
    error (0 baris terpengaruh — instalasi baru memang tidak punya jabatan `Koordinator …`)."""
    upgrade(fresh_db_url, "cdd92c950f19")
    upgrade(fresh_db_url, "head")
    downgrade(fresh_db_url, "cdd92c950f19")


# --- Backfill nilai standar OPM (`ad595b80d3d1`, backlog #33) --------------------

_FROZEN_OPM_STD_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "data"
    / "20260729_opm_std_values_v2_19.json"
)

# Revisi tepat sebelum backfill data — kolom std_opm_* sudah ada (DDL `c8fb8be9e184`)
# tetapi masih NULL untuk seluruh baris.
_OPM_STD_DDL_REVISION = "c8fb8be9e184"


def _entri_opm_std_kontrol() -> dict[str, object]:
    """Entri beku berkode `KS-ALL-LEAD-001` (importance/frequency/criticality penuh,
    tanpa Frequency kotor), dipakai bersama oleh test backfill nilai standar OPM."""
    with _FROZEN_OPM_STD_PATH.open(encoding="utf-8") as f:
        frozen: list[dict[str, object]] = json.load(f)
    return next(e for e in frozen if e["kode"] == "KS-ALL-LEAD-001")


def _insert_ti_uraian_tugas_jabatan_opm(
    conn,
    *,
    kode: str,
    importance: int | None = None,
    frequency: int | None = None,
    criticality: int | None = None,
) -> str:
    """Sisipkan satu baris `ti_uraian_tugas` + `ti_uraian_tugas_jabatan` minimal, dengan
    `std_opm_*` opsional (default `NULL`); kembalikan `id` kanoniknya.

    `jabatan_id`/`tugas_pokok_id` tidak punya FK (lihat
    `models.py::TiUraianTugasJabatanModel`) sehingga nilai dummy aman dipakai tanpa
    perlu menyisipkan baris `jabatan`/`ti_tugas_pokok`. Dipakai khusus oleh test
    revisi `ad595b80d3d1` (backfill nilai standar OPM, backlog #33).
    """
    ut_id = f"tiut_mig_{uuid.uuid4().hex[:8]}"
    conn.execute(
        text("INSERT INTO ti_uraian_tugas (id, uraian, created_at) VALUES (:id, 'x', now())"),
        {"id": ut_id},
    )
    conn.execute(
        text(
            "INSERT INTO ti_uraian_tugas_jabatan "
            "(uraian_tugas_id, kode, jabatan_id, unit, urutan, tugas_pokok_id, "
            " std_opm_importance, std_opm_frequency, std_opm_criticality) "
            "VALUES (:uid, :kode, 'jbt_mig_x', 'ALL', 1, 'tp_mig_x', :imp, :freq, :crit)"
        ),
        {"uid": ut_id, "kode": kode, "imp": importance, "freq": frequency, "crit": criticality},
    )
    return ut_id


def _baca_std_opm(engine, ut_id: str) -> tuple[int | None, int | None, int | None]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT std_opm_importance, std_opm_frequency, std_opm_criticality "
                "FROM ti_uraian_tugas_jabatan WHERE uraian_tugas_id = :id"
            ),
            {"id": ut_id},
        ).one()
    return row.std_opm_importance, row.std_opm_frequency, row.std_opm_criticality


def test_opm_std_upgrade_mengisi_baris_null(fresh_db_url: str) -> None:
    """Revisi `ad595b80d3d1`: baris kosong (`std_opm_*` NULL) diisi sesuai berkas beku."""
    entry = _entri_opm_std_kontrol()
    upgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_jabatan_opm(conn, kode=entry["kode"])

        upgrade(fresh_db_url, "head")

        assert _baca_std_opm(engine, ut_id) == (
            entry["importance"],
            entry["frequency"],
            entry["criticality"],
        )
    finally:
        engine.dispose()


def test_opm_std_downgrade_mengembalikan_ke_null(fresh_db_url: str) -> None:
    """`downgrade()` satu langkah dari head mengosongkan kembali `std_opm_*` ke `NULL`."""
    entry = _entri_opm_std_kontrol()
    upgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_jabatan_opm(conn, kode=entry["kode"])

        upgrade(fresh_db_url, "head")
        assert _baca_std_opm(engine, ut_id) == (
            entry["importance"],
            entry["frequency"],
            entry["criticality"],
        )

        downgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
        assert _baca_std_opm(engine, ut_id) == (None, None, None)
    finally:
        engine.dispose()


def test_opm_std_tidak_menimpa_baris_sudah_diisi_manual(fresh_db_url: str) -> None:
    """Baris yang salah satu kolom `std_opm_*`-nya sudah terisi manual sebelum migrasi
    dilewati UTUH — ketiga kolom dibiarkan apa adanya, tidak ditimpa sebagian."""
    entry = _entri_opm_std_kontrol()
    upgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_jabatan_opm(conn, kode=entry["kode"], importance=1)

        upgrade(fresh_db_url, "head")

        assert _baca_std_opm(engine, ut_id) == (1, None, None)
    finally:
        engine.dispose()


def test_opm_std_kode_tidak_dikenal_tidak_error(fresh_db_url: str) -> None:
    """Baris ber-kode yang tidak ada di berkas beku dilewati tanpa error, tetap NULL."""
    upgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            ut_id = _insert_ti_uraian_tugas_jabatan_opm(conn, kode="TI_TAK_DIKENAL_01")

        upgrade(fresh_db_url, "head")  # tidak boleh raise walau kode tak dikenal

        assert _baca_std_opm(engine, ut_id) == (None, None, None)
    finally:
        engine.dispose()


def test_opm_std_database_kosong_tanpa_error(fresh_db_url: str) -> None:
    """Upgrade & downgrade revisi `ad595b80d3d1` pada database TANPA baris
    `ti_uraian_tugas_jabatan` manapun selesai tanpa error (0 baris terpengaruh)."""
    upgrade(fresh_db_url, _OPM_STD_DDL_REVISION)
    upgrade(fresh_db_url, "head")
    downgrade(fresh_db_url, _OPM_STD_DDL_REVISION)


# --------------------------------------------------------------------------- #
# backlog #37 — opm_sesi.cabang: DDL `981b2e1945b0` + backfill `5f9c20955d88`
# --------------------------------------------------------------------------- #

_OPM_CABANG_DDL_REVISION = "981b2e1945b0"


def _insert_jabatan(conn, *, jabatan_id: str, kode: str, nama: str) -> None:
    conn.execute(
        text(
            "INSERT INTO jabatan (id, kode, nama, jenis, aktif, created_at) "
            "VALUES (:id, :kode, :nama, 'Guru', true, now())"
        ),
        {"id": jabatan_id, "kode": kode, "nama": nama},
    )


def _insert_ti_sesi_mig(conn, *, ti_sesi_id: str, jabatan_id: str, cabang: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO ti_sesi (id, jabatan_id, cabang, status, task_frozen, created_at) "
            "VALUES (:id, :jabatan_id, :cabang, 'TAHAP3', true, now())"
        ),
        {"id": ti_sesi_id, "jabatan_id": jabatan_id, "cabang": cabang},
    )


def _insert_opm_sesi_mig(
    conn, *, sesi_id: str, jabatan_id: str, ti_sesi_id: str, cabang: str | None, periode: str
) -> None:
    conn.execute(
        text(
            "INSERT INTO opm_sesi "
            "(id, jabatan_id, ti_sesi_id, cabang, periode, status, min_responden, "
            " max_responden, created_at) "
            "VALUES (:id, :jabatan_id, :ti_sesi_id, :cabang, :periode, 'ANALYZED', 3, 10, now())"
        ),
        {
            "id": sesi_id,
            "jabatan_id": jabatan_id,
            "ti_sesi_id": ti_sesi_id,
            "cabang": cabang,
            "periode": periode,
        },
    )


def _insert_opm_responden_mig(conn, *, responden_id: str, sesi_id: str) -> None:
    conn.execute(
        text(
            "INSERT INTO opm_responden (id, sesi_id, jabatan_label, sudah_submit, created_at) "
            "VALUES (:id, :sesi_id, 'Guru', true, now())"
        ),
        {"id": responden_id, "sesi_id": sesi_id},
    )


def _insert_opm_jawaban_mig(conn, *, jawaban_id: str, responden_id: str, task_kode: str) -> None:
    conn.execute(
        text(
            "INSERT INTO opm_jawaban "
            "(id, responden_id, task_kode, importance, frequency, criticality) "
            "VALUES (:id, :responden_id, :task_kode, 4, 3, 5)"
        ),
        {"id": jawaban_id, "responden_id": responden_id, "task_kode": task_kode},
    )


def _hitung_baris_opm(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            tabel: conn.execute(text(f"SELECT COUNT(*) FROM {tabel}")).scalar_one()
            for tabel in ("opm_sesi", "opm_responden", "opm_jawaban")
        }


def _baca_cabang_opm_sesi(engine, sesi_id: str) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT cabang FROM opm_sesi WHERE id = :id"), {"id": sesi_id}
        ).scalar_one()


def test_opm_sesi_cabang_upgrade_backfill_dari_ti_sesi(fresh_db_url: str) -> None:
    """Revisi `5f9c20955d88`: sesi OPM ber-`cabang IS NULL` dibackfill dari `ti_sesi.cabang`
    sumbernya — meniru 3 sesi OPM produksi YPII (2026-08-03), semuanya bersumber dari sesi
    TI cabang Semarang. Jumlah baris `opm_sesi`/`opm_responden`/`opm_jawaban` TIDAK boleh
    berkurang sebaris pun (tidak ada `DELETE` di revisi ini)."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            _insert_jabatan(conn, jabatan_id="jbt_mig01", kode="MIG-01", nama="Guru BK")
            _insert_ti_sesi_mig(
                conn, ti_sesi_id="tises_mig01", jabatan_id="jbt_mig01", cabang="Semarang"
            )
            _insert_opm_sesi_mig(
                conn,
                sesi_id="opses_mig01",
                jabatan_id="jbt_mig01",
                ti_sesi_id="tises_mig01",
                cabang=None,
                periode="2026-06",
            )
            _insert_opm_responden_mig(conn, responden_id="oprs_mig01", sesi_id="opses_mig01")
            _insert_opm_jawaban_mig(
                conn, jawaban_id="opjw_mig01", responden_id="oprs_mig01", task_kode="K001"
            )

        before = _hitung_baris_opm(engine)
        upgrade(fresh_db_url, "head")
        after = _hitung_baris_opm(engine)

        assert before == after, "jumlah baris opm_sesi/opm_responden/opm_jawaban berubah"
        assert _baca_cabang_opm_sesi(engine, "opses_mig01") == "Semarang"
    finally:
        engine.dispose()


def test_opm_sesi_cabang_tidak_menimpa_yang_sudah_terisi(fresh_db_url: str) -> None:
    """Baris `opm_sesi.cabang` yang SUDAH terisi (non-NULL) tidak ditimpa, meski
    `ti_sesi.cabang` sumbernya berbeda."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            _insert_jabatan(conn, jabatan_id="jbt_mig02", kode="MIG-02", nama="Guru BK 2")
            _insert_ti_sesi_mig(
                conn, ti_sesi_id="tises_mig02", jabatan_id="jbt_mig02", cabang="Semarang"
            )
            _insert_opm_sesi_mig(
                conn,
                sesi_id="opses_mig02",
                jabatan_id="jbt_mig02",
                ti_sesi_id="tises_mig02",
                cabang="Bandung",
                periode="2026-06",
            )

        upgrade(fresh_db_url, "head")

        assert _baca_cabang_opm_sesi(engine, "opses_mig02") == "Bandung"
    finally:
        engine.dispose()


def test_opm_sesi_cabang_ti_sesi_sumber_null_tetap_null(fresh_db_url: str) -> None:
    """`ti_sesi.cabang IS NULL` (sesi TI lama) → `opm_sesi.cabang` tetap `NULL` setelah
    migrasi, bukan error."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            _insert_jabatan(conn, jabatan_id="jbt_mig03", kode="MIG-03", nama="Guru BK 3")
            _insert_ti_sesi_mig(conn, ti_sesi_id="tises_mig03", jabatan_id="jbt_mig03", cabang=None)
            _insert_opm_sesi_mig(
                conn,
                sesi_id="opses_mig03",
                jabatan_id="jbt_mig03",
                ti_sesi_id="tises_mig03",
                cabang=None,
                periode="2026-06",
            )

        upgrade(fresh_db_url, "head")  # tidak boleh raise

        assert _baca_cabang_opm_sesi(engine, "opses_mig03") is None
    finally:
        engine.dispose()


def test_opm_sesi_cabang_downgrade_lalu_upgrade_ulang_idempoten(fresh_db_url: str) -> None:
    """`downgrade()` mengosongkan kembali HANYA baris yang nilainya masih persis sama
    dengan `ti_sesi.cabang`; `upgrade()` berikutnya membackfill nilai yang sama lagi —
    aman dijalankan berulang (roundtrip)."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            _insert_jabatan(conn, jabatan_id="jbt_mig04", kode="MIG-04", nama="Guru BK 4")
            _insert_ti_sesi_mig(
                conn, ti_sesi_id="tises_mig04", jabatan_id="jbt_mig04", cabang="Semarang"
            )
            _insert_opm_sesi_mig(
                conn,
                sesi_id="opses_mig04",
                jabatan_id="jbt_mig04",
                ti_sesi_id="tises_mig04",
                cabang=None,
                periode="2026-06",
            )

        upgrade(fresh_db_url, "head")
        assert _baca_cabang_opm_sesi(engine, "opses_mig04") == "Semarang"

        downgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
        assert _baca_cabang_opm_sesi(engine, "opses_mig04") is None

        upgrade(fresh_db_url, "head")
        assert _baca_cabang_opm_sesi(engine, "opses_mig04") == "Semarang"
    finally:
        engine.dispose()


def test_opm_sesi_cabang_downgrade_tidak_menimpa_yang_diubah_manual(fresh_db_url: str) -> None:
    """`downgrade()` TIDAK mengosongkan baris yang nilainya sudah diubah manual setelah
    migrasi berjalan (nilainya kini tidak lagi persis sama dengan `ti_sesi.cabang`)."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    engine = create_engine(fresh_db_url)
    try:
        with engine.begin() as conn:
            _insert_jabatan(conn, jabatan_id="jbt_mig05", kode="MIG-05", nama="Guru BK 5")
            _insert_ti_sesi_mig(
                conn, ti_sesi_id="tises_mig05", jabatan_id="jbt_mig05", cabang="Semarang"
            )
            _insert_opm_sesi_mig(
                conn,
                sesi_id="opses_mig05",
                jabatan_id="jbt_mig05",
                ti_sesi_id="tises_mig05",
                cabang=None,
                periode="2026-06",
            )

        upgrade(fresh_db_url, "head")
        assert _baca_cabang_opm_sesi(engine, "opses_mig05") == "Semarang"

        with engine.begin() as conn:
            conn.execute(text("UPDATE opm_sesi SET cabang = 'Bandung' WHERE id = 'opses_mig05'"))

        downgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
        assert _baca_cabang_opm_sesi(engine, "opses_mig05") == "Bandung"
    finally:
        engine.dispose()


def test_opm_sesi_cabang_database_kosong_tanpa_error(fresh_db_url: str) -> None:
    """Upgrade & downgrade revisi `5f9c20955d88` pada database TANPA baris `opm_sesi`
    manapun selesai tanpa error (0 baris terpengaruh)."""
    upgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
    upgrade(fresh_db_url, "head")
    downgrade(fresh_db_url, _OPM_CABANG_DDL_REVISION)
