from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..categorize import (
    combined_text,
    existing_keywords,
    remember_keyword,
    suggest_category,
)
from ..deps import DbSession, LedgerRead, LedgerWrite
from ..keywords import sanitise_keyword, would_shadow
from ..models import KW_AI, KW_MANUAL, Category, CategoryKeyword, Entry
from ..schemas import (
    CategoryCreate,
    CategoryDetail,
    CategoryOut,
    CategorySuggestion,
    CategoryUpdate,
    KeywordCreate,
    KeywordOut,
)
from ..tagger import suggest_tag

router = APIRouter(prefix="/ledgers/{ledger_id}/categories", tags=["categories"])


def _get(db, ledger_id: int, category_id: int) -> Category:
    category = db.execute(
        select(Category).where(
            Category.id == category_id, Category.ledger_id == ledger_id
        )
    ).scalar_one_or_none()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบหมวดหมู่นี้"
        )
    return category


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


@router.get("/detail", response_model=list[CategoryDetail])
def list_categories_detail(ctx: LedgerRead, db: DbSession) -> list[CategoryDetail]:
    """Categories with their keywords and usage counts.

    This is what makes automatic keyword writing safe to ship: the learner and
    the tagger both add rows here without asking, so there has to be one place
    that shows everything they added and lets it be deleted. Without it, a bad
    keyword is undiagnosable — matching is substring-based, so the symptom is
    "some entries go to the wrong category" with nothing pointing at why.
    """
    categories = (
        db.execute(
            select(Category)
            .options(selectinload(Category.keywords))
            .where(Category.ledger_id == ctx.ledger.id, Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )

    counts = dict(
        db.execute(
            select(Entry.category_id, func.count(Entry.id))
            .where(Entry.ledger_id == ctx.ledger.id)
            .group_by(Entry.category_id)
        ).all()
    )

    return [
        CategoryDetail(
            id=c.id,
            name=c.name,
            emoji=c.emoji,
            sort_order=c.sort_order,
            entry_count=counts.get(c.id, 0),
            keywords=sorted(
                (KeywordOut.model_validate(k) for k in c.keywords),
                key=lambda k: (k.source != "seed", k.keyword),
            ),
        )
        for c in categories
    ]


@router.get("/suggest", response_model=CategorySuggestion)
async def suggest(
    ctx: LedgerRead,
    db: DbSession,
    text: str = Query("", description="ชื่อรายการ"),
    note: str = Query("", description="หมายเหตุ — ใช้เป็นสัญญาณที่สองในการเดา"),
    deep: bool = Query(
        False,
        description="ให้ถาม tagger ได้ถ้า keyword ไม่ตรง — ใช้ตอนพิมพ์เสร็จเท่านั้น",
    ),
) -> CategorySuggestion:
    """Keyword table first; the tagger only on a miss, and only when asked.

    `deep` exists because the entry form calls this on a 400ms debounce while
    you type. Left to fire freely, one shop name typed with a couple of pauses
    would send three or four requests to the model — a free tier spent on
    guessing at half-finished words. So the keyword path runs on every
    keystroke, for nothing, and the client sets deep=1 once, when the field is
    finished.

    The tagger is a cache-miss handler either way: its answer is written
    straight back as a keyword, so the same shop is never asked about twice
    and the running cost decays toward nothing.

    Both the name and the note are searched. A slip names the payee, which is
    frequently the least informative string involved — "บริษัท ซีพี ออลล์
    จำกัด (มหาชน)" is a holding company, not lunch — while the note is where
    "ผัดกะเพรา" gets written.
    """
    haystack = combined_text(text, note)
    category, keyword = suggest_category(db, ctx.ledger.id, haystack)
    if category is not None:
        return CategorySuggestion(
            category=CategoryOut.model_validate(category),
            matched_keyword=keyword,
            source="keyword",
        )

    if not deep or not haystack.strip() or not ctx.can_edit:
        return CategorySuggestion()

    names = [
        c.name
        for c in db.execute(
            select(Category)
            .where(Category.ledger_id == ctx.ledger.id, Category.is_active.is_(True))
            .order_by(Category.sort_order)
        ).scalars()
    ]
    tag = await suggest_tag(text or note, names, note=note if text else "")
    if not tag.ok:
        return CategorySuggestion()

    matched = db.execute(
        select(Category).where(
            Category.ledger_id == ctx.ledger.id, Category.name == tag.category_name
        )
    ).scalar_one_or_none()
    if matched is None:
        return CategorySuggestion()

    # Persist so this costs one call per shop, not one per entry. Refusal is
    # normal and never blocks the suggestion — see app/keywords.py.
    saved = remember_keyword(
        db, ctx.ledger.id, matched.id, tag.keyword or haystack, KW_AI, priority=1
    )
    if saved is not None:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    return CategorySuggestion(
        category=CategoryOut.model_validate(matched),
        matched_keyword=saved.keyword if saved else None,
        source="ai",
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
        remember_keyword(db, ctx.ledger.id, category.id, kw, KW_MANUAL, priority=2)

    db.commit()
    db.refresh(category)
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, payload: CategoryUpdate, ctx: LedgerWrite, db: DbSession
) -> CategoryOut:
    category = _get(db, ctx.ledger.id, category_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="มีหมวดหมู่ชื่อนี้ในสมุดนี้แล้ว",
        ) from None
    db.refresh(category)
    return CategoryOut.model_validate(category)


@router.post(
    "/{category_id}/keywords",
    response_model=KeywordOut,
    status_code=status.HTTP_201_CREATED,
)
def add_keyword(
    category_id: int, payload: KeywordCreate, ctx: LedgerWrite, db: DbSession
) -> KeywordOut:
    """A keyword typed by hand still goes through the same sanitiser.

    The rules exist because of how substring matching fails, not because of
    who is typing — "ร้าน" ruins the table whether a model or a person adds it.
    Refusals are explained rather than silent, since here there *is* someone
    to explain them to.
    """
    category = _get(db, ctx.ledger.id, category_id)
    existing = existing_keywords(db, ctx.ledger.id)

    word = sanitise_keyword(payload.keyword, existing)
    if word is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="คำนี้ใช้ไม่ได้ — สั้นเกินไป กว้างเกินไป เป็นตัวเลขล้วน หรือมีอยู่แล้ว",
        )
    if would_shadow(word, existing, category.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="คำนี้ทับกับคำที่ชี้ไปหมวดอื่นอยู่ จะทำให้รายการเก่าเปลี่ยนหมวดโดยไม่ตั้งใจ",
        )

    row = CategoryKeyword(
        ledger_id=ctx.ledger.id,
        keyword=word,
        category_id=category.id,
        priority=2,
        source=KW_MANUAL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return KeywordOut.model_validate(row)


@router.delete(
    "/{category_id}/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_keyword(
    category_id: int, keyword_id: int, ctx: LedgerWrite, db: DbSession
) -> Response:
    row = db.execute(
        select(CategoryKeyword).where(
            CategoryKeyword.id == keyword_id,
            CategoryKeyword.ledger_id == ctx.ledger.id,
            CategoryKeyword.category_id == category_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบคำนี้"
        )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, ctx: LedgerWrite, db: DbSession) -> Response:
    """Hidden rather than deleted when entries still point at it, so historical
    rows keep their label instead of silently becoming uncategorised."""
    category = _get(db, ctx.ledger.id, category_id)

    in_use = db.execute(
        select(Entry.id).where(Entry.category_id == category_id).limit(1)
    ).scalar_one_or_none()

    if in_use:
        category.is_active = False
    else:
        db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
