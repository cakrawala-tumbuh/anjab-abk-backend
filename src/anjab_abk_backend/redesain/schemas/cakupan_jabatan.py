"""Skema Pydantic cakupan jabatan redesain (sheet CAKUPAN_19), satu baris = entri x cabang."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...schemas.common import Cabang
from .kosakata import StatusPemeriksaanCakupan, StatusUnitCakupan

_POLA_ROLE = re.compile(r"^J-\d{2}$")


class CakupanJabatanCreate(BaseModel):
    """Payload entri cakupan baru; pasangan `role_kode`+`cabang` harus unik."""

    model_config = ConfigDict(extra="forbid")

    role_kode: str = Field(max_length=10, description="Kode peran paket.", examples=["J-01"])
    nama_jabatan: str = Field(min_length=1, max_length=200, description="Nama jabatan pada paket.")
    cabang: Cabang = Field(description="Cabang yayasan.")
    jabatan_id: str | None = Field(default=None, max_length=40, description="ID master jabatan.")
    status_unit: StatusUnitCakupan = "Belum diperiksa"
    pemegang_diperiksa: StatusPemeriksaanCakupan = "Belum diperiksa"
    inventori_ditinjau: StatusPemeriksaanCakupan = "Belum diperiksa"
    peta_diperkuat: StatusPemeriksaanCakupan = "Belum diperiksa"
    gap_variasi: str | None = None
    pic_kode_orang: str | None = Field(default=None, max_length=20, examples=["O-0001"])

    @field_validator("role_kode")
    @classmethod
    def _pola_role(cls, v: str) -> str:
        if not _POLA_ROLE.match(v):
            raise ValueError("role_kode harus berpola J-NN (mis. J-01).")
        return v


class CakupanJabatanUpdate(BaseModel):
    """Payload ubah parsial. `role_kode` dan `cabang` tidak dapat diubah.

    Field nullable (`jabatan_id`, `gap_variasi`, `pic_kode_orang`) boleh dikosongkan dengan
    `null`; field wajib yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    nama_jabatan: str | None = Field(default=None, min_length=1, max_length=200)
    jabatan_id: str | None = Field(default=None, max_length=40)
    status_unit: StatusUnitCakupan | None = None
    pemegang_diperiksa: StatusPemeriksaanCakupan | None = None
    inventori_ditinjau: StatusPemeriksaanCakupan | None = None
    peta_diperkuat: StatusPemeriksaanCakupan | None = None
    gap_variasi: str | None = None
    pic_kode_orang: str | None = Field(default=None, max_length=20)


class CakupanJabatanRead(BaseModel):
    """Satu entri cakupan jabatan pada satu cabang."""

    id: str = Field(description="ID entri (UUID v4).")
    role_kode: str = Field(examples=["J-01"])
    nama_jabatan: str
    cabang: Cabang
    jabatan_id: str | None
    status_unit: StatusUnitCakupan
    pemegang_diperiksa: StatusPemeriksaanCakupan
    inventori_ditinjau: StatusPemeriksaanCakupan
    peta_diperkuat: StatusPemeriksaanCakupan
    gap_variasi: str | None
    pic_kode_orang: str | None
    created_at: datetime
    updated_at: datetime
