"""Implementasi `TiSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiSesiService` TANPA mengubah kontrak Protocol.

Uniqueness sesi diperiksa di aplikasi (sama dengan InMemory): (jabatan_id, cabang).
State machine `_VALID_TRANSITIONS` & whitelist search dipakai ULANG dari modul InMemory.

`task_terpilih` model bernilai None sampai di-freeze (`task_frozen=True`);
`freeze_task_terpilih` mengisi tabel anak `ti_sesi_task_terpilih`. `get_task_terpilih`
mengembalikan [] bila belum di-freeze.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.services.partisipan import PartisipanService
from ...core.services.sekolah import SekolahService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import JabatanModel, SMEPanelModel, TiSesiModel, TiSesiTaskTerpilihModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import StatusSesi, TiSesiCreate, TiSesiRead, TiSesiUpdate
from .responden_sql import _resolve_cabang_partisipan, assign_ti_responden_banyak

# Sumber tunggal whitelist & state machine.
from .sesi import _ERR_NON_DRAFT, _VALID_TRANSITIONS, SEARCHABLE_FIELDS


def _sesi_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiSesiModel.id),
        "jabatan_id": FieldSpec(column=TiSesiModel.jabatan_id),
        "cabang": FieldSpec(column=TiSesiModel.cabang),
        "status": FieldSpec(column=TiSesiModel.status),
        "created_at": FieldSpec(column=TiSesiModel.created_at, order_column=TiSesiModel.created_at),
    }


def _to_read(rec: TiSesiModel, jabatan_nama: str | None = None) -> TiSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    terpilih = rec.task_terpilih  # None bila belum di-freeze
    return TiSesiRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        jabatan_nama=jabatan_nama,
        cabang=rec.cabang,  # type: ignore[arg-type]
        status=rec.status,  # type: ignore[arg-type]
        koordinator_id=rec.koordinator_id,
        jumlah_task_terpilih=(len(terpilih) if terpilih is not None else None),
        catatan=rec.catatan,
        created_at=created,
    )


class SqlTiSesiService:
    """`TiSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(
        self,
        session: Session,
        partisipan_service: PartisipanService,
        sekolah_service: SekolahService,
    ) -> None:
        self._s = session
        self._par = partisipan_service
        self._sek = sekolah_service

    def _get_model(self, sesi_id: str) -> TiSesiModel:
        rec = self._s.get(TiSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi Task Inventory '{sesi_id}' tidak ditemukan.")
        return rec

    def _jabatan_map(self, jabatan_ids: list[str]) -> dict[str, str]:
        if not jabatan_ids:
            return {}
        rows = self._s.scalars(select(JabatanModel).where(JabatanModel.id.in_(jabatan_ids))).all()
        return {j.id: j.nama for j in rows}

    def list(self, *, limit: int, offset: int) -> tuple[list[TiSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiSesiModel)) or 0
        rows = self._s.scalars(
            select(TiSesiModel).order_by(TiSesiModel.created_at.desc()).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total

    def get(self, sesi_id: str) -> TiSesiRead:
        rec = self._get_model(sesi_id)
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def create(self, data: TiSesiCreate) -> TiSesiRead:
        """Buat sesi Task Inventory baru untuk `data.jabatan_id` + `data.cabang`.

        Auto-populate responden (backlog `anjab-abk-backend#41`, lanjutan
        `#37`/`#40`): anggota SME panel jabatan ini yang cabang sekolahnya
        **diketahui dan berbeda** dari `data.cabang` dilewati (`skipped`
        beralasan `beda_cabang`, lihat `assign_ti_responden_banyak`) —
        anggota bercabang sama atau tidak diketahui tetap masuk ("tidak tahu
        ≠ salah"). Sesi tanpa `cabang` (`data.cabang is None`) tetap mendapat
        SELURUH anggota panel seperti perilaku sebelum #41.

        `koordinator_id` **murni dari payload** — pewarisan dari
        `SMEPanelModel.koordinator_id` (entri Revisi Desain `[2026-07-13]`)
        **dihentikan** oleh #41; kolom `SMEPanelModel.koordinator_id` sendiri
        tidak dihapus, hanya berhenti dibaca di jalur ini. Bila
        `data.koordinator_id` diisi, ditolak (`ValidationAppError`, 422) bila
        cabang sekolahnya diketahui dan berbeda dari `data.cabang` (keduanya
        diketahui) — pesan menyebut kedua nilainya.

        Args:
            data: payload pembuatan sesi (`jabatan_id`, `cabang`,
                `koordinator_id` opsional, `catatan` opsional).

        Returns:
            Sesi yang baru dibuat (`status="DRAFT"`).

        Raises:
            ConflictError: sesi untuk `(jabatan_id, cabang)` ini sudah ada.
            ValidationAppError: `koordinator_id` bercabang beda dari `cabang`
                sesi (keduanya diketahui).
        """
        dup = self._s.scalar(
            select(TiSesiModel.id).where(
                TiSesiModel.jabatan_id == data.jabatan_id,
                TiSesiModel.cabang == data.cabang,
            )
        )
        if dup is not None:
            raise ConflictError(
                f"Sesi untuk jabatan '{data.jabatan_id}' cabang '{data.cabang}' sudah ada."
            )
        # Panel unik per jabatan (SMEPanelModel.jabatan_id unique) → satu lookup,
        # dipakai HANYA untuk auto-assign anggota sebagai responden (setelah rec
        # di-flush). Pewarisan koordinator dari panel DIHENTIKAN (backlog #41) —
        # koordinator_id murni dari payload, digerbang di bawah. Best-effort:
        # panel tidak ada/kosong → sesi tetap dibuat (tidak error).
        panel = self._s.scalar(
            select(SMEPanelModel).where(SMEPanelModel.jabatan_id == data.jabatan_id)
        )

        if data.koordinator_id is not None and data.cabang is not None:
            kor_cabang = _resolve_cabang_partisipan(self._par, self._sek, data.koordinator_id)
            if kor_cabang is not None and kor_cabang != data.cabang:
                raise ValidationAppError(
                    f"Koordinator bercabang '{kor_cabang}' tidak dapat ditugaskan"
                    f" ke sesi bercabang '{data.cabang}'."
                )

        rec = TiSesiModel(
            id=f"tises_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            cabang=data.cabang,
            status="DRAFT",
            koordinator_id=data.koordinator_id,
            catatan=data.catatan,
        )
        self._s.add(rec)
        # Flush sesi TERLEBIH DAHULU, sebelum insert responden auto-populate di
        # bawah. `TiRespondenModel.sesi_id` adalah FK murni tanpa `relationship()`
        # ORM ke `TiSesiModel` — tanpa flush eksplisit ini, urutan INSERT saat
        # flush gabungan TIDAK terjamin (unit-of-work SQLAlchemy mengurutkan
        # INSERT berdasar `relationship()` yang dikonfigurasi, bukan sekadar FK
        # kolom mentah), sehingga bisa mencoba INSERT responden sebelum sesi ada
        # → `ForeignKeyViolation`. Diverifikasi lewat E2E yang mereproduksi
        # persis kegagalan ini (lihat CHANGELOG).
        self._s.flush()

        # Auto-populate best-effort: anggota SME panel jabatan ini langsung jadi
        # responden, tanpa batas atas, disaring cabang (backlog #41). Panel
        # tidak ada/kosong → sesi tetap dibuat kosong (tidak error).
        if panel is not None and panel.anggota:
            assign_ti_responden_banyak(
                self._s,
                rec.id,
                panel.partisipan_ids,
                cabang=data.cabang,
                sekolah_service=self._sek,
            )
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def update(self, sesi_id: str, data: TiSesiUpdate) -> TiSesiRead:
        """Perbarui sesi Task Inventory (field apa pun hanya saat `DRAFT`,
        kecuali `koordinator_id` yang dapat diperbarui kapan pun).

        **Gerbang cabang koordinator** (backlog `anjab-abk-backend#41`): bila
        payload mengisi `koordinator_id` non-null, ditolak (`ValidationAppError`,
        422) bila cabang target sesi (`data.cabang` bila ikut diubah pada
        payload yang sama, selain itu `rec.cabang` saat ini) **diketahui** dan
        cabang sekolah koordinator (`_resolve_cabang_partisipan`) juga
        **diketahui** tapi berbeda. Salah satu cabang tidak diketahui →
        diloloskan ("tidak tahu ≠ salah").

        Args:
            sesi_id: ID sesi Task Inventory.
            data: field yang diperbarui (`exclude_unset` — hanya field yang
                dikirim yang diterapkan).

        Returns:
            Sesi setelah pembaruan.

        Raises:
            NotFoundError: `sesi_id` tidak ditemukan.
            ValidationAppError: sesi bukan `DRAFT` dan ada field selain
                `koordinator_id` yang diubah; atau `koordinator_id` bercabang
                beda dari cabang target sesi (keduanya diketahui).
        """
        rec = self._get_model(sesi_id)
        changes = data.model_dump(exclude_unset=True)
        if rec.status != "DRAFT" and any(k != "koordinator_id" for k in changes):
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
        if "koordinator_id" in changes and changes["koordinator_id"] is not None:
            target_cabang = changes.get("cabang", rec.cabang)
            if target_cabang is not None:
                kor_cabang = _resolve_cabang_partisipan(
                    self._par, self._sek, changes["koordinator_id"]
                )
                if kor_cabang is not None and kor_cabang != target_cabang:
                    raise ValidationAppError(
                        f"Koordinator bercabang '{kor_cabang}' tidak dapat ditugaskan"
                        f" ke sesi bercabang '{target_cabang}'."
                    )
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def delete(self, sesi_id: str, *, paksa: bool = False) -> None:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT" and not paksa:
            raise ValidationAppError(_ERR_NON_DRAFT)
        self._s.delete(rec)
        self._s.flush()
        self._s.expire_all()

    def freeze_task_terpilih(self, sesi_id: str, kodes: list[str]) -> TiSesiRead:
        """Bekukan himpunan task terpilih saat transisi TAHAP2 → TAHAP3."""
        rec = self._get_model(sesi_id)
        if rec.status != "TAHAP2":
            raise ValidationAppError(
                f"Himpunan task hanya dapat dibekukan dari status TAHAP2"
                f" (saat ini: {rec.status})."
            )
        if not kodes:
            raise ValidationAppError("Tidak ada task relevan; tidak dapat masuk TAHAP3.")
        rec.task_terpilih_links.clear()
        for kode in sorted(set(kodes)):
            rec.task_terpilih_links.append(TiSesiTaskTerpilihModel(task_kode=kode))
        rec.task_frozen = True
        rec.status = "TAHAP3"
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def batalkan_tahap3(self, sesi_id: str, alasan: str) -> TiSesiRead:
        """Balikkan sesi TAHAP3 ke TAHAP2 (unfreeze), membatalkan pembekuan task.

        Menghapus seluruh baris `rec.task_terpilih_links` (tabel anak
        `ti_sesi_task_terpilih`), lalu mengembalikan `task_frozen` ke `False` dan
        `status` ke `"TAHAP2"`. Tidak menyentuh `TiRespondenModel`
        (`tahap1_submit`/`tahap3_submit` tetap apa adanya) maupun baris
        `ti_seleksi`/`ti_detail`/`ti_usulan_task` — hanya status sesi dan link task
        terpilih yang dibalik.

        Args:
            sesi_id: ID sesi Task Inventory.
            alasan: Alasan pembatalan (dipakai pemanggil untuk audit log; method ini
                sendiri tidak mencatatnya — audit terjadi di lapisan endpoint).

        Returns:
            `TiSesiRead` sesi setelah `status` kembali ke `"TAHAP2"` dan
            `jumlah_task_terpilih` menjadi `None`.

        Raises:
            NotFoundError: `sesi_id` tidak ditemukan.
            ValidationAppError: `status` sesi saat ini bukan `"TAHAP3"`.
        """
        rec = self._get_model(sesi_id)
        if rec.status != "TAHAP3":
            raise ValidationAppError(
                "Hanya sesi berstatus TAHAP3 yang dapat dibatalkan ke TAHAP2"
                f" (saat ini: {rec.status})."
            )
        rec.task_terpilih_links.clear()
        rec.task_frozen = False
        rec.status = "TAHAP2"
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def get_task_terpilih(
        self, sesi_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[str], int]:
        rec = self._get_model(sesi_id)
        terpilih = rec.task_terpilih
        kodes = list(terpilih) if terpilih is not None else []
        total = len(kodes)
        page = kodes[offset:] if limit is None else kodes[offset : offset + limit]
        return page, total

    def transition(self, sesi_id: str, target: StatusSesi) -> TiSesiRead:
        rec = self._get_model(sesi_id)
        expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
        if expected != target:
            raise ValidationAppError(
                f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
            )
        rec.status = target
        self._s.flush()
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TiSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _sesi_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [TiSesiModel.created_at.desc()]
        total = self._s.scalar(select(func.count()).select_from(TiSesiModel).where(cond)) or 0
        rows = self._s.scalars(
            select(TiSesiModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total
