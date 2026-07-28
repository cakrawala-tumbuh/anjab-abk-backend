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
