"""Test endpoint `OpmSesi`: create (snapshot + auto-responden), CRUD, transisi, search."""

from __future__ import annotations

import uuid

import pytest
from _opm_common import (
    SME_BASE,
    TI_SESI,
    _buat_partisipan,
    _setup_jabatan_panel_ti,
    _uniq_periode,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from anjab_abk_backend.models import OpmRespondenModel
from anjab_abk_backend.opm.schemas.sesi import OpmSesiCreate
from anjab_abk_backend.opm.services.sesi_sql import SqlOpmSesiService

BASE = "/api/v1/opm/sesi"


def _payload(jabatan_id: str, ti_sesi_id: str, **over) -> dict:
    payload = {
        "jabatan_id": jabatan_id,
        "ti_sesi_id": ti_sesi_id,
        "periode": _uniq_periode(),
        "min_responden": 1,
        "max_responden": 10,
    }
    payload.update(over)
    return payload


def test_create_sesi_ok(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r.status_code == 201, r.text
    sesi = r.json()
    assert sesi["id"].startswith("opses_")
    assert sesi["jabatan_id"] == ctx["jabatan_id"]
    assert sesi["ti_sesi_id"] == ctx["ti_sesi_id"]
    assert sesi["status"] == "DRAFT"
    assert sesi["jumlah_task"] == 2

    # Snapshot task = task_terpilih TI.
    rt = client.get(f"{BASE}/{sesi['id']}/task")
    assert rt.status_code == 200, rt.text
    task_kodes = {t["task_kode"] for t in rt.json()}
    assert task_kodes == set(ctx["kodes"])

    # Auto-responden = anggota panel.
    rr = client.get(f"{BASE}/{sesi['id']}/responden")
    assert rr.status_code == 200, rr.text
    responden = rr.json()
    assert len(responden) == 2
    assert {r["partisipan_id"] for r in responden} == set(ctx["partisipan_ids"])
    assert all(r["sudah_submit"] is False for r in responden)


def test_create_sesi_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_x"))
    assert r.status_code == 401


def test_create_sesi_tanpa_sme_panel(client: TestClient, jabatan_id_tk: str) -> None:
    # jabatan_id_tk belum tentu punya panel di transaksi test ini (rollback per-test).
    r = client.post(BASE, json=_payload(jabatan_id_tk, "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_panel_tanpa_anggota(client: TestClient, jabatan_id_tk: str) -> None:
    r = client.post(SME_BASE, json={"jabatan_id": jabatan_id_tk})
    assert r.status_code == 201, r.text
    r2 = client.post(BASE, json=_payload(jabatan_id_tk, "tises_tidakada"))
    assert r2.status_code == 422, r2.text


def test_create_sesi_jabatan_tidak_ada(client: TestClient) -> None:
    r = client.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_tidak_ada(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], "tises_tidakada"))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_jabatan_beda(client: TestClient, jabatan_id_tk: str, db_session) -> None:
    from anjab_abk_backend.models import TiSesiModel

    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    # Sesi TI untuk jabatan lain — disisipkan langsung (bukan via API) karena
    # create sesi TI mensyaratkan katalog task untuk jabatan tsb, yang tak relevan
    # di sini; cukup baris TiSesiModel dengan jabatan_id berbeda.
    other = TiSesiModel(
        id=f"tises_{uuid.uuid4().hex[:8]}",
        jabatan_id=f"jbt_{uuid.uuid4().hex[:8]}",
        cabang="Bandung",
        status="DRAFT",
    )
    db_session.add(other)
    db_session.flush()
    r = client.post(BASE, json=_payload(ctx["jabatan_id"], other.id))
    assert r.status_code == 422, r.text


def test_create_sesi_ti_belum_frozen(client: TestClient, jabatan_id_tk: str) -> None:
    par_ctx_jabatan = jabatan_id_tk
    par1 = _buat_partisipan(client, par_ctx_jabatan, "C")
    par2 = _buat_partisipan(client, par_ctx_jabatan, "D")
    r = client.post(SME_BASE, json={"jabatan_id": par_ctx_jabatan})
    panel_id = r.json()["id"]
    for pid in (par1, par2):
        client.post(f"{SME_BASE}/{panel_id}/anggota", json={"partisipan_id": pid})

    r_ti = client.post(
        TI_SESI,
        json={"jabatan_id": par_ctx_jabatan, "cabang": "Bandung"},
    )
    assert r_ti.status_code == 201, r_ti.text
    # Belum mulai-tahap1 sama sekali → task_frozen masih False.
    r = client.post(BASE, json=_payload(par_ctx_jabatan, r_ti.json()["id"]))
    assert r.status_code == 422, r.text


def test_create_sesi_conflict_jabatan_sudah_punya_sesi(
    client: TestClient, jabatan_id_tk: str
) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    r1 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r1.status_code == 201, r1.text
    r2 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r2.status_code == 409, r2.text


def test_create_sesi_conflict_pesan_pakai_nama_jabatan_bukan_id_mentah(
    client: TestClient, jabatan_id_tk: str
) -> None:
    """Regresi #18: pesan 409 harus menyebut nama jabatan, bukan `jbt_...` mentah."""
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    jbt = client.get(f"/api/v1/jabatan/{ctx['jabatan_id']}")
    assert jbt.status_code == 200, jbt.text
    nama_jabatan = jbt.json()["nama"]

    r1 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r1.status_code == 201, r1.text
    r2 = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"]))
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert nama_jabatan in body["message"], body
    assert ctx["jabatan_id"] not in body["message"], body


def test_create_sesi_tanpa_autoflush_seperti_produksi(
    client: TestClient, jabatan_id_tk: str, db_session
) -> None:
    """Regresi bug 023: `create()` harus jalan juga saat `autoflush` MATI.

    Produksi memakai `sessionmaker(autoflush=False)` (`db.py`), sedangkan harness test
    memakai `Session(...)` dengan `autoflush=True` (default) — dan autoflush itulah yang
    diam-diam mem-flush baris sesi saat `create()` menjalankan SELECT snapshot task,
    sehingga baris sesi kebetulan sudah ada ketika responden di-INSERT. Itu sebabnya bug
    ini SELALU lolos test biasa: seluruh test lain di berkas ini tetap hijau meski
    `flush()` eksplisit dicabut.

    `OpmRespondenModel.sesi_id` adalah FK telanjang tanpa `relationship()` balik ke
    `OpmSesiModel` → unit-of-work SQLAlchemy tidak menjamin INSERT sesi mendahului INSERT
    responden. Tanpa autoflush & tanpa `flush()` eksplisit: `ForeignKeyViolation` (di
    produksi tersamar jadi 409 "sesi sudah ada" — lihat test berikutnya).

    `no_autoflush` di sini MENIRU kondisi produksi; jangan dihapus "karena test lain
    tidak butuh" — justru test lain itulah yang buta terhadap bug ini.
    """
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    svc = SqlOpmSesiService(db_session)

    with db_session.no_autoflush:
        sesi = svc.create(
            OpmSesiCreate(
                jabatan_id=ctx["jabatan_id"],
                ti_sesi_id=ctx["ti_sesi_id"],
                periode=_uniq_periode(),
                min_responden=1,
                max_responden=10,
            )
        )

    assert sesi.id.startswith("opses_")
    assert sesi.jumlah_task == 2
    responden = db_session.scalars(
        select(OpmRespondenModel).where(OpmRespondenModel.sesi_id == sesi.id)
    ).all()
    assert {r.partisipan_id for r in responden} == set(ctx["partisipan_ids"])


def test_flush_checked_tidak_menyamarkan_fk_violation(db_session) -> None:
    """`_flush_checked` hanya boleh memetakan UniqueViolation → 409 (ConflictError).

    Pelanggaran integritas lain harus naik apa adanya. Memetakan SEMUA `IntegrityError`
    jadi "sesi sudah ada" persis yang menyamarkan `ForeignKeyViolation` di `create()`
    sebagai konflik duplikat palsu — dan menyembunyikannya selama dua sesi pengujian
    produksi.
    """
    svc = SqlOpmSesiService(db_session)
    db_session.add(
        OpmRespondenModel(
            id=f"oprs_{uuid.uuid4().hex[:8]}",
            sesi_id="opses_tidak_pernah_ada",  # melanggar FK ke opm_sesi
            nama="X",
            jabatan_label="X",
            partisipan_id=None,
            sudah_submit=False,
        )
    )
    with pytest.raises(IntegrityError):
        svc._flush_checked(on_conflict="pesan konflik ini TIDAK BOLEH dipakai")


def test_create_sesi_idempotency_replay(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    key = f"idem-{uuid.uuid4().hex[:8]}"
    payload = _payload(ctx["jabatan_id"], ctx["ti_sesi_id"])
    r1 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    r2 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == r1.json()["id"]


def test_update_delete_hanya_draft(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]

    r = client.patch(f"{BASE}/{sid}", json={"catatan": "revisi"})
    assert r.status_code == 200, r.text
    assert r.json()["catatan"] == "revisi"

    r_buka = client.post(f"{BASE}/{sid}/buka")
    assert r_buka.status_code == 200
    assert r_buka.json()["status"] == "OPEN"

    r_upd = client.patch(f"{BASE}/{sid}", json={"catatan": "gagal"})
    assert r_upd.status_code == 422

    r_del = client.delete(f"{BASE}/{sid}")
    assert r_del.status_code == 422
    assert "paksa=true" in r_del.json()["message"]


def test_delete_non_draft_dengan_paksa_ok(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]
    client.post(f"{BASE}/{sid}/buka")
    r = client.delete(f"{BASE}/{sid}", params={"paksa": True})
    assert r.status_code == 204
    assert client.get(f"{BASE}/{sid}").status_code == 404


def test_delete_paksa_forbidden_non_admin(
    client: TestClient, client_as, jabatan_id_tk: str
) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]
    client.post(f"{BASE}/{sid}/buka")
    non_admin = client_as("partisipan-1", groups=["partisipan"])
    r = non_admin.delete(f"{BASE}/{sid}", params={"paksa": True})
    assert r.status_code == 403


def test_delete_draft_ok(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    r = client.delete(f"{BASE}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{BASE}/{sesi['id']}").status_code == 404


def test_transisi_lengkap_dan_invalid(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    sid = sesi["id"]

    # Tutup sebelum buka → invalid.
    r_invalid = client.post(f"{BASE}/{sid}/tutup")
    assert r_invalid.status_code == 422

    r1 = client.post(f"{BASE}/{sid}/buka")
    assert r1.status_code == 200
    assert r1.json()["status"] == "OPEN"

    r2 = client.post(f"{BASE}/{sid}/tutup")
    assert r2.status_code == 200
    assert r2.json()["status"] == "CLOSED"

    # Buka lagi dari CLOSED → invalid.
    r3 = client.post(f"{BASE}/{sid}/buka")
    assert r3.status_code == 422


def test_search_domain(client: TestClient, jabatan_id_tk: str) -> None:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id_tk)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["jabatan_id", "=", ctx["jabatan_id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert any(item["id"] == sesi["id"] for item in data["items"])


def test_get_sesi_not_found(client: TestClient) -> None:
    assert client.get(f"{BASE}/opses_tidakada").status_code == 404


# --------------------------------------------------------------------------- #
# Otorisasi (item 015): lapis 1 (admin murni) & lapis 2 (admin/responden sesi)
#
# Lapis 1 (`_ADMIN_GUARDS`) berjalan sebagai dependency FastAPI, sebelum badan
# endpoint dieksekusi — non-admin ditolak 403 walau `sesi_id` tidak nyata (lihat
# preseden serupa di `test_taskinv.py::test_sesi_get_tanpa_token_401`). Karena itu
# test 401/403 di bawah memakai ID sesi dummy, kecuali test yang memang perlu
# memverifikasi efek (mis. status sesi tidak berubah) atau lapis 2 (`/task`).
# --------------------------------------------------------------------------- #

_DUMMY_SESI_ID = "opses_dummy"


def _sesi_admin(client: TestClient, jabatan_id: str) -> tuple[dict, dict]:
    ctx = _setup_jabatan_panel_ti(client, jabatan_id)
    sesi = client.post(BASE, json=_payload(ctx["jabatan_id"], ctx["ti_sesi_id"])).json()
    return sesi, ctx


def _link_authentik_user(db_session, partisipan_id: str, subject: str) -> None:
    """Tautkan partisipan yang sudah ada ke `subject` login (test lapis 2 `/task`)."""
    from anjab_abk_backend.models import PartisipanModel

    obj = db_session.get(PartisipanModel, partisipan_id)
    obj.authentik_user_id = subject
    db_session.flush()


def test_opm_sesi_list_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(BASE).status_code == 401


def test_opm_sesi_list_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-list")
    assert as_partisipan.get(BASE).status_code == 403


def test_opm_sesi_search_tanpa_token_401(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/search", json={"domain": [], "limit": 10, "offset": 0})
    assert r.status_code == 401


def test_opm_sesi_search_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-search")
    r = as_partisipan.post(f"{BASE}/search", json={"domain": [], "limit": 10, "offset": 0})
    assert r.status_code == 403


def test_opm_sesi_create_tanpa_token_401(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_x"))
    assert r.status_code == 401


def test_opm_sesi_create_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-create")
    r = as_partisipan.post(BASE, json=_payload(f"jbt_{uuid.uuid4().hex[:8]}", "tises_x"))
    assert r.status_code == 403


def test_opm_sesi_get_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(f"{BASE}/{_DUMMY_SESI_ID}").status_code == 401


def test_opm_sesi_get_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-get")
    assert as_partisipan.get(f"{BASE}/{_DUMMY_SESI_ID}").status_code == 403


def test_opm_sesi_patch_tanpa_token_401(anon_client: TestClient) -> None:
    r = anon_client.patch(f"{BASE}/{_DUMMY_SESI_ID}", json={"catatan": "x"})
    assert r.status_code == 401


def test_opm_sesi_patch_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-patch")
    r = as_partisipan.patch(f"{BASE}/{_DUMMY_SESI_ID}", json={"catatan": "x"})
    assert r.status_code == 403


def test_opm_sesi_buka_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.post(f"{BASE}/{_DUMMY_SESI_ID}/buka").status_code == 401


def test_opm_buka_sesi_partisipan_403(client: TestClient, client_as, jabatan_id_tk: str) -> None:
    """403 ditolak, dan status sesi TIDAK berubah (tetap DRAFT)."""
    sesi, _ctx = _sesi_admin(client, jabatan_id_tk)
    as_partisipan = client_as("opm-guard-buka-real")
    r = as_partisipan.post(f"{BASE}/{sesi['id']}/buka")
    assert r.status_code == 403
    # `client_as` mengoverride verifier pada `app` — pakai client_as admin untuk
    # verifikasi lanjutan, bukan fixture `client` (lihat docstring `client_as`).
    as_admin = client_as("opm-guard-buka-admin", groups=["admin"])
    r_get = as_admin.get(f"{BASE}/{sesi['id']}")
    assert r_get.json()["status"] == "DRAFT"


def test_opm_sesi_tutup_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.post(f"{BASE}/{_DUMMY_SESI_ID}/tutup").status_code == 401


def test_opm_sesi_tutup_partisipan_403(client_as) -> None:
    as_partisipan = client_as("opm-guard-tutup")
    assert as_partisipan.post(f"{BASE}/{_DUMMY_SESI_ID}/tutup").status_code == 403


def test_opm_sesi_task_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(f"{BASE}/{_DUMMY_SESI_ID}/task").status_code == 401


def test_opm_task_responden_boleh(
    client: TestClient, client_as, jabatan_id_tk: str, db_session
) -> None:
    """Regresi paling mungkin (item 015): satu-satunya endpoint sesi-level yang
    dipakai halaman pengisian partisipan (`opm/isi/[responden_id]`) — TIDAK boleh
    jadi admin-only, karena akan mematikan alur pengisian OPM partisipan."""
    sesi, ctx = _sesi_admin(client, jabatan_id_tk)
    par_a = ctx["partisipan_ids"][0]
    _link_authentik_user(db_session, par_a, "opm-guard-task-boleh")
    as_a = client_as("opm-guard-task-boleh")
    r = as_a.get(f"{BASE}/{sesi['id']}/task")
    assert r.status_code == 200, r.text
    assert {t["task_kode"] for t in r.json()} == set(ctx["kodes"])


def test_opm_task_bukan_responden_403(
    client: TestClient, client_as, jabatan_id_tk: str, db_session
) -> None:
    sesi, ctx = _sesi_admin(client, jabatan_id_tk)
    luar = _buat_partisipan(client, ctx["jabatan_id"], "LuarTask")
    _link_authentik_user(db_session, luar, "opm-guard-task-luar")
    as_luar = client_as("opm-guard-task-luar")
    r = as_luar.get(f"{BASE}/{sesi['id']}/task")
    assert r.status_code == 403
