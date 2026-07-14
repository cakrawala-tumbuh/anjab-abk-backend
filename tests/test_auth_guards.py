"""Penjaga invariant keamanan: TIDAK ADA endpoint baca yang dapat diakses tanpa token.

Backlog 025 — sebelumnya 32 operasi GET (termasuk `/partisipan` yang membocorkan
nama+email seluruh pegawai, dan `/{dcs,wcp}/hasil-responden/{id}` yang membocorkan
hasil psikososial per individu) dapat dibaca siapa pun TANPA `Authorization` sama sekali.

Test di berkas ini **memindai `app.routes`**, bukan daftar path yang ditulis tangan:
setiap operasi GET/`POST /search` baru yang lupa dipasangi `READ_GUARDS` otomatis
membuat test gagal — daftar manual akan basi diam-diam.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

# Endpoint yang memang SENGAJA publik (system.py) — satu-satunya pengecualian yang sah.
PUBLIC_PATHS = {"/api/v1/health", "/api/v1/ready", "/api/v1/version"}

_PARAM = re.compile(r"\{[^}]+\}")


def _concrete(path: str) -> str:
    """Ganti path param dengan nilai dummy — guard 401 dievaluasi sebelum badan fungsi,
    jadi ID yang tidak ada tetap harus menghasilkan 401 (bukan 404): keberadaan resource
    tidak boleh bocor ke pemanggil tanpa identitas."""
    return _PARAM.sub("x", path)


def _all_read_routes() -> list[tuple[str, str]]:
    """Semua operasi BACA (GET, plus `POST /search`) di luar endpoint publik.

    Dibaca dari skema OpenAPI, bukan `app.routes`: router disertakan sebagai
    `_IncludedRouter` bersarang sehingga `app.routes` TIDAK datar dan penyaringan
    `isinstance(r, APIRoute)` akan menghasilkan daftar KOSONG (test lulus vakum).
    """
    from anjab_abk_backend.main import create_app

    paths = create_app().openapi()["paths"]
    out: list[tuple[str, str]] = []
    for path, ops in paths.items():
        if not path.startswith("/api/v1") or path in PUBLIC_PATHS:
            continue
        for method in ops:
            m = method.upper()
            if m == "GET" or (m == "POST" and path.endswith("/search")):
                out.append((m, path))
    return sorted(set(out))


_READ_ROUTES = _all_read_routes()


def test_ada_rute_baca_terpindai() -> None:
    """Penjaga bagi penjaga: bila pemindaian rute rusak/kosong, test parametrized di
    bawah akan 'lulus' secara vakum tanpa menguji apa pun."""
    assert (
        len(_READ_ROUTES) >= 40
    ), f"Hanya {len(_READ_ROUTES)} rute baca terpindai — pemindai rusak?"


@pytest.mark.parametrize(("method", "path"), _READ_ROUTES, ids=lambda v: v)
def test_endpoint_baca_tanpa_token_401(anon_client: TestClient, method: str, path: str) -> None:
    """SETIAP operasi baca tanpa `Authorization` → 401 (bukan 200/404/422)."""
    url = _concrete(path)
    r = anon_client.request(method, url, json={} if method == "POST" else None)
    assert r.status_code == 401, (
        f"{method} {url} mengembalikan {r.status_code}, seharusnya 401 —"
        f" endpoint baca WAJIB memasang READ_GUARDS (lihat dependencies.READ_GUARDS)."
    )


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS))
def test_endpoint_publik_tetap_200_tanpa_token(anon_client: TestClient, path: str) -> None:
    """Regresi: `/health`, `/ready`, `/version` HARUS tetap dapat diakses tanpa token
    (dipakai probe Docker/Traefik — mengunci ini akan mematikan deployment)."""
    assert anon_client.get(path).status_code == 200


def test_partisipan_list_tanpa_token_tidak_bocorkan_pii(anon_client: TestClient) -> None:
    """Regresi eksplisit atas kebocoran nyata di produksi (backlog 025 fakta #4):
    `GET /partisipan` tanpa token pernah mengembalikan 200 + nama & email 103 pegawai."""
    r = anon_client.get("/api/v1/partisipan")
    assert r.status_code == 401
    assert "email" not in r.text


def test_partisipan_search_tanpa_token_tidak_bocorkan_pii(anon_client: TestClient) -> None:
    """`POST /partisipan/search` mengembalikan data yang SAMA dengan `GET /partisipan` —
    menutup GET saja tidak menutup kebocorannya."""
    r = anon_client.post("/api/v1/partisipan/search", json={"domain": []})
    assert r.status_code == 401
    assert "email" not in r.text
