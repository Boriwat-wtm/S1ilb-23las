from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..categorize import suggest_category
from ..deps import DbSession, LedgerRead, LedgerWrite
from ..models import Category, CategoryKeyword, Entry
from ..schemas import CategoryCreate, CategoryOut, CategorySuggestion

router = APIRouter(prefix="/ledgers/{ledger_id}/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(ctx: LedgerRead, db: DbSession) -> list[CategoryOut]:
    rows = (
        db.execute(
            select(Category)
            .where(Category.ledger_id == ctx.ledger.id, Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )
    return [CategoryOut.model_validate(c) for c in rows]


@router.get("/suggest", response_model=CategorySuggestion)
def suggest(
    ctx: LedgerRead,
    db: DbSession,
    text: str = Query("", description="ข้อความรายการที่จะเดาหมวดหมู่จาก"),
) -> CategorySuggestion:
    category, keyword = suggest_category(db, ctx.ledger.id, text)
    return CategorySuggestion(
        category=CategoryOut.model_validate(category) if category else None,
        matched_keyword=keyword,
    )


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, ctx: LedgerWrite, db: DbSession
) -> CategoryOut:
    category = Category(
        ledger_id=ctx.ledger.id,
        name=payload.name.strip(),
        emoji=payload.emoji,
        sort_order=payload.sort_order,
    )
    db.add(category)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="มีหมวดหมู่ชื่อนี้ในสมุดนี้แล้ว",
        ) from None

    for kw in payload.keywords:
        kw = kw.lower().strip()
        if not kw:
            continue
        exists = db.execute(
            select(CategoryKeyword).where(
                CategoryKeyword.ledger_id == ctx.ledger.id,
                CategoryKeyword.keyword == kw,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                CategoryKeyword(
                    ledger_id=ctx.ledger.id, keyword=kw, category_id=category.id
                )
            )

    db.commit()
    db.refresh(category)
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, ctx: LedgerWrite, db: DbSession) -> Response:
    """Hidden rather than deleted when entries still point at it, so historical
    rows keep their label instead of silently becoming uncategorised."""
    category = db.execute(
        select(Category).where(
            Category.id == category_id, Category.ledger_id == ctx.ledger.id
        )
    ).scalar_one_or_none()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบหมวดหมู่นี้"
        )

    in_use = db.execute(
        select(Entry.id).where(Entry.category_id == category_id).limit(1)
    ).scalar_one_or_none()

    if in_use:
        category.is_active = False
    else:
        db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
