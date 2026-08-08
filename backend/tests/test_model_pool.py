"""Tests for the two-model pool.

Two Gemma variants share one key, each with its own 30-requests and
16,000-tokens per minute. Pooling them doubles throughput, but only if the
counters stay separate and a model that runs out steps aside instead of
collecting 429s. These tests pin that.

Run: python -m tests.test_model_pool     (from backend/)
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("GOOGLE_VISION_API_KEY", "")
os.environ.setdefault("TAGGER_PROVIDER", "none")
os.environ.setdefault("GEMINI_API_KEY", "")

from app.model_pool import ModelPool  # noqa: E402

passed = failed = 0

A, B = "gemma-4-26b-a4b-it", "gemma-4-31b-it"


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


def pool(**kw) -> ModelPool:
    return ModelPool([A, B], **kw)


print("\n== the first model is used until it runs out ==")
p = pool(requests_per_minute=3, tokens_per_minute=1_000_000)
picks = [p.acquire(1) for _ in range(3)]
check("all three go to the first model", picks == [A, A, A], picks)
check("the fourth moves to the second", p.acquire(1) == B, "")
check("...and the first is now cooling",
      p.snapshot()[0]["cooling_for"] > 0, p.snapshot()[0])

print("\n== failover, then waiting ==")
p = pool(requests_per_minute=2, tokens_per_minute=1_000_000, cooldown_seconds=90)
got = [p.acquire(1) for _ in range(6)]
check("two on each before both are spent", got[:2] == [A, A] and got[2:4] == [B, B], got)
check("once both are cooling, acquire returns nothing",
      got[4] is None and got[5] is None, got)
wait = p.wait_seconds()
check("and it says how long to wait", 80 < wait <= 90, wait)

print("\n== the two models are metered separately ==")
p = pool(requests_per_minute=2, tokens_per_minute=1_000_000)
p.acquire(1)
p.acquire(1)  # A is now full
p.acquire(1)  # -> B
snap = {s["model"]: s for s in p.snapshot()}
check("A counted two requests", snap[A]["requests_this_minute"] == 2, snap[A])
check("B counted one", snap[B]["requests_this_minute"] == 1, snap[B])
check("B is not cooling because A ran out", snap[B]["cooling_for"] == 0, snap[B])

print("\n== the token ceiling, not just the request count ==")
p = pool(requests_per_minute=1000, tokens_per_minute=1000)
check("a call that fits is allowed", p.acquire(400) == A)
check("a second that fits is allowed", p.acquire(400) == A)
# 800 used, a third 400 would be 1200 — over 1000, so A steps aside.
check("the one that would overrun moves to the other model",
      p.acquire(400) == B, "")
check("A is cooling on tokens alone",
      p.snapshot()[0]["cooling_for"] > 0, p.snapshot()[0])

print("\n== the estimate is corrected by what the call actually cost ==")
p = pool(requests_per_minute=1000, tokens_per_minute=10_000)
p.acquire(500)
snap = p.snapshot()[0]
check("the estimate is reserved up front",
      snap["tokens_this_minute"] == 500, snap)
p.record(A, 320)
snap = p.snapshot()[0]
check("and replaced by the real figure", snap["tokens_this_minute"] == 320, snap)

# Reserving low and spending high must still trip the ceiling.
p = pool(requests_per_minute=1000, tokens_per_minute=1000)
p.acquire(100)
p.record(A, 1500)
check("a call that overran the ceiling puts the model to sleep",
      p.snapshot()[0]["cooling_for"] > 0, p.snapshot()[0])

print("\n== trip: the provider refused us anyway ==")
p = pool()
check("a fresh pool hands out the first model", p.acquire() == A)
p.trip(A)
check("after a 429 the next call goes elsewhere", p.acquire() == B, "")
check("nothing to wait for while one is free", p.wait_seconds() == 0)

print("\n== a cooldown that has expired is usable again ==")
p = pool(requests_per_minute=1, tokens_per_minute=1_000_000, cooldown_seconds=0.25)
p.acquire(1)
p.acquire(1)  # trips A, uses B
p.acquire(1)  # trips B
check("both spent", p.acquire(1) is None)
time.sleep(0.35)
check("after the cooldown the pool works again", p.acquire(1) in (A, B))

print("\n== a single-model pool still behaves ==")
p = ModelPool([A], requests_per_minute=1, cooldown_seconds=5)
check("first call fine", p.acquire(1) == A)
check("second is refused", p.acquire(1) is None)
check("and reports a wait", p.wait_seconds() > 0)

print("\n== clear() must not detach the object ==")
# main.py exposes this through /health, so replacing it would leave the
# endpoint reporting a counter that never moves — the same bug the tagger
# budget had.
p = pool(requests_per_minute=5)
held = p
p.acquire(1)
p.clear()
check("the same object is cleared in place", held is p)
check("and reads as empty", p.snapshot()[0]["requests_this_minute"] == 0, p.snapshot())

print(f"\n{'=' * 52}\n  {passed} passed, {failed} failed\n{'=' * 52}")
sys.exit(1 if failed else 0)
