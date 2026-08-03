"""Implementasi `OpmSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

`create()` melakukan validasi lintas-domain (Jabatan, SME panel, Task Inventory)
lalu men-snapshot task terpilih TI ke `opm_sesi_task` dan membuat responden
otomatis dari responden sesi TI sumber yang sudah submit Tahap 1 — semuanya
dalam SATU transaksi (pola `taskinv/services/sesi_sql.py::_jabatan_map`,
`anjab/services/sme_panel_sql.py` untuk pre-check `ConflictError` + backstop
`IntegrityError`).

**`cabang` diturunkan, bukan input** (backlog `anjab-abk-backend#37`):
`OpmSesiModel.cabang` disalin dari `ti_sesi.cabang` sesi TI sumber saat sesi OPM
dibuat, dan uniqueness sesi berubah dari `jabatan_id` global menjadi
`(jabatan_id, cabang)` — ditegakkan di APLIKASI (bukan constraint DB) karena
`cabang` nullable.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    JabatanModel,
    OpmRespondenModel,
    OpmSesiModel,
    OpmSesiTaskModel,
    SMEPanelModel,
    TiDetilTugasModel,
    TiRespondenModel,
    TiSesiModel,
    TiTugasPokokModel,
    TiUraianTugasJabatanModel,
    TiUraianTugasModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import OpmSesiCreate, OpmSesiRead, OpmSesiTaskRead, OpmSesiUpdate, StatusSesi

# Sumber tunggal whitelist & state machine.
from .sesi import _ERR_NON_DRAFT, _VALID_TRANSITIONS, SEARCHABLE_FIELDS


def _sesi_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=OpmSesiModel.id),
        "jabatan_id": FieldSpec(column=OpmSesiModel.jabatan_id),
        "ti_sesi_id": FieldSpec(column=OpmSesiModel.ti_sesi_id),
        "cabang": FieldSpec(column=OpmSesiModel.cabang),
        "periode": FieldSpec(column=OpmSesiModel.periode),
        "status": FieldSpec(column=OpmSesiModel.status),
        "created_at": FieldSpec(
            column=OpmSesiModel.created_at, order_column=OpmSesiModel.created_at
        ),
    }


def _task_to_read(rec: OpmSesiTaskModel) -> OpmSesiTaskRead:
    return OpmSesiTaskRead(
        task_kode=rec.task_kode,
        uraian_tugas=rec.uraian_tugas,
        tugas_pokok=rec.tugas_pokok,
        detil_tugas=rec.detil_tugas,
        urutan=rec.urutan,
        std_importance=rec.std_importance,
        std_frequency=rec.std_frequency,
        std_criticality=rec.std_criticality,
    )


def _to_read(rec: OpmSesiModel, jabatan_nama: str | None = None) -> OpmSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return OpmSesiRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        jabatan_nama=jabatan_nama,
        ti_sesi_id=rec.ti_sesi_id,
        cabang=rec.cabang,  # type: ignore[arg-type]
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        min_responden=rec.min_responden,
        max_responden=rec.max_responden,
        jumlah_task=len(rec.task_links),
        catatan=rec.catatan,
        created_at=created,
    )


class SqlOpmSesiService:
    """`OpmSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sesi_id: str) -> OpmSesiModel:
        rec = self._s.get(OpmSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
        return rec

    def _jabatan_map(self, jabatan_ids: list[str]) -> dict[str, str]:
        if not jabatan_ids:
            return {}
        rows = self._s.scalars(select(JabatanModel).where(JabatanModel.id.in_(jabatan_ids))).all()
        return {j.id: j.nama for j in rows}

    def _flush_checked(self, *, on_conflict: str) -> None:
        """Flush dalam SAVEPOINT; petakan **hanya** `UniqueViolation` → 409.

        Pelanggaran integritas lain (`ForeignKeyViolation`, NOT NULL, dst.) sengaja
        dibiarkan naik apa adanya: memetakannya jadi "sudah ada" menyamarkan bug
        nyata sebagai konflik duplikat yang mustahil. Persis itu yang menyembunyikan
        `ForeignKeyViolation` di `create()` selama dua sesi pengujian produksi.
        """
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise ConflictError(on_conflict) from exc
            raise

    def list(self, *, limit: int, offset: int) -> tuple[list[OpmSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(OpmSesiModel)) or 0
        rows = self._s.scalars(
            select(OpmSesiModel)
            .order_by(OpmSesiModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total

    def get(self, sesi_id: str) -> OpmSesiRead:
        rec = self._get_model(sesi_id)
        jab = self._s.get(JabatanModel, rec.jabatan_id)
        return _to_read(rec, jab.nama if jab else None)

    def create(self, data: OpmSesiCreate) -> OpmSesiRead:
        # 1. Jabatan wajib ada.
        jabatan = self._s.get(JabatanModel, data.jabatan_id)
        if jabatan is None:
            raise ValidationAppError(f"Jabatan '{data.jabatan_id}' tidak ditemukan.")

        # 2. min <= max.
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")

        # 3. Jabatan wajib punya SME panel dengan anggota. Gate keanggotaan ini TETAP
        # ada apa adanya (turunan aturan #37) — yang berubah hanya SUMBER baris
        # responden di langkah 6, bukan gerbang keberadaan panel ini.
        panel = self._s.scalar(
            select(SMEPanelModel).where(SMEPanelModel.jabatan_id == data.jabatan_id)
        )
        if panel is None or not panel.anggota:
            raise ValidationAppError(
                "Jabatan ini belum memiliki SME panel / panel belum punya anggota."
            )

        # 4. TiSesi sumber wajib ada, milik jabatan yang sama, dan sudah frozen.
        # Dipindah SEBELUM pre-check konflik (langkah 5) karena `cabang` OPM
        # DITURUNKAN dari `ti.cabang` — pre-check butuh nilai ini lebih dulu.
        ti = self._s.get(TiSesiModel, data.ti_sesi_id)
        if ti is None:
            raise ValidationAppError(f"Sesi Task Inventory '{data.ti_sesi_id}' tidak ditemukan.")
        if ti.jabatan_id != data.jabatan_id:
            raise ValidationAppError("Sesi Task Inventory yang dipilih bukan untuk jabatan ini.")
        if not ti.task_frozen:
            raise ValidationAppError(
                "Sesi Task Inventory belum dibekukan (belum melewati Tahap 3)."
            )
        terpilih = ti.task_terpilih or []
        if not terpilih:
            raise ValidationAppError(
                "Sesi Task Inventory tidak memiliki task terpilih untuk dijadikan snapshot."
            )
        cabang = ti.cabang

        # 5. Pre-check satu sesi OPM per (jabatan_id, cabang) — backstop unique index
        # `jabatan_id` di bawah tidak lagi cukup (langkah 4 di migrasi `981b2e1945b0`
        # melepas `unique=True`-nya). Dicek di lapisan APLIKASI, BUKAN via `WHERE
        # cabang = :cabang` di SQL: `cabang` nullable, dan PostgreSQL memperlakukan
        # NULL sebagai distinct pada unique constraint MAUPUN pada operator `=` (
        # `NULL = NULL` bernilai UNKNOWN, bukan TRUE) — comparison Python di bawah
        # (`None == None` bernilai True) yang menutup celah dua sesi ber-`cabang
        # IS NULL` untuk jabatan yang sama.
        existing = self._s.scalars(
            select(OpmSesiModel).where(OpmSesiModel.jabatan_id == data.jabatan_id)
        ).all()
        if any(r.cabang == cabang for r in existing):
            raise ConflictError(
                f"Sesi OPM untuk jabatan '{jabatan.nama}' cabang '{cabang}' sudah ada."
            )

        # 6. Calon responden = responden sesi TI SUMBER yang SUDAH submit Tahap 1 —
        # BUKAN seluruh anggota SME panel (backlog #37). Himpunan task terpilih
        # berbeda antar cabang, jadi penilai OPM harus orang yang benar-benar
        # mengerjakan sesi TI ini. `nama`/`partisipan_id` diambil LANGSUNG dari
        # baris `TiRespondenModel` (sudah diresolusi saat responden TI dibuat/
        # di-auto-populate) — tidak perlu query `PartisipanModel` tambahan.
        # `max_responden` dibandingkan ke himpunan INI, bukan ke `panel.anggota`.
        ti_submitters = self._s.scalars(
            select(TiRespondenModel).where(
                TiRespondenModel.sesi_id == data.ti_sesi_id,
                TiRespondenModel.tahap1_submit.is_(True),
            )
        ).all()
        if len(ti_submitters) > data.max_responden:
            raise ValidationAppError(
                f"Jumlah responden sesi Task Inventory yang sudah submit Tahap 1"
                f" ({len(ti_submitters)}) melebihi max_responden ({data.max_responden})."
            )

        konflik = f"Sesi OPM untuk jabatan '{jabatan.nama}' cabang '{cabang}' sudah ada."

        rec = OpmSesiModel(
            id=f"opses_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            ti_sesi_id=data.ti_sesi_id,
            cabang=cabang,
            periode=data.periode,
            status="DRAFT",
            min_responden=data.min_responden,
            max_responden=data.max_responden,
            catatan=data.catatan,
        )
        self._s.add(rec)
        # Flush sesi TERLEBIH DAHULU, sebelum insert responden auto-populate di
        # langkah 8. `OpmRespondenModel.sesi_id` adalah FK murni tanpa
        # `relationship()` ORM ke `OpmSesiModel` — tanpa flush eksplisit ini, urutan
        # INSERT saat flush gabungan TIDAK terjamin (unit-of-work SQLAlchemy
        # mengurutkan INSERT berdasar `relationship()` yang dikonfigurasi, bukan
        # sekadar FK kolom mentah), sehingga bisa mencoba INSERT responden sebelum
        # sesi ada → `ForeignKeyViolation`. Pola sama dengan `SqlTiSesiService.create()`.
        # Tetap lewat `_flush_checked` — kini backstop-nya bukan lagi unique index
        # `jabatan_id` (sudah dilepas), melainkan pre-check Python langkah 5; race dua
        # create bersamaan untuk `(jabatan_id, cabang)` yang sama bisa lolos keduanya
        # (diterima, identik dengan perilaku TI). `rec.task_links` (langkah 7) TIDAK
        # terpengaruh — itu relationship, urutannya memang dijamin.
        self._flush_checked(on_conflict=konflik)

        # 7. Snapshot task terpilih TI → opm_sesi_task. `kode`/`tugas_pokok_id`/
        # `detil_tugas_id`/`urutan` kini hidup di `TiUraianTugasJabatanModel` (link
        # per-jabatan); `uraian` tetap di kanonik `TiUraianTugasModel` — join keduanya.
        ut_rows = self._s.execute(
            select(TiUraianTugasJabatanModel, TiUraianTugasModel.uraian)
            .join(
                TiUraianTugasModel,
                TiUraianTugasModel.id == TiUraianTugasJabatanModel.uraian_tugas_id,
            )
            .where(TiUraianTugasJabatanModel.kode.in_(terpilih))
        ).all()
        ut_by_kode = {link.kode: (link, uraian_text) for link, uraian_text in ut_rows}
        tp_map = self._s.scalars(
            select(TiTugasPokokModel).where(
                TiTugasPokokModel.id.in_({link.tugas_pokok_id for link, _ in ut_rows})
            )
        ).all()
        tp_by_id = {t.id: t.nama for t in tp_map}
        detil_ids = {link.detil_tugas_id for link, _ in ut_rows if link.detil_tugas_id is not None}
        dt_map = (
            self._s.scalars(
                select(TiDetilTugasModel).where(TiDetilTugasModel.id.in_(detil_ids))
            ).all()
            if detil_ids
            else []
        )
        dt_by_id = {d.id: d.nama for d in dt_map}

        for kode in sorted(terpilih):
            entry = ut_by_kode.get(kode)
            if entry is None:
                continue  # tidak seharusnya terjadi; kode berasal dari snapshot TI valid
            link, uraian_text = entry
            rec.task_links.append(
                OpmSesiTaskModel(
                    task_kode=kode,
                    uraian_tugas=uraian_text,
                    tugas_pokok=tp_by_id.get(link.tugas_pokok_id, ""),
                    detil_tugas=dt_by_id.get(link.detil_tugas_id) if link.detil_tugas_id else None,
                    urutan=link.urutan,
                    # Nilai standar OPM DISALIN dari katalog TI di titik waktu ini —
                    # beku, tidak pernah disegarkan ulang (backlog #34). `link` tidak
                    # punya nilai standar (mis. task hasil materialisasi usulan Tahap 1)
                    # → ketiganya tetap `None` di sini, bukan error.
                    std_importance=link.std_opm_importance,
                    std_frequency=link.std_opm_frequency,
                    std_criticality=link.std_opm_criticality,
                )
            )

        # 8. Auto-responden dari submitter Tahap 1 sesi TI sumber (langkah 6) — bukan
        # anggota SME panel. `nama`/`partisipan_id` disalin langsung dari baris
        # `TiRespondenModel`; nol submitter → sesi tetap dibuat kosong tanpa error
        # (konsisten dengan perilaku "panel kosong" yang sudah ada sebelumnya).
        for r in ti_submitters:
            self._s.add(
                OpmRespondenModel(
                    id=f"oprs_{uuid.uuid4().hex[:8]}",
                    sesi_id=rec.id,
                    nama=r.nama,
                    jabatan_label=jabatan.nama,
                    partisipan_id=r.partisipan_id,
                    sudah_submit=False,
                )
            )

        self._flush_checked(on_conflict=konflik)
        return _to_read(rec, jabatan.nama)

    def update(self, sesi_id: str, data: OpmSesiUpdate) -> OpmSesiRead:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT":
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
        changes = data.model_dump(exclude_unset=True)
        new_min = changes.get("min_responden", rec.min_responden)
        new_max = changes.get("max_responden", rec.max_responden)
        if new_min > new_max:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
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

    def transition(self, sesi_id: str, target: StatusSesi) -> OpmSesiRead:
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

    def list_task(
        self, sesi_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[OpmSesiTaskRead], int]:
        self._get_model(sesi_id)
        total = (
            self._s.scalar(
                select(func.count())
                .select_from(OpmSesiTaskModel)
                .where(OpmSesiTaskModel.sesi_id == sesi_id)
            )
            or 0
        )
        stmt = (
            select(OpmSesiTaskModel)
            .where(OpmSesiTaskModel.sesi_id == sesi_id)
            .order_by(OpmSesiTaskModel.urutan, OpmSesiTaskModel.task_kode)
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        rows = self._s.scalars(stmt).all()
        return [_task_to_read(r) for r in rows], total

    def get_task_kodes(self, sesi_id: str) -> set[str]:
        tasks, _ = self.list_task(sesi_id)
        return {t.task_kode for t in tasks}

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[OpmSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _sesi_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [OpmSesiModel.created_at.desc()]
        total = self._s.scalar(select(func.count()).select_from(OpmSesiModel).where(cond)) or 0
        rows = self._s.scalars(
            select(OpmSesiModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        jmap = self._jabatan_map(list({r.jabatan_id for r in rows}))
        return [_to_read(r, jmap.get(r.jabatan_id)) for r in rows], total
