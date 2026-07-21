"""Test seeding item DCS/WCP bersifat first-run (anti-resurrection).

`initdb` menjalankan `seed_all` SETIAP boot container. Bila seeding item bersifat
top-up per-baris, item yang sengaja DIHAPUS admin lewat API akan muncul lagi
("resurrection") pada redeploy/restart berikutnya. Test ini menegaskan seeding item
dilewati saat tabel item sudah berisi, sehingga penghapusan bertahan.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from anjab_abk_backend.seed_db import _seed_dcs, _seed_wcp

DCS_ITEM_URL = "/api/v1/dcs/sub-skala/DEMAND/items"
WCP_ITEM_URL = "/api/v1/wcp/dimensi/SC/items"


def test_seed_dcs_tidak_resurrect_item_terhapus(client: TestClient, db_session: Session) -> None:
    assert client.delete("/api/v1/dcs/sub-skala/items/D8").status_code == 204
    # Simulasikan seeding boot berikutnya pada DB yang sudah berisi item.
    _seed_dcs(db_session)
    item_ids = [i["item_id"] for i in client.get(DCS_ITEM_URL).json()]
    assert "D8" not in item_ids


def test_seed_wcp_tidak_resurrect_item_terhapus(client: TestClient, db_session: Session) -> None:
    assert client.delete("/api/v1/wcp/dimensi/items/SC1a").status_code == 204
    _seed_wcp(db_session)
    item_ids = [i["item_id"] for i in client.get(WCP_ITEM_URL).json()]
    assert "SC1a" not in item_ids
