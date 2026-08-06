import csv
import io
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..deps import CurrentUser, DbSession
from ..models import Category, Transaction, User
from ..schemas import (
    CategoryOut,
    CategoryTotal,
    MonthlySummary,
    SignedUrlResponse,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
    UserOut,
    UserTotal,
)
from ..storage import create_signed_url, delete_slip
from ..timeutil import (
    current_month,
    day_end_utc,
    day_start_utc,
    month_bounds_utc,
    to_local,
)
from ..config import settings

router = APIRouter(prefix="/transactions", tags=["transactions"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _apply_filters(
    stmt: Select,
    *,
    month: str | None,
    date_from: date | None,
    date_to: date | None,
    category_id: int | None,
    added_by_id: int | None,
    q: str | None,
) -> Select:
    if month:
        try:
            start, end = month_bounds_utc(month)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        stmt = stmt.where(Transaction.occurred_at >= start, Transaction.occurred_at < end)
    if date_from:
        stmt = stmt.where(Transaction.occurred_at >= day_start_utc(date_from))
    if date_to:
        stmt = stmt.where(Transaction.occurred_at < day_end_utc(date_to))
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if added_by_id is not None:
        stmt = stmt.where(Transaction.added_by_id == added_by_id)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Transaction.description.ilike(needle), Transaction.note.ilike(needle))
        )
    return stmt


def _load(db, transaction_id: int) -> Transaction:
    tx = db.execute(
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.added_by))
        .where(Transaction.id == transaction_id)
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
        )
    return tx


# --------------------------------------------------------------------------
# static paths first — otherwise "/summary" gets parsed as a transaction id
# --------------------------------------------------------------------------
@router.get("/summary", response_model=MonthlySummary)
def summary(
    db: DbSession,
    current_user: CurrentUser,
    month: str = Query(default_factory=current_month, description="YYYY-MM"),
) -> MonthlySummary:
    try:
        start, end = month_bounds_utc(month)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    window = (Transaction.occurred_at >= start, Transaction.occurred_at < end)

    total, count = db.execute(
        select(
            func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id)
        ).where(*window)
    ).one()

    by_category_rows = db.execute(
        select(
            Category,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
        )
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(*window)
        .group_by(Category.id)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    by_user_rows = db.execute(
        select(
            User,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
        )
        .select_from(Transaction)
        .join(User, Transaction.added_by_id == User.id)
        .where(*window)
        .group_by(User.id)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    return MonthlySummary(
        month=month,
        total=Decimal(total),
        count=count,
        by_category=[
            CategoryTotal(
                category=CategoryOut.model_validate(cat) if cat else None,
                total=Decimal(amt),
                count=cnt,
            )
            for cat, amt, cnt in by_category_rows
        ],
        by_user=[
            UserTotal(user=UserOut.model_validate(u), total=Decimal(amt), count=cnt)
            for u, amt, cnt in by_user_rows
        ],
    )


@router.get("/export.csv")
def export_csv(
    db: DbSession,
    current_user: CurrentUser,
    month: str | None = Query(None, description="YYYY-MM, ว่าง = ทั้งหมด"),
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    added_by_id: int | None = None,
    q: str | None = None,
) -> Response:
    """Periodic backup hatch — the data should never be trapped in Neon."""
    stmt = (
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.added_by))
        .order_by(Transaction.occurred_at.asc())
    )
    stmt = _apply_filters(
        stmt,
        month=month,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        added_by_id=added_by_id,
        q=q,
    )
    rows = db.execute(stmt).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["วันที่", "เวลา", "รายการ", "จำนวนเงิน", "หมวดหมู่", "คนลง", "หมายเหตุ", "ที่มา", "slip_ref"]
    )
    for tx in rows:
        local = to_local(tx.occurred_at)
        writer.writerow(
            [
                local.strftime("%Y-%m-%d"),
                local.strftime("%H:%M"),
                tx.description,
                f"{tx.amount:.2f}",
                tx.category.name if tx.category else "",
                tx.added_by.display_name,
                tx.note or "",
                tx.source,
                tx.slip_ref or "",
            ]
        )

    stamp = month or datetime.now().strftime("%Y%m%d")
    # utf-8-sig so Excel on Windows opens Thai text without mojibake
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bank-{stamp}.csv"'},
    )


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------
@router.get("", response_model=TransactionPage)
def list_transactions(
    db: DbSession,
    current_user: CurrentUser,
    month: str | None = Query(None, description="YYYY-MM (เวลาไทย)"),
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    added_by_id: int | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TransactionPage:
    filter_kwargs = dict(
        month=month,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        added_by_id=added_by_id,
        q=q,
    )

    total, total_amount = db.execute(
        _apply_filters(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            ),
            **filter_kwargs,
        )
    ).one()

    stmt = _apply_filters(
        select(Transaction).options(
            joinedload(Transaction.category), joinedload(Transaction.added_by)
        ),
        **filter_kwargs,
    )
    items = (
        db.execute(
            stmt.order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return TransactionPage(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        total_amount=Decimal(total_amount),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate, db: DbSession, current_user: CurrentUser
) -> TransactionOut:
    if payload.category_id is not None and db.get(Category, payload.category_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ไม่พบหมวดหมู่ที่เลือก",
        )

    # Cheap pre-check for the common case; the UNIQUE index below is what
    # actually makes it safe when both phones submit at the same instant.
    if payload.slip_ref:
        existing = db.execute(
            select(Transaction).where(Transaction.slip_ref == payload.slip_ref)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "สลิปใบนี้ถูกลงไว้แล้ว",
                    "duplicate_of_id": existing.id,
                },
            )

    tx = Transaction(
        occurred_at=payload.occurred_at,
        description=payload.description,
        amount=payload.amount,
        category_id=payload.category_id,
        note=payload.note,
        slip_path=payload.slip_path,
        slip_ref=payload.slip_ref,
        source=payload.source,
        ocr_raw_text=payload.ocr_raw_text,
        ocr_confidence=payload.ocr_confidence,
        added_by_id=current_user.id,
        version=1,
    )
    db.add(tx)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "สลิปใบนี้ถูกลงไว้แล้ว", "duplicate_of_id": None},
        ) from None

    return TransactionOut.model_validate(_load(db, tx.id))


# --------------------------------------------------------------------------
# item
# --------------------------------------------------------------------------
@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int, db: DbSession, current_user: CurrentUser
) -> TransactionOut:
    return TransactionOut.model_validate(_load(db, transaction_id))


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TransactionOut:
    """Optimistic locking: the UPDATE only matches if the row is still at the
    version the client read. A conditional UPDATE rather than read-then-write,
    so two simultaneous saves cannot both pass the check."""
    if payload.category_id is not None and db.get(Category, payload.category_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ไม่พบหมวดหมู่ที่เลือก",
        )

    result = db.execute(
        update(Transaction)
        .where(
            Transaction.id == transaction_id, Transaction.version == payload.version
        )
        .values(
            occurred_at=payload.occurred_at,
            description=payload.description,
            amount=payload.amount,
            category_id=payload.category_id,
            note=payload.note,
            slip_path=payload.slip_path,
            version=Transaction.version + 1,
            updated_at=func.now(),
        )
    )

    if result.rowcount == 0:
        db.rollback()
        current = db.get(Transaction, transaction_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "อีกฝ่ายเพิ่งแก้รายการนี้ กรุณาโหลดใหม่แล้วลองอีกครั้ง",
                "current_version": current.version,
            },
        )

    db.commit()
    return TransactionOut.model_validate(_load(db, transaction_id))


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: int,
    db: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Response:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
        )

    slip_path = tx.slip_path
    db.delete(tx)
    db.commit()

    # Orphaning a slip object is harmless; failing the delete because storage
    # is unreachable is not. Fire and forget after the row is already gone.
    if slip_path:
        background_tasks.add_task(delete_slip, slip_path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{transaction_id}/slip", response_model=SignedUrlResponse)
async def get_slip_url(
    transaction_id: int, db: DbSession, current_user: CurrentUser
) -> SignedUrlResponse:
    """Mint a short-lived signed URL. Nothing durable is ever handed out."""
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบรายการนี้"
        )
    if not tx.slip_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="รายการนี้ไม่มีสลิป"
        )
    signed = await create_signed_url(tx.slip_path)
    return SignedUrlResponse(
        signed_url=signed, expires_in=settings.signed_url_ttl_seconds
    )
