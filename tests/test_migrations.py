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

Test berbasis-DB membangun **database sekali-pakai** terpisah dari DB test utama agar
tidak mengganggu fixtur ``engine`` (yang sudah di-seed). Database itu dibuat & dihapus
di dalam fixtur ``fresh_db_url``.
"""

from __future__ import annotations

import uuid

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
    assert diff == [], (
        "Model ORM tidak sinkron dengan migrasi (perlu revisi baru). " f"Selisih terdeteksi: {diff}"
    )


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
