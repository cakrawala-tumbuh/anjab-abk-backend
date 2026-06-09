"""Tulis dokumen OpenAPI ke file tanpa menjalankan server.

python scripts/export_openapi.py openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from anjab_abk_backend.main import create_app  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    schema = create_app().openapi()
    Path(out).write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI ditulis ke {out}")


if __name__ == "__main__":
    main()
