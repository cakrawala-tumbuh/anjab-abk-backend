"""Otorisasi object-level (BOLA/IDOR) untuk hasil per individu DCS & WCP.

Backlog 025 — `GET /{dcs,wcp}/hasil-responden/{id}` adalah data paling sensitif di
aplikasi ini (hasil psikososial & beban kerja per orang). Token valid saja TIDAK cukup:
partisipan tidak boleh membaca hasil rekan kerjanya hanya karena dia login. Guard =
admin ATAU partisipan pemilik responden (`authorize_responden_access`).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

DCS_RSP = "/api/v1/dcs/responden"
DCS_SUB = "/api/v1/dcs/sub-skala"
DCS_HASIL_RSP = "/api/v1/dcs/hasil-responden"

WCP_RSP = "/api/v1/wcp/responden"
WCP_DIM = "/api/v1/wcp/dimensi"
WCP_HASIL_RSP = "/api/v1/wcp/hasil-responden"


def _item_ids(client: TestClient, base: str) -> list[str]:
    out: list[str] = []
    for grp in client.get(base).json():
        r = client.get(f"{base}/{grp['kode']}/items")
        out.extend(i["item_id"] for i in r.json())
    return out


def _assign_and_submit(client: TestClient, rsp_base: str, item_base: str, par_id: str) -> str:
    r = client.post(rsp_base, json={"partisipan_ids": [par_id]})
    assert r.status_code == 201, r.text
    rsp_id = r.json()["created"][0]["id"]

    item_ids = _item_ids(client, item_base)
    r2 = client.put(
        f"{rsp_base}/{rsp_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r2.status_code == 200, r2.text
    r3 = client.post(f"{rsp_base}/{rsp_id}/jawaban/submit")
    assert r3.status_code == 201, r3.text
    return rsp_id


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hr"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hr"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_partisipan_lain_403(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Partisipan B (login, token sah) TIDAK boleh membaca hasil milik partisipan A."""
    par_a = partisipan_factory(f"{subj}-a")
    partisipan_factory(f"{subj}-b")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_b = client_as(f"{subj}-b", groups=["partisipan"])
    r = as_b.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 403, r.text
    # Isi hasil tidak boleh ikut terkirim bersama respons penolakan.
    assert "dimensi" not in r.json().get("data", {})
    assert "sub_skala" not in r.json().get("data", {})


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hro"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hro"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_pemilik_boleh(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Pemilik responden tetap boleh membaca hasilnya sendiri (tidak over-block)."""
    par_a = partisipan_factory(f"{subj}-a")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_a = client_as(f"{subj}-a", groups=["partisipan"])
    r = as_a.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 200, r.text
    assert r.json()["responden_id"] == rsp_id


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hra"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hra"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_admin_boleh(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Admin boleh membaca hasil responden mana pun."""
    par_a = partisipan_factory(f"{subj}-a")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_admin = client_as(f"{subj}-adm", groups=["admin"])
    r = as_admin.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 200, r.text
    assert r.json()["responden_id"] == rsp_id


@pytest.mark.parametrize("hasil_base", [DCS_HASIL_RSP, WCP_HASIL_RSP], ids=["dcs", "wcp"])
def test_hasil_responden_tanpa_token_401(anon_client: TestClient, hasil_base: str) -> None:
    """Kebocoran nyata di produksi (backlog 025 fakta #6): hasil satu individu dapat
    dibaca TANPA token apa pun."""
    assert anon_client.get(f"{hasil_base}/wrsp_7c0ff89d").status_code == 401


# --- Audit baca data terlindung (backlog 74) ---

AUDIT_LOGGER = "anjab_abk_backend.audit"


def _audit(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == AUDIT_LOGGER and r.message == "protected_read"]


def test_normalisasi_tujuan_potong_200_dan_default() -> None:
    from anjab_abk_backend.dependencies import normalisasi_tujuan

    assert len(normalisasi_tujuan("x" * 250)) == 200
    assert normalisasi_tujuan("  verifikasi data  ") == "verifikasi data"
    assert normalisasi_tujuan(None) == "TIDAK_DINYATAKAN"
    assert normalisasi_tujuan("   ") == "TIDAK_DINYATAKAN"


def test_audit_get_jawaban_admin_dengan_tujuan(
    client: TestClient, client_as, partisipan_factory, caplog: pytest.LogCaptureFixture
) -> None:
    par = partisipan_factory("aud-a")
    rsp_id = _assign_and_submit(client, WCP_RSP, WCP_DIM, par)
    adm = client_as("aud-adm", groups=["admin"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    r = adm.get(f"{WCP_RSP}/{rsp_id}/jawaban", headers={"X-Tujuan-Akses": "verifikasi data"})
    assert r.status_code == 200, r.text
    recs = _audit(caplog)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.actor == "aud-adm"
    assert rec.resource == "/api/v1/wcp/responden/{responden_id}/jawaban"
    assert rec.resource_id == rsp_id
    assert rec.tujuan == "verifikasi data"
    # Tidak ada nama / isi jawaban pada record.
    assert not hasattr(rec, "nama")
    assert not hasattr(rec, "jawaban")


def test_audit_tanpa_header_tujuan_tidak_dinyatakan(
    client: TestClient, client_as, partisipan_factory, caplog: pytest.LogCaptureFixture
) -> None:
    par = partisipan_factory("aud-b")
    rsp_id = _assign_and_submit(client, WCP_RSP, WCP_DIM, par)
    adm = client_as("aud-adm2", groups=["admin"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    assert adm.get(f"{WCP_RSP}/{rsp_id}/jawaban").status_code == 200
    recs = _audit(caplog)
    assert len(recs) == 1
    assert recs[0].tujuan == "TIDAK_DINYATAKAN"


def test_audit_hasil_responden_dcs_pemilik(
    client: TestClient, client_as, partisipan_factory, caplog: pytest.LogCaptureFixture
) -> None:
    par = partisipan_factory("aud-own")
    rsp_id = _assign_and_submit(client, DCS_RSP, DCS_SUB, par)
    own = client_as("aud-own", groups=["partisipan"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    assert own.get(f"{DCS_HASIL_RSP}/{rsp_id}").status_code == 200
    recs = _audit(caplog)
    assert len(recs) == 1
    assert recs[0].actor == "aud-own"
    assert recs[0].resource_id == rsp_id


def test_audit_ditolak_403_nol_record(
    client: TestClient, client_as, partisipan_factory, caplog: pytest.LogCaptureFixture
) -> None:
    par_a = partisipan_factory("aud-x-a")
    partisipan_factory("aud-x-b")
    rsp_id = _assign_and_submit(client, WCP_RSP, WCP_DIM, par_a)
    as_b = client_as("aud-x-b", groups=["partisipan"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    assert as_b.get(f"{WCP_RSP}/{rsp_id}/jawaban").status_code == 403
    assert _audit(caplog) == []


def test_audit_tulis_lewat_guard_sama_nol_record(
    client: TestClient, client_as, partisipan_factory, caplog: pytest.LogCaptureFixture
) -> None:
    par = partisipan_factory("aud-w")
    r = client.post(WCP_RSP, json={"partisipan_ids": [par]})
    rsp_id = r.json()["created"][0]["id"]
    adm = client_as("aud-w-adm", groups=["admin"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    item_ids = _item_ids(adm, WCP_DIM)
    r2 = adm.put(
        f"{WCP_RSP}/{rsp_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r2.status_code == 200, r2.text
    assert _audit(caplog) == []


def test_audit_kode_orang_tim_kajian(client_as, caplog: pytest.LogCaptureFixture) -> None:
    tk = client_as("aud-tk", groups=["tim-kajian"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    r = tk.get("/api/v1/redesain/kode-orang", headers={"X-Tujuan-Akses": "kajian"})
    assert r.status_code == 200, r.text
    recs = _audit(caplog)
    assert len(recs) == 1
    assert recs[0].actor == "aud-tk"
    assert recs[0].resource == "/api/v1/redesain/kode-orang"
    assert recs[0].tujuan == "kajian"


def test_audit_kode_orang_bukan_tim_kajian_nol_record(
    client_as, caplog: pytest.LogCaptureFixture
) -> None:
    other = client_as("aud-nontk", groups=["partisipan"])
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    caplog.clear()
    assert other.get("/api/v1/redesain/kode-orang").status_code == 403
    assert _audit(caplog) == []
