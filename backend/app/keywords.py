"""Turning a description into a keyword worth remembering, safely.

Three different things write into `category_keywords`: the starter template,
the user overriding a guess, and eventually an LLM. The last two write
*automatically*, which is the whole risk — one bad word here silently
misfiles every future entry, and because matching is substring-based the
damage is invisible until someone reads a month's summary and finds the
numbers wrong.

So everything auto-generated goes through `sanitise_keyword` first, and the
rules it enforces exist for specific failure modes:

  * Too short, and it matches inside unrelated words.
  * Too generic ("ร้าน", "ค่า", "บริษัท") and it matches everything. This is
    the one that ruins a ledger, because the keyword that swallows the whole
    table is also the longest match, so it wins every tie.
  * Pure digits are an amount or an account number, never a merchant.
  * Already present pointing somewhere else — one word cannot mean two
    categories, and silently repointing it would rewrite the past.
"""

import re

# Words that describe the *shape* of a transaction rather than who it was
# with. Any of these alone would match a large fraction of every ledger.
GENERIC = {
    "ร้าน", "ค่า", "ซื้อ", "จ่าย", "โอน", "เงิน", "บาท", "บริษัท", "จำกัด",
    "มหาชน", "สาขา", "ที่", "การ", "ของ", "และ", "ใน", "จาก", "ไป", "มา",
    "shop", "store", "co", "ltd", "inc", "the", "and", "for", "pay", "payment",
    "transfer", "total", "baht", "thb",
}

# Stripped from the front and back before the stem is taken. These are noise
# in a merchant name, not part of it.
_LEADING = re.compile(
    r"^(?:ค่า|ซื้อ|จ่าย|โอนให้|โอนไป|โอน|ชำระ|เติม|บริษัท|ร้าน|หจก\.?|บจก\.?)\s*"
)
_TRAILING = re.compile(
    r"(?:\s*(?:จำกัด|\(มหาชน\)|มหาชน|จก\.?)\s*)+$"
)
# "สาขาเซ็นทรัลลาดพร้าว", "Branch 12", "#004" — the shop, not the chain.
_BRANCH = re.compile(
    r"\s*(?:สาขา\S*|branch\s*\S*|#\s*\d+|เลขที่\s*\S+).*$", re.IGNORECASE
)

MIN_LEN = 3
MAX_LEN = 40


def normalise(text: str) -> str:
    """Lowercase and collapse whitespace — the form keywords are matched in."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def stem(description: str) -> str:
    """A merchant name reduced to the part likely to repeat.

    "ค่ากาแฟ After You สาขาสยาม" -> "กาแฟ after you"

    Deliberately conservative and deliberately unclever: without a language
    model there is no reliable way to find the brand inside a Thai string, so
    this only strips prefixes and suffixes that are noise by definition and
    leaves the rest alone. The categories screen exists so a bad stem can be
    shortened by hand, and the tagger — when it is switched on — returns a far
    better keyword than this can.
    """
    text = normalise(description)
    text = _BRANCH.sub("", text)
    text = _TRAILING.sub("", text)
    text = _LEADING.sub("", text)
    text = normalise(text)
    if len(text) > MAX_LEN:
        # Cut on a word boundary where there is one; Thai often has none.
        cut = text[:MAX_LEN]
        if " " in cut:
            cut = cut[: cut.rindex(" ")]
        text = cut.strip()
    return text


def sanitise_keyword(raw: str, existing: dict[str, int] | None = None) -> str | None:
    """Return a keyword safe to store, or None to refuse.

    `existing` maps already-stored keywords to their category id, so a word
    that is already spoken for can be rejected rather than quietly moved.
    """
    word = normalise(raw)
    if len(word) < MIN_LEN or len(word) > MAX_LEN:
        return None
    if word in GENERIC:
        return None
    # Digits only, or digits and punctuation: an amount, a date, an account.
    if not re.search(r"[^\W\d_]", word, re.UNICODE):
        return None
    # Every token generic means the whole phrase is ("ค่า ร้าน").
    tokens = [t for t in word.split(" ") if t]
    if tokens and all(t in GENERIC for t in tokens):
        return None
    if existing is not None and word in existing:
        return None
    return word


def would_shadow(word: str, existing: dict[str, int], category_id: int) -> bool:
    """True if storing `word` would hijack matches that belong elsewhere.

    Matching is substring-based and longest-wins, so a *shorter* new word
    cannot steal from a longer existing one — but a longer new word sits on
    top of every shorter word it contains. Adding "กาแฟสด" over an existing
    "กาแฟ" pointing at a different category is a silent reclassification of
    everything containing "กาแฟสด", so it is refused rather than guessed at.
    """
    for other, other_category in existing.items():
        if other_category == category_id:
            continue
        if other in word or word in other:
            return True
    return False
