"""A pool of interchangeable models with per-model quota and cooldown.

Both Gemma variants sit on the same key with the same allowance — 30 requests
and 16,000 tokens per minute each — so running two of them doubles the
throughput without touching a second vendor or a second account.

The rules, and why each exists:

  * Each model is metered separately. They are separate quota buckets on
    Google's side, so pooling the counters would either waste one or overrun
    the other.

  * Hitting either ceiling puts that model to sleep for 90 seconds rather
    than letting the next call collect a 429. Backing off before being told
    to is the difference between a queue that slows down and a queue that
    starts erroring.

  * A caller asks for whichever model is free. When both are cooling it is
    told how long to wait rather than being refused, because the work that
    uses this runs in the background where waiting is free.

  * Tokens are counted from what the API actually reports, not from an
    estimate, with a conservative estimate used only to decide whether a call
    fits before making it.

In-process, like the other limiters here. Counters reset on deploy, which
loses at most one cooldown window, and Render's free tier runs one instance.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field

# Measured from the account's own AI Studio dashboard. Both Gemma rows show
# the same allowance; the Gemini rows are an order of magnitude smaller.
DEFAULT_REQUESTS_PER_MINUTE = 30
DEFAULT_TOKENS_PER_MINUTE = 16_000
DEFAULT_COOLDOWN_SECONDS = 90.0

# One call is roughly 300 tokens in and 30 out with the category list in the
# prompt. Rounded up, because being wrong in this direction only costs a
# slightly early cooldown.
ESTIMATED_TOKENS_PER_CALL = 500


@dataclass
class _Slot:
    model: str
    requests: deque[float] = field(default_factory=deque)
    tokens: deque[tuple[float, int]] = field(default_factory=deque)
    cooling_until: float = 0.0

    def prune(self, now: float) -> None:
        cutoff = now - 60
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()
        while self.tokens and self.tokens[0][0] < cutoff:
            self.tokens.popleft()

    def tokens_used(self) -> int:
        return sum(count for _, count in self.tokens)


class ModelPool:
    def __init__(
        self,
        models: list[str],
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        tokens_per_minute: int = DEFAULT_TOKENS_PER_MINUTE,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute
        self.cooldown = cooldown_seconds
        self._slots = [_Slot(model=m) for m in models]
        self._lock = threading.Lock()

    @property
    def models(self) -> list[str]:
        return [s.model for s in self._slots]

    def acquire(self, estimated_tokens: int = ESTIMATED_TOKENS_PER_CALL) -> str | None:
        """Reserve a slot on whichever model is free, or None if all are cooling.

        The reservation is recorded immediately, before the call is made, so
        concurrent callers cannot both slip through the same last slot. The
        token figure is corrected afterwards by `record`.
        """
        now = time.monotonic()
        with self._lock:
            for slot in self._slots:
                if now < slot.cooling_until:
                    continue

                # Coming off a cooldown starts the minute over. Without this
                # the old timestamps are still inside the rolling window, the
                # very next call trips the ceiling again, and a model that has
                # served its 90 seconds goes straight back to sleep. With the
                # real numbers — 90s cooldown against a 60s window — the
                # window has drained anyway; this makes it true for any
                # configuration rather than only the lucky ones.
                if slot.cooling_until:
                    slot.cooling_until = 0.0
                    slot.requests.clear()
                    slot.tokens.clear()

                slot.prune(now)

                over_requests = len(slot.requests) + 1 > self.rpm
                over_tokens = slot.tokens_used() + estimated_tokens > self.tpm
                if over_requests or over_tokens:
                    # Sleep it now rather than let the next call be refused by
                    # the provider.
                    slot.cooling_until = now + self.cooldown
                    continue

                slot.requests.append(now)
                slot.tokens.append((now, estimated_tokens))
                return slot.model
        return None

    def record(self, model: str, actual_tokens: int) -> None:
        """Replace the estimate for the most recent call with what it cost."""
        if actual_tokens <= 0:
            return
        now = time.monotonic()
        with self._lock:
            for slot in self._slots:
                if slot.model != model or not slot.tokens:
                    continue
                stamp, _ = slot.tokens[-1]
                slot.tokens[-1] = (stamp, actual_tokens)
                slot.prune(now)
                if slot.tokens_used() >= self.tpm and now >= slot.cooling_until:
                    slot.cooling_until = now + self.cooldown
                return

    def trip(self, model: str) -> None:
        """Put a model to sleep because the provider refused it anyway."""
        now = time.monotonic()
        with self._lock:
            for slot in self._slots:
                if slot.model == model:
                    slot.cooling_until = now + self.cooldown
                    return

    def wait_seconds(self) -> float:
        """How long until any model frees up. 0 when one is available now."""
        now = time.monotonic()
        with self._lock:
            if not self._slots:
                return 0.0
            soonest = min(s.cooling_until for s in self._slots)
            return max(0.0, soonest - now)

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            out = []
            for slot in self._slots:
                slot.prune(now)
                out.append(
                    {
                        "model": slot.model,
                        "requests_this_minute": len(slot.requests),
                        "requests_limit": self.rpm,
                        "tokens_this_minute": slot.tokens_used(),
                        "tokens_limit": self.tpm,
                        "cooling_for": round(max(0.0, slot.cooling_until - now), 1),
                    }
                )
            return out

    def clear(self) -> None:
        """Test hook. Clears in place — callers hold this object."""
        with self._lock:
            for slot in self._slots:
                slot.requests.clear()
                slot.tokens.clear()
                slot.cooling_until = 0.0
