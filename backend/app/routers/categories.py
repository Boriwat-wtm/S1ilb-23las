from fastapi import APIRouter, Query
from sqlalchemy import select

from ..categorize import suggest_category
from ..deps import CurrentUser, DbSession
from ..models import Category
from ..schemas import CategoryOut, CategorySuggestion

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: DbSession, current_user: CurrentUser) -> list[CategoryOut]:
    rows = (
        db.execute(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )
    return [CategoryOut.model_validate(c) for c in rows]


@router.get("/suggest", response_model=CategorySuggestion)
def suggest(
    db: DbSession,
    current_user: CurrentUser,
    text: str = Query("", description="ข้อความรายการที่จะเดาหมวดหมู่จาก"),
) -> CategorySuggestion:
    category, keyword = suggest_category(db, text)
    return CategorySuggestion(
        category=CategoryOut.model_validate(category) if category else None,
        matched_keyword=keyword,
    )
