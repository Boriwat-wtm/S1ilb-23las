import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .keywords import sanitise_keyword, stem, would_shadow
from .models import KW_LEARNED, Category, CategoryKeyword

log = logging.getLogger("bank.categorize")


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


def existing_keywords(db: Session, ledger_id: int) -> dict[str, int]:
    """Every keyword in this ledger mapped to the category it points at."""
    rows = db.execute(
        select(CategoryKeyword.keyword, CategoryKeyword.category_id).where(
            CategoryKeyword.ledger_id == ledger_id
        )
    ).all()
    return {keyword: category_id for keyword, category_id in rows}


def remember_keyword(
    db: Session,
    ledger_id: int,
    category_id: int,
    raw: str,
    source: str,
    priority: int = 1,
) -> CategoryKeyword | None:
    """Store a keyword if it is safe to. Returns None when it was refused.

    Refusal is the normal, expected outcome for most inputs and is never an
    error — see app/keywords.py for what gets rejected and why. The caller
    does not commit; this only stages the row.
    """
    existing = existing_keywords(db, ledger_id)
    word = sanitise_keyword(stem(raw), existing)
    if word is None:
        return None
    if would_shadow(word, existing, category_id):
        return None

    row = CategoryKeyword(
        ledger_id=ledger_id,
        keyword=word,
        category_id=category_id,
        priority=priority,
        source=source,
    )
    db.add(row)
    return row


def learn_from_entry(
    db: Session, ledger_id: int, description: str, category_id: int | None
) -> None:
    """Record what the user just taught us by filing this entry.

    Only fires when the guess was *wrong or missing*. If the keyword table
    already resolves this description to the chosen category there is nothing
    to learn, and writing anyway would fill the table with duplicates of what
    it already knows.

    Never raises: mis-filing an entry because the learner tripped would be a
    far worse outcome than not learning from it.
    """
    if not category_id or not description:
        return
    try:
        guessed, _ = suggest_category(db, ledger_id, description)
        if guessed is not None and guessed.id == category_id:
            return
        remember_keyword(db, ledger_id, category_id, description, KW_LEARNED)
    except Exception:  # noqa: BLE001
        log.warning("learn_from_entry failed for ledger %s", ledger_id, exc_info=True)
