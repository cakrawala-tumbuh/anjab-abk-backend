"""Endpoint master data WCP: dimensi (read-only) dan item (edit admin-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status

from ...dependencies import (
    READ_GUARDS,
    get_wcp_dimensi_service,
    get_wcp_instrumen_service,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...wcp.schemas.dimensi import (
    WcpDimensiRead,
    WcpDimensiWithItemsRead,
    WcpItemRead,
    WcpItemUpdate,
)
from ...wcp.services.dimensi import WcpDimensiService
from ...wcp.services.instrumen import WcpInstrumenService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Dimensi tidak ditemukan."}}
_ITEM_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Item tidak ditemukan."}}
_AUTH = {
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Hanya admin yang diizinkan."},
}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "",
    response_model=list[WcpDimensiRead],
    summary="Daftar 12 dimensi WCP",
    operation_id="wcp_dimensi_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def list_dimensi(
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> list[WcpDimensiRead]:
    return service.list_dimensi()


@router.get(
    "/{kode}",
    response_model=WcpDimensiWithItemsRead,
    summary="Ambil dimensi WCP beserta 6 item-nya",
    operation_id="wcp_dimensi_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def get_dimensi(
    kode: Annotated[str, Path(description="Kode dimensi (SC/TM/AS/RC/DA/WP/PC/SS/CH/SD/PI/RA).")],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> WcpDimensiWithItemsRead:
    return service.get_dimensi(kode.upper())


@router.get(
    "/{kode}/items",
    response_model=list[WcpItemRead],
    summary="Daftar item untuk satu dimensi WCP",
    operation_id="wcp_dimensi_items",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def list_items_by_dimensi(
    kode: Annotated[str, Path(description="Kode dimensi.")],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> list[WcpItemRead]:
    dim = service.get_dimensi(kode.upper())
    return dim.items


@router.patch(
    "/items/{item_id}",
    response_model=WcpItemRead,
    summary="Ubah satu item WCP (admin)",
    operation_id="wcp_item_update",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_ITEM_NOT_FOUND},
)
def update_item(
    item_id: Annotated[str, Path(description="Kode item orisinal, mis. SC1a.")],
    payload: Annotated[WcpItemUpdate, Body()],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> WcpItemRead:
    return service.update_item(item_id, payload)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus satu item WCP dari master instrumen (admin)",
    operation_id="wcp_item_delete",
    dependencies=[Depends(require_admin)],
    responses={
        **_AUTH,
        **_ITEM_NOT_FOUND,
        422: {
            "model": ErrorResponse,
            "description": "Instrumen tidak OPEN, atau item terakhir dimensi.",
        },
    },
)
def delete_item(
    item_id: Annotated[str, Path(description="Kode item orisinal, mis. SC1a.")],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
    instrumen_service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> Response:
    # Hapus item master hanya sah saat pengumpulan data belum final (OPEN) — mencegah
    # katalog berubah di bawah analisis yang sudah/segera dijalankan (CLOSED/ANALYZED).
    instrumen = instrumen_service.get()
    if instrumen.status != "OPEN":
        raise ValidationAppError(
            f"Item hanya dapat dihapus saat instrumen WCP berstatus OPEN"
            f" (saat ini: {instrumen.status})."
        )
    service.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
