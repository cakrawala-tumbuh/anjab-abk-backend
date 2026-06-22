"""Script migrasi: seed TugasPokok, DetilTugas, UraianTugas ke production via REST API.

Dijalankan SEKALI saat deployment pertama kali setelah backend v0.4.0+.
Membaca data dari task_catalog.json dan memanggil endpoint CRUD untuk setiap record.

Penggunaan:
    BASE_URL=https://anjab.example.com/api/v1 TOKEN=<bearer-token> python scripts/seed_catalog.py

Variabel lingkungan:
    BASE_URL   URL dasar API (default: http://localhost:8000/api/v1)
    TOKEN      Bearer token untuk autentikasi (wajib untuk operasi tulis)
    DRY_RUN    Set ke "1" untuk cek tanpa menulis data (default: "0")
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
TOKEN = os.getenv("TOKEN", "")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

DATA_FILE = Path(__file__).parent.parent / "src" / "anjab_abk_backend" / "taskinv" / "data" / "task_catalog.json"

if not TOKEN and not DRY_RUN:
    print("ERROR: TOKEN wajib diisi untuk operasi tulis.", file=sys.stderr)
    sys.exit(1)


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def _post(path: str, payload: dict) -> dict | None:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409:
            return None  # sudah ada, skip
        if e.code == 200:
            return json.loads(body)
        print(f"  HTTPError {e.code} pada {path}: {body[:200]}", file=sys.stderr)
        return None


def _search(path: str, domain: list) -> list:
    url = f"{BASE_URL}{path}/search"
    payload = {"domain": domain, "limit": 1, "offset": 0}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result.get("items", [])
    except urllib.error.HTTPError:
        return []


def main() -> None:
    print(f"Membaca catalog dari {DATA_FILE}...")
    with DATA_FILE.open(encoding="utf-8") as f:
        catalog: list[dict] = json.load(f)
    print(f"  {len(catalog)} item ditemukan.")

    if DRY_RUN:
        print("DRY RUN aktif — tidak ada data yang ditulis.")
        return

    tp_by_nama: dict[str, str] = {}
    dt_by_key: dict[tuple[str, str], str] = {}

    # Langkah 1: seed TugasPokok
    seen_tp: set[str] = set()
    tp_created = tp_skipped = 0
    for item in catalog:
        nama = item["tugas_pokok"]
        if nama in seen_tp:
            continue
        seen_tp.add(nama)
        result = _post("/task-inventory/tugas-pokok", {"nama": nama})
        if result:
            tp_by_nama[nama] = result["id"]
            tp_created += 1
        else:
            rows = _search("/task-inventory/tugas-pokok", [["nama", "=", nama]])
            if rows:
                tp_by_nama[nama] = rows[0]["id"]
            tp_skipped += 1
    print(f"TugasPokok: {tp_created} dibuat, {tp_skipped} sudah ada.")

    # Langkah 2: seed DetilTugas
    seen_dt: set[tuple[str, str]] = set()
    dt_created = dt_skipped = 0
    for item in catalog:
        dt_nama = item["detil_tugas"].strip()
        if not dt_nama:
            continue
        key = (item["tugas_pokok"], dt_nama)
        if key in seen_dt:
            continue
        seen_dt.add(key)
        tp_id = tp_by_nama.get(item["tugas_pokok"], "")
        result = _post("/task-inventory/detil-tugas", {"nama": dt_nama, "tugas_pokok_id": tp_id})
        if result:
            dt_by_key[key] = result["id"]
            dt_created += 1
        else:
            rows = _search("/task-inventory/detil-tugas", [["nama", "=", dt_nama], ["tugas_pokok_id", "=", tp_id]])
            if rows:
                dt_by_key[key] = rows[0]["id"]
            dt_skipped += 1
    print(f"DetilTugas: {dt_created} dibuat, {dt_skipped} sudah ada.")

    # Langkah 3: seed UraianTugas
    ut_created = ut_skipped = 0
    for item in catalog:
        tp_id = tp_by_nama.get(item["tugas_pokok"], "")
        dt_nama = item["detil_tugas"].strip()
        dt_id = dt_by_key.get((item["tugas_pokok"], dt_nama)) if dt_nama else None
        payload = {
            "kode": item["kode"],
            "uraian": item["uraian_tugas"],
            "unit": item["unit"],
            "kategori_jabatan": item["kategori_jabatan"],
            "urutan": item["urutan"],
            "tugas_pokok_id": tp_id,
        }
        if dt_id:
            payload["detil_tugas_id"] = dt_id
        result = _post("/task-inventory/uraian-tugas", payload)
        if result:
            ut_created += 1
        else:
            ut_skipped += 1
    print(f"UraianTugas: {ut_created} dibuat, {ut_skipped} sudah ada.")
    print("Selesai.")


if __name__ == "__main__":
    main()
