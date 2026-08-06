from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Category, CategoryKeyword


def suggest_category(
    db: Session, text: str
) -> tuple[Category | None, str | None]:
    """Guess a category from free text using the category_keywords table.

    The keyword table is small (tens of rows), so it is cheaper and far more
    predictable to match in Python than to build a SQL LIKE query — and it
    sidesteps collation quirks with Thai text entirely.

    Best match wins by: highest priority, then longest keyword. Longest-wins
    matters because "กาแฟ" and "ร้านกาแฟอเมซอน" can both match one description.
    """
    haystack = (text or "").lower().strip()
    if not haystack:
        return None, None

    rows = db.execute(
        select(CategoryKeyword).options(joinedload(CategoryKeyword.category))
    ).scalars().all()

    matches = [kw for kw in rows if kw.keyword in haystack]
    if not matches:
        return None, None

    best = max(matches, key=lambda kw: (kw.priority, len(kw.keyword)))
    return best.category, best.keyword
