"""Tes rute `POST /api/v1/task-inventory/jabatan/{id}/tag-peran-ai` (P03 versi terbatas).

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Sumber yang terkirim
hanya usulan P02 (`USULAN_AI`) dan baris mandat (`KATALOG_TI`); hasil hanya `ai_usulan`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p03 import FIELD_SUMBER_MANDAT_P03, FUNGSI_P03
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    JabatanModel,
    TiTugasPokokModel,
    TiUraianTugasJabatanModel,
    TiUraianTugasModel,
)

URL = "/api/v1/task-inventory/jabatan"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["USULAN_AI", "KATALOG_TI"],
}
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p03(monkeypatch):
    """Daftarkan P03 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P03", FUNGSI_P03)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p03", groups=["tim-kajian"])


def _jabatan(db: Session) -> str:
    jid = ("jbt_" + uuid.uuid4().hex * 2)[:40]
    db.add(
        JabatanModel(
            id=jid, kode=f"P3-{uuid.uuid4().hex[:8]}", nama="Jabatan Uji P03", jenis="struktural"
        )
    )  # fmt: skip
    db.flush()
    return jid


def _uraian(db: Session, n: int) -> list[str]:
    ids = []
    for i in range(n):
        ut = TiUraianTugasModel(id=f"ut_{uuid.uuid4().hex[:12]}", uraian=f"Menyusun laporan {i}")
        db.add(ut)
        ids.append(ut.id)
    db.flush()
    return ids


def _pegang(db: Session, jabatan_id: str, uraian_ids: list[str]) -> None:
    tp = TiTugasPokokModel(id=f"tp_{uuid.uuid4().hex[:12]}", nama=f"Pokok {uuid.uuid4().hex}")
    db.add(tp)
    db.flush()
    for i, uid in enumerate(uraian_ids):
        db.add(
            TiUraianTugasJabatanModel(
                uraian_tugas_id=uid, kode=f"P3{uuid.uuid4().hex[:12]}", jabatan_id=jabatan_id,
                unit="SD", urutan=i + 1, tugas_pokok_id=tp.id, std_va_type="VA-Core",
            )
        )  # fmt: skip
    db.flush()


def _usulan(
    db: Session,
    jabatan_id: str,
    uraian_ids: list[str],
    fungsi: str = "P02",
    putusan: str | None = "APPROVE",
) -> str:
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id, fungsi=fungsi, prompt_version="v1", prompt_hash="a" * 64,
            model_diminta="model-uji", protocol_id="uji", input_snapshot_id="b" * 64,
            sumber=[], masukan={}, keluaran={}, status_qa="LOLOS", kode_qa=[],
        )
    )  # fmt: skip
    db.flush()
    isi = {
        "task_candidates": [
            {
                "tindakan": "Menyusun", "objek": "laporan", "tujuan": "tertib", "cara": "format",
                "output": "laporan", "tingkat": "TASK", "source_ids": [f"uraian:{u}"],
            }
            for u in uraian_ids
        ],
        "duplicate_suspicions": [],
        "split_merge_rationale": [],
        "reviewer_questions": [],
    }  # fmt: skip
    rec = AiUsulanModel(
        id=str(uuid.uuid4()), fungsi=fungsi, sasaran_jenis="JABATAN", sasaran_id=jabatan_id,
        job_id=str(uuid.uuid4()), ai_run_id=run_id,
        sumber_ids=[f"uraian:{u}" for u in uraian_ids], diminta_oleh="tim-1",
        diserap_at=_DASAR, hasil_serap="USULAN_DIBUAT", isi=isi,
    )  # fmt: skip
    db.add(rec)
    db.flush()
    if putusan:
        kw: dict[str, Any] = {}
        if putusan == "REJECT":
            kw = {"tingkat_koreksi": "MAJOR", "catatan": "Tidak berdasar."}
        db.add(
            AiUsulanPutusanModel(
                id=str(uuid.uuid4()), usulan_id=rec.id, putusan=putusan, actor_key="r",
                created_at=_DASAR + timedelta(minutes=1), **kw,
            )
        )  # fmt: skip
        db.flush()
    return rec.id


def _ajukan(c, jabatan_id: str, usulan_id: str, periode: str = "2026/27"):
    return c.post(
        f"{URL}/{jabatan_id}/tag-peran-ai", json={"usulan_p02_id": usulan_id, "periode": periode}
    )


def _hitung_p03(db: Session) -> int:
    stmt = select(func.count()).select_from(AiUsulanModel).where(AiUsulanModel.fungsi == "P03")
    return db.scalar(stmt) or 0


def _skenario_dua_uraian_tiga_jabatan(db: Session) -> tuple[str, list[str], list[str], str]:
    """Usulan P02 jabatan A merujuk 2 uraian; uraian 1 dipegang A dan B, uraian 2 dipegang C."""
    a, b, c = _jabatan(db), _jabatan(db), _jabatan(db)
    u1, u2 = _uraian(db, 2)
    _pegang(db, a, [u1])
    _pegang(db, b, [u1])
    _pegang(db, c, [u2])
    _pegang(db, c, _uraian(db, 1))  # uraian lain milik C, tidak dirujuk
    return a, [u1, u2], [a, b, c], _usulan(db, a, [u1, u2])


# --- positif -------------------------------------------------------------------------------


def test_positif_202_sumber_satu_usulan_dan_tiga_baris_mandat(app, client_as, db_session, p03):
    jid, (u1, u2), (a, b, c), usulan_id = _skenario_dua_uraian_tiga_jabatan(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P03" and body["sasaran_jenis"] == "JABATAN"
    assert body["sasaran_id"] == jid
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    assert rec.sumber_ids[0] == f"usulan:{usulan_id}"
    assert sorted(rec.sumber_ids[1:]) == sorted(
        [f"uraian:{u1}@{a}", f"uraian:{u1}@{b}", f"uraian:{u2}@{c}"]
    )
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P03" and run.status_qa == "MENUNGGU"
    kode = db_session.get(JabatanModel, jid).kode
    assert run.masukan["parameter"] == {"jabatan_kode": kode, "periode": "2026/27"}
    sumber = run.masukan["sumber"]
    assert [s["jenis"] for s in sumber] == ["USULAN_AI", "KATALOG_TI", "KATALOG_TI", "KATALOG_TI"]
    for s in sumber:
        assert s["source_hash"] == hashlib.sha256(s["teks"].encode()).hexdigest()
    for s in sumber[1:]:
        kunci = {baris.split(":", 1)[0] for baris in s["teks"].splitlines()}
        assert kunci <= set(FIELD_SUMBER_MANDAT_P03)
        assert "jabatan_kode" in kunci and "std_va_type" not in kunci


def test_sumber_tidak_memuat_tabel_petunjuk_aktual(app, client_as, db_session, p03):
    jid, _u, _j, usulan_id = _skenario_dua_uraian_tiga_jabatan(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 202, r.text
    run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
    jenis = {s["jenis"] for s in run.masukan["sumber"]}
    assert jenis == {"USULAN_AI", "KATALOG_TI"}
    assert "assignment_sources" not in run.masukan
    assert all(s["source_id"].startswith(("usulan:", "uraian:")) for s in run.masukan["sumber"])


def test_revise_juga_diterima(app, client_as, db_session, p03):
    jid = _jabatan(db_session)
    u = _uraian(db_session, 1)
    _pegang(db_session, jid, u)
    usulan_id = _usulan(db_session, jid, u, putusan=None)
    db_session.add(
        AiUsulanPutusanModel(
            id=str(uuid.uuid4()), usulan_id=usulan_id, putusan="REVISE", actor_key="r",
            tingkat_koreksi="MINOR", teks_koreksi="Kandidat dikoreksi.", created_at=_DASAR,
        )
    )  # fmt: skip
    db_session.flush()
    _atur(app)
    assert _ajukan(_tim(client_as), jid, usulan_id).status_code == 202


# --- negatif -------------------------------------------------------------------------------


def test_settings_bawaan_409_tanpa_usulan_baru(app, client_as, db_session):
    jid, _u, _j, usulan_id = _skenario_dua_uraian_tiga_jabatan(db_session)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 409, r.text
    assert _hitung_p03(db_session) == 0


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    jid, _u, _j, usulan_id = _skenario_dua_uraian_tiga_jabatan(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung_p03(db_session) == 0


@pytest.mark.parametrize("putusan", [None, "REJECT"])
def test_usulan_tanpa_putusan_atau_reject_409_usulan_belum_diterima(
    app, client_as, db_session, p03, putusan
):
    jid = _jabatan(db_session)
    u = _uraian(db_session, 1)
    _pegang(db_session, jid, u)
    usulan_id = _usulan(db_session, jid, u, putusan=putusan)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "USULAN_BELUM_DITERIMA"
    assert _hitung_p03(db_session) == 0


def test_usulan_fungsi_p09_422_usulan_bukan_p02(app, client_as, db_session, p03):
    jid = _jabatan(db_session)
    u = _uraian(db_session, 1)
    usulan_id = _usulan(db_session, jid, u, fungsi="P09")
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "USULAN_BUKAN_P02"


def test_usulan_p02_milik_jabatan_lain_422_usulan_bukan_p02(app, client_as, db_session, p03):
    jid, lain = _jabatan(db_session), _jabatan(db_session)
    u = _uraian(db_session, 1)
    usulan_id = _usulan(db_session, lain, u)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, usulan_id)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "USULAN_BUKAN_P02"


def test_jabatan_tak_ada_404_dan_usulan_tak_ada_404(app, client_as, db_session, p03):
    jid = _jabatan(db_session)
    _atur(app)
    c = _tim(client_as)
    assert _ajukan(c, "jbt_tidak_ada", str(uuid.uuid4())).status_code == 404
    assert _ajukan(c, jid, str(uuid.uuid4())).status_code == 404


def test_sumber_lebih_dari_80_422_sumber_terlalu_banyak(app, client_as, db_session, p03):
    jid = _jabatan(db_session)
    u = _uraian(db_session, 80)
    _pegang(db_session, jid, u)
    usulan_id = _usulan(db_session, jid, u)
    _atur(app)
    c = _tim(client_as)
    r = _ajukan(c, jid, usulan_id)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "SUMBER_TERLALU_BANYAK"
    pas = _jabatan(db_session)
    u79 = _uraian(db_session, 79)
    _pegang(db_session, pas, u79)
    assert _ajukan(c, pas, _usulan(db_session, pas, u79)).status_code == 202


def test_bukan_tim_kajian_403(app, client_as, db_session, p03):
    jid, _u, _j, usulan_id = _skenario_dua_uraian_tiga_jabatan(db_session)
    _atur(app)
    r = _ajukan(client_as("admin-1", groups=["admin"]), jid, usulan_id)
    assert r.status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p03):
    jid = _jabatan(db_session)
    _atur(app)
    c = _tim(client_as)
    sah = str(uuid.uuid4())
    for badan in (
        {},
        {"usulan_p02_id": sah},
        {"usulan_p02_id": "bukan-uuid", "periode": "2026/27"},
        {"usulan_p02_id": sah, "periode": "2026/27 ganjil"},
        {"usulan_p02_id": sah, "periode": "2026/27", "assignment_sources": []},
    ):
        r = c.post(f"{URL}/{jid}/tag-peran-ai", json=badan)
        assert r.status_code == 422, badan
