from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Category, CategoryKeyword


def suggest_category(
    db: Session, ledger_id: int, text: str
) -> tuple[Category | None, str | None]:
    """Guess a category from free text using this ledger's keyword table.

    Scoped to the ledger — a suggestion must never surface a category name from
    a book the caller cannot see.

    The keyword set is small (tens of rows per ledger), so matching in Python is
    cheaper and far more predictable than building a SQL LIKE query, and it
    sidesteps collation quirks with Thai text entirely.

    Best match wins by: highest priority, then longest keyword. Longest-wins
    matters because "กาแฟ" and "เซเว่น" can both hit the same description.
    """
    haystack = (text or "").lower().strip()
    if not haystack:
        return None, None

    rows = (
        db.execute(
            select(CategoryKeyword)
            .options(joinedload(CategoryKeyword.category))
            .where(CategoryKeyword.ledger_id == ledger_id)
        )
        .scalars()
        .all()
    )

    matches = [kw for kw in rows if kw.keyword in haystack]
    if not matches:
        return None, None

    best = max(matches, key=lambda kw: (kw.priority, len(kw.keyword)))
    return best.category, best.keyword
