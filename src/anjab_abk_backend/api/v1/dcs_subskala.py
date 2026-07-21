"""Endpoint master data DCS: sub-skala (read-only) dan item (edit admin-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status

from ...dcs.schemas.subskala import (
    DcsItemRead,
    DcsItemUpdate,
    DcsSubSkalaRead,
    DcsSubSkalaWithItemsRead,
)
from ...dcs.services.instrumen import DcsInstrumenService
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import (
    READ_GUARDS,
    get_dcs_instrumen_service,
    get_dcs_subskala_service,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sub-skala tidak ditemukan."}}
_ITEM_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Item tidak ditemukan."}}
_AUTH = {
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Hanya admin yang diizinkan."},
}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "",
    response_model=list[DcsSubSkalaRead],
    summary="Daftar 3 sub-skala DCS",
    operation_id="dcs_subskala_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def list_sub_skala(
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> list[DcsSubSkalaRead]:
    return service.list_sub_skala()


@router.get(
    "/{kode}",
    response_model=DcsSubSkalaWithItemsRead,
    summary="Ambil sub-skala DCS beserta 14 item-nya",
    operation_id="dcs_subskala_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def get_sub_skala(
    kode: Annotated[str, Path(description="Kode sub-skala (DEMAND/CONTROL/SUPPORT).")],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> DcsSubSkalaWithItemsRead:
    return service.get_sub_skala(kode.upper())


@router.get(
    "/{kode}/items",
    response_model=list[DcsItemRead],
    summary="Daftar item untuk satu sub-skala DCS",
    operation_id="dcs_subskala_items",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def list_items_by_sub_skala(
    kode: Annotated[str, Path(description="Kode sub-skala.")],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> list[DcsItemRead]:
    sk = service.get_sub_skala(kode.upper())
    return sk.items


@router.patch(
    "/items/{item_id}",
    response_model=DcsItemRead,
    summary="Ubah satu item DCS (admin)",
    operation_id="dcs_item_update",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_ITEM_NOT_FOUND},
)
def update_item(
    item_id: Annotated[str, Path(description="Kode item orisinal, mis. D1a.")],
    payload: Annotated[DcsItemUpdate, Body()],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> DcsItemRead:
    return service.update_item(item_id, payload)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus satu item DCS dari master instrumen (admin)",
    operation_id="dcs_item_delete",
    dependencies=[Depends(require_admin)],
    responses={
        **_AUTH,
        **_ITEM_NOT_FOUND,
        422: {
            "model": ErrorResponse,
            "description": "Instrumen tidak OPEN, atau item terakhir sub-skala.",
        },
    },
)
def delete_item(
    item_id: Annotated[str, Path(description="Kode item orisinal, mis. D1a.")],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
    instrumen_service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> Response:
    # Hapus item master hanya sah saat pengumpulan data belum final (OPEN) — mencegah
    # katalog berubah di bawah analisis yang sudah/segera dijalankan (CLOSED/ANALYZED).
    instrumen = instrumen_service.get()
    if instrumen.status != "OPEN":
        raise ValidationAppError(
            f"Item hanya dapat dihapus saat instrumen DCS berstatus OPEN"
            f" (saat ini: {instrumen.status})."
        )
    service.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
