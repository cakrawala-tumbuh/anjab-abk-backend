"""Helper bersama untuk header `Link` (RFC 5988) pada endpoint yang dipaginasi.

Diekstrak dari salinan lokal `_pagination_links` di router resource master (mis.
`api/v1/jabatan.py`) agar endpoint list koleksi anak memakai perilaku yang sama:
memancarkan relasi `first`/`prev`/`next`/`last` berbasis `limit`/`offset`/`total`.
"""

from __future__ import annotations

from fastapi import Request, Response


def set_pagination_links(
    response: Response, request: Request, total: int, limit: int, offset: int
) -> None:
    """Pasang header `Link` (first/prev/next/last) pada `response`.

    `prev` hanya dipancarkan bila `offset > 0`; `next` hanya bila masih ada baris
    setelah halaman ini (`offset + limit < total`); `last` menunjuk offset halaman
    terakhir. URL mempertahankan query string selain `limit`/`offset`.
    """
    base = request.url.remove_query_params(["limit", "offset"])

    def url(off: int) -> str:
        return str(base.include_query_params(limit=limit, offset=off))

    links = [f'<{url(0)}>; rel="first"']
    if offset > 0:
        links.append(f'<{url(max(0, offset - limit))}>; rel="prev"')
    if offset + limit < total:
        links.append(f'<{url(offset + limit)}>; rel="next"')
    if total > 0 and limit > 0:
        links.append(f'<{url(((total - 1) // limit) * limit)}>; rel="last"')
    response.headers["Link"] = ", ".join(links)
