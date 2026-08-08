"""Tests for the two things that keep the tagger from eating a free tier.

The entry form calls /categories/suggest on a 400ms debounce while you type.
Before `deep`, every one of those that missed the keyword table was a request
to the model — a single shop name typed with a couple of pauses cost three or
four calls. These tests pin the three defences: the tagger only runs when
asked, the same text is never asked twice, and a self-imposed ceiling stops
before the provider's does.

Run: python -m tests.test_tagger_budget     (from backend/)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never reach a live provider from a test: Settings reads backend/.env,
# so a real key sitting there would otherwise be spent by a test run.
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("GOOGLE_VISION_API_KEY", "")
os.environ.setdefault("TAGGER_PROVIDER", "none")
os.environ.setdefault("GEMINI_API_KEY", "")

from app import tagger as tagger_module  # noqa: E402
from app.config import settings  # noqa: E402
from app.tagger import TagSuggestion, reset_state, suggest_tag  # noqa: E402

passed = failed = 0


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


CATEGORIES = ["อาหาร/เครื่องดื่ม", "เดินทาง", "อื่นๆ"]


class CountingTagger:
    """Stands in for Gemini and counts how often it is actually reached."""

    name = "counting"

    def __init__(self, answer: str | None = "อาหาร/เครื่องดื่ม") -> None:
        self.calls = 0
        self.answer = answer

    async def tag(self, description: str, categories: list[str]) -> TagSuggestion:
        self.calls += 1
        return TagSuggestion(
            category_name=self.answer, keyword="stub", provider=self.name
        )


def install(stub) -> None:
    tagger_module.get_tagger = lambda: stub  # type: ignore[assignment]


original_get_tagger = tagger_module.get_tagger
original_minute = settings.tagger_max_per_minute
original_day = settings.tagger_max_per_day


async def main() -> None:
    print("\n== the cache ==")
    reset_state()
    stub = CountingTagger()
    install(stub)

    await suggest_tag("After You สาขาสยาม", CATEGORIES)
    await suggest_tag("After You สาขาสยาม", CATEGORIES)
    await suggest_tag("After You สาขาสยาม", CATEGORIES)
    check("the same text is asked once, not three times", stub.calls == 1, stub.calls)

    await suggest_tag("  after you   SAKHA สยาม  ", CATEGORIES)
    check("whitespace and case do not defeat the cache",
          stub.calls == 2, stub.calls)  # different words, so a genuine second shop

    reset_state()
    stub = CountingTagger()
    install(stub)
    await suggest_tag("After You", CATEGORIES)
    await suggest_tag("  AFTER   YOU  ", CATEGORIES)
    check("case and spacing normalise to one call", stub.calls == 1, stub.calls)

    await suggest_tag("After You", ["อื่นๆ"])
    check("a different category list is a different question",
          stub.calls == 2, stub.calls)

    print("\n== negative results are cached too ==")
    reset_state()
    stub = CountingTagger(answer=None)
    install(stub)
    await suggest_tag("ห้างสรรพสินค้าที่ไม่มีใครรู้จัก", CATEGORIES)
    await suggest_tag("ห้างสรรพสินค้าที่ไม่มีใครรู้จัก", CATEGORIES)
    # Retyping the same unplaceable name is exactly what a user does; asking
    # again cannot produce a different answer.
    check("a miss is not re-asked", stub.calls == 1, stub.calls)

    print("\n== the budget ==")
    reset_state()
    settings.tagger_max_per_minute = 3
    settings.tagger_max_per_day = 100
    stub = CountingTagger()
    install(stub)

    results = [await suggest_tag(f"ร้านที่ {i}", CATEGORIES) for i in range(6)]
    check("stops at the per-minute ceiling", stub.calls == 3, stub.calls)
    check("the first three answered", all(r.ok for r in results[:3]))
    check("the rest come back empty, not as errors",
          all(not r.ok and r.error is None for r in results[3:]),
          [(r.ok, r.error) for r in results[3:]])

    reset_state()
    settings.tagger_max_per_minute = 100
    settings.tagger_max_per_day = 2
    stub = CountingTagger()
    install(stub)
    for i in range(5):
        await suggest_tag(f"ร้านวันนี้ {i}", CATEGORIES)
    check("stops at the per-day ceiling", stub.calls == 2, stub.calls)

    print("\n== the budget is not spent on cache hits ==")
    reset_state()
    settings.tagger_max_per_minute = 2
    settings.tagger_max_per_day = 100
    stub = CountingTagger()
    install(stub)
    for _ in range(10):
        await suggest_tag("ร้านเดิม", CATEGORIES)
    snap = tagger_module.budget.snapshot()
    check("ten identical asks cost one call", stub.calls == 1, stub.calls)
    check("...and one unit of budget", snap["used_this_minute"] == 1, snap)

    print("\n== transport failures are not cached ==")
    reset_state()
    settings.tagger_max_per_minute = 100

    class Flaky:
        name = "flaky"

        def __init__(self) -> None:
            self.calls = 0

        async def tag(self, description, categories):
            self.calls += 1
            if self.calls == 1:
                return TagSuggestion(provider=self.name, error="Gemini ตอบ 503")
            return TagSuggestion(
                category_name="เดินทาง", keyword="x", provider=self.name
            )

    flaky = Flaky()
    install(flaky)
    first = await suggest_tag("ร้านใหม่", CATEGORIES)
    second = await suggest_tag("ร้านใหม่", CATEGORIES)
    check("a failed call is retried rather than remembered", flaky.calls == 2, flaky.calls)
    check("and the retry's answer is used", second.ok and not first.ok)

    print("\n== reset_state must not detach the budget ==")
    # main.py binds this object once, at import, for /health. Replacing it in
    # reset_state left the health endpoint reporting a counter that never
    # moved again — invisible unless something looks for it.
    reset_state()
    settings.tagger_max_per_minute = 100
    settings.tagger_max_per_day = 100
    held = tagger_module.budget  # what /health holds
    stub = CountingTagger()
    install(stub)
    await suggest_tag("ร้านหลังรีเซ็ต", CATEGORIES)
    check("the object /health holds is the one that counts",
          held is tagger_module.budget, "reset_state rebound the global")
    check("...and it sees the call", held.snapshot()["used_today"] == 1,
          held.snapshot())

    print("\n== the null tagger costs nothing at all ==")
    reset_state()
    tagger_module.get_tagger = original_get_tagger
    settings.tagger_provider = "none"
    before = tagger_module.budget.snapshot()["used_this_minute"]
    r = await suggest_tag("อะไรก็ได้", CATEGORIES)
    after = tagger_module.budget.snapshot()["used_this_minute"]
    check("no suggestion", not r.ok)
    check("and no budget spent", before == after == 0, (before, after))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        tagger_module.get_tagger = original_get_tagger
        settings.tagger_max_per_minute = original_minute
        settings.tagger_max_per_day = original_day
        reset_state()
    print(f"\n{'=' * 52}\n  {passed} passed, {failed} failed\n{'=' * 52}")
    sys.exit(1 if failed else 0)
