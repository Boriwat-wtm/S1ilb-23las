import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import Numeric, Select, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..config import settings
from ..deps import DbSession, LedgerRead, LedgerWrite
from ..models import DIR_IN, DIR_OUT, Category, Entry, User
from ..schemas import (
    CategoryOut,
    CategoryTotal,
    EntryCreate,
    EntryOut,
    EntryPage,
    EntryUpdate,
    LedgerSummary,
    LedgerTotals,
    SignedUrlResponse,
    UserOut,
    UserTotal,
)
from ..storage import create_signed_url, delete_slip
from ..timeutil import current_month, day_end_utc, day_start_utc, month_bounds_utc, to_local

router = APIRouter(prefix="/ledgers/{ledger_id}/entries", tags=["entries"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sum_direction(direction: str):
    return func.coalesce(
        func.sum(case((Entry.direction == direction, Entry.amount), else_=0)), 0
    ).cast(Numeric(14, 2))


def _apply_filters(
    stmt: Select,
    *,
    ledger_id: int,
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    created_by_id: int | None = None,
    direction: str | None = None,
    q: str | None = None,
) -> Select:
    # Ledger scoping is not optional and not a caller's responsibility — it is
    # applied here, in the one place every query passes through.
    stmt = stmt.where(Entry.ledger_id == ledger_id)

    if month:
        try:
            start, end = month_bounds_utc(month)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        stmt = stmt.where(Entry.occurred_at >= start, Entry.occurred_at < end)
    if date_from:
        stmt = stmt.where(Entry.occurred_at >= day_start_utc(date_from))
    if date_to:
        stmt = stmt.where(Entry.occurred_at < day_end_utc(date_to))
    if category_id is not None:
        stmt = stmt.where(Entry.category_id == category_id)
    if created_by_id is not None:
        stmt = stmt.where(Entry.created_by_id == created_by_id)
    if direction in (DIR_IN, DIR_OUT):
        stmt = stmt.where(Entry.direction == direction)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Entry.description.ilike(needle), Entry.note.ilike(needle))
        )
    return stmt


def _load(db, ledger_id: int, entry_id: int) -> Entry:
    entry = db.execute(
        select(Entry)
        .options(joinedload(Entry.category), joinedload(Entry.created_by))
        .where(Entry.id == entry_id, Entry.ledger_id == ledger_id)
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
        )
    return entry


def _totals(db, ledger_id: int, **filters) -> LedgerTotals:
    tin, tout, count = db.execute(
        _apply_filters(
            select(_sum_direction(DIR_IN), _sum_direction(DIR_OUT), func.count(Entry.id)),
            ledger_id=ledger_id,
            **filters,
        )
    ).one()
    return LedgerTotals(
        total_in=Decimal(tin),
        total_out=Decimal(tout),
        balance=Decimal(tin) - Decimal(tout),
        count=count,
    )


def _check_category(db, ledger_id: int, category_id: int | None) -> None:
    """A category from another ledger must not be attachable here."""
    if category_id is None:
        return
    ok = db.execute(
        select(Category.id).where(
            Category.id == category_id, Category.ledger_id == ledger_id
        )
    ).scalar_one_or_none()
    if ok is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ไม่พบหมวดหมู่ที่เลือกในสมุดนี้",
        )


# --------------------------------------------------------------------------
# static paths first — otherwise "/summary" is parsed as an entry id
# --------------------------------------------------------------------------
@router.get("/summary", response_model=LedgerSummary)
def summary(
    ctx: LedgerRead,
    db: DbSession,
    month: str = Query(default_factory=current_month, description="YYYY-MM"),
) -> LedgerSummary:
    """Both ledger kinds read this. A cashflow book cares about `period`; a debt
    book reads `lifetime.balance` as the amount still owed."""
    ledger_id = ctx.ledger.id
    try:
        start, end = month_bounds_utc(month)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    window = (
        Entry.ledger_id == ledger_id,
        Entry.occurred_at >= start,
        Entry.occurred_at < end,
    )

    by_category_rows = db.execute(
        select(Category, _sum_direction(DIR_IN), _sum_direction(DIR_OUT), func.count(Entry.id))
        .select_from(Entry)
        .outerjoin(Category, Entry.category_id == Category.id)
        .where(*window)
        .group_by(Category.id)
        .order_by(_sum_direction(DIR_OUT).desc())
    ).all()

    by_user_rows = db.execute(
        select(User, _sum_direction(DIR_IN), _sum_direction(DIR_OUT), func.count(Entry.id))
        .select_from(Entry)
        .join(User, Entry.created_by_id == User.id)
        .where(*window)
        .group_by(User.id)
        .order_by(_sum_direction(DIR_OUT).desc())
    ).all()

    return LedgerSummary(
        month=month,
        kind=ctx.ledger.kind,
        period=_totals(db, ledger_id, month=month),
        lifetime=_totals(db, ledger_id),
        by_category=[
            CategoryTotal(
                category=CategoryOut.model_validate(cat) if cat else None,
                total_in=Decimal(tin),
                total_out=Decimal(tout),
                count=count,
            )
            for cat, tin, tout, count in by_category_rows
        ],
        by_user=[
            UserTotal(
                user=UserOut.model_validate(user),
                total_in=Decimal(tin),
                total_out=Decimal(tout),
                count=count,
            )
            for user, tin, tout, count in by_user_rows
        ],
    )


@router.get("/export.csv")
def export_csv(
    ctx: LedgerRead,
    db: DbSession,
    month: str | None = Query(None, description="YYYY-MM, ว่าง = ทั้งหมด"),
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    created_by_id: int | None = None,
    direction: str | None = None,
    q: str | None = None,
) -> Response:
    stmt = _apply_filters(
        select(Entry).options(joinedload(Entry.category), joinedload(Entry.created_by)),
        ledger_id=ctx.ledger.id,
        month=month,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        created_by_id=created_by_id,
        direction=direction,
        q=q,
    ).order_by(Entry.occurred_at.asc())
    rows = db.execute(stmt).scalars().all()

    is_debt = ctx.ledger.kind == "debt"
    in_label, out_label = ("หนี้เพิ่ม", "จ่ายคืน") if is_debt else ("รายรับ", "รายจ่าย")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["วันที่", "เวลา", "รายการ", "ประเภท", "จำนวนเงิน", "หมวดหมู่", "คนลง", "หมายเหตุ", "ที่มา"]
    )
    for e in rows:
        local = to_local(e.occurred_at)
        writer.writerow([
            local.strftime("%Y-%m-%d"),
            local.strftime("%H:%M"),
            e.description,
            in_label if e.direction == DIR_IN else out_label,
            f"{e.amount:.2f}",
            e.category.name if e.category else "",
            e.created_by.display_name,
            e.note or "",
            e.source,
        ])

    stamp = month or datetime.now().strftime("%Y%m%d")
    full_name = f"{ctx.ledger.name}-{stamp}.csv"
    # HTTP headers are latin-1, and ledger names are usually Thai, so the
    # filename needs RFC 5987: an ASCII fallback plus a UTF-8 encoded form.
    # Without this, exporting from any Thai-named ledger 500s.
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", full_name).strip("_") or "export.csv"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(full_name, safe='')}"
    )

    # utf-8-sig so Excel on Windows opens Thai text without mojibake
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------
@router.get("", response_model=EntryPage)
def list_entries(
    ctx: LedgerRead,
    db: DbSession,
    month: str | None = Query(None, description="YYYY-MM (เวลาไทย)"),
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    created_by_id: int | None = None,
    direction: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EntryPage:
    ledger_id = ctx.ledger.id
    filters = dict(
        month=month,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        created_by_id=created_by_id,
        direction=direction,
        q=q,
    )

    total = db.execute(
        _apply_filters(select(func.count(Entry.id)), ledger_id=ledger_id, **filters)
    ).scalar_one()

    items = (
        db.execute(
            _apply_filters(
                select(Entry).options(
                    joinedload(Entry.category), joinedload(Entry.created_by)
                ),
                ledger_id=ledger_id,
                **filters,
            )
            .order_by(Entry.occurred_at.desc(), Entry.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return EntryPage(
        items=[EntryOut.model_validate(e) for e in items],
        total=total,
        totals=_totals(db, ledger_id, **filters),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(payload: EntryCreate, ctx: LedgerWrite, db: DbSession) -> EntryOut:
    ledger_id = ctx.ledger.id
    _check_category(db, ledger_id, payload.category_id)

    # Cheap pre-check for the common case; UNIQUE(ledger_id, slip_ref) is what
    # makes it safe when both phones submit at the same instant.
    if payload.slip_ref:
        existing = db.execute(
            select(Entry).where(
                Entry.ledger_id == ledger_id, Entry.slip_ref == payload.slip_ref
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "สลิปใบนี้ถูกลงในสมุดนี้แล้ว",
                    "duplicate_of_id": existing.id,
                },
            )

    entry = Entry(
        ledger_id=ledger_id,
        occurred_at=payload.occurred_at,
        description=payload.description,
        amount=payload.amount,
        direction=payload.direction,
        category_id=payload.category_id,
        note=payload.note,
        slip_path=payload.slip_path,
        slip_ref=payload.slip_ref,
        source=payload.source,
        ocr_raw_text=payload.ocr_raw_text,
        ocr_confidence=payload.ocr_confidence,
        created_by_id=ctx.user.id,
        version=1,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "สลิปใบนี้ถูกลงในสมุดนี้แล้ว", "duplicate_of_id": None},
        ) from None

    return EntryOut.model_validate(_load(db, ledger_id, entry.id))


# --------------------------------------------------------------------------
# item
# --------------------------------------------------------------------------
@router.get("/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: int, ctx: LedgerRead, db: DbSession) -> EntryOut:
    return EntryOut.model_validate(_load(db, ctx.ledger.id, entry_id))


@router.put("/{entry_id}", response_model=EntryOut)
def update_entry(
    entry_id: int, payload: EntryUpdate, ctx: LedgerWrite, db: DbSession
) -> EntryOut:
    """Optimistic locking: a conditional UPDATE rather than read-then-write, so
    two simultaneous saves cannot both pass the version check."""
    ledger_id = ctx.ledger.id
    _check_category(db, ledger_id, payload.category_id)

    result = db.execute(
        update(Entry)
        .where(
            Entry.id == entry_id,
            Entry.ledger_id == ledger_id,
            Entry.version == payload.version,
        )
        .values(
            occurred_at=payload.occurred_at,
            description=payload.description,
            amount=payload.amount,
            direction=payload.direction,
            category_id=payload.category_id,
            note=payload.note,
            slip_path=payload.slip_path,
            version=Entry.version + 1,
            updated_at=func.now(),
        )
    )

    if result.rowcount == 0:
        db.rollback()
        current = db.execute(
            select(Entry).where(Entry.id == entry_id, Entry.ledger_id == ledger_id)
        ).scalar_one_or_none()
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "มีคนเพิ่งแก้รายการนี้ กรุณาโหลดใหม่แล้วลองอีกครั้ง",
                "current_version": current.version,
            },
        )

    db.commit()
    return EntryOut.model_validate(_load(db, ledger_id, entry_id))


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int, ctx: LedgerWrite, db: DbSession, background_tasks: BackgroundTasks
) -> Response:
    entry = _load(db, ctx.ledger.id, entry_id)
    slip_path = entry.slip_path

    db.delete(entry)
    db.commit()

    # Orphaning a slip object is harmless; failing the delete because storage
    # is unreachable is not.
    if slip_path:
        background_tasks.add_task(delete_slip, slip_path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{entry_id}/slip", response_model=SignedUrlResponse)
async def get_slip_url(
    entry_id: int, ctx: LedgerRead, db: DbSession
) -> SignedUrlResponse:
    """Short-lived signed URL, minted per request. Membership is already proven
    by the dependency, so this is the only door to someone's slip images."""
    entry = _load(db, ctx.ledger.id, entry_id)
    if not entry.slip_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="รายการนี้ไม่มีสลิป"
        )
    signed = await create_signed_url(entry.slip_path)
    return SignedUrlResponse(
        signed_url=signed, expires_in=settings.signed_url_ttl_seconds
    )
