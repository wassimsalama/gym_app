"""Request rate limiting.

Keeps one misbehaving client — a script, a runaway retry loop, someone bored —
from monopolising the API or running up a bill. Counters live in process
memory, which is the right trade at this size: a hundred users on one worker
need nothing more, and it costs no extra service to run.

The limitation is honest and worth knowing: counters are per process. Run
several workers and each enforces its own share, so effective limits multiply
by worker count. Restarting clears them. At the point that matters, this module
is the only thing that has to change — swapping the store for Redis leaves
every caller untouched.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

#: Stop tracking keys after this long idle, so memory cannot grow without bound.
KEY_TTL_SECONDS = 3600

#: How often to sweep expired keys, in requests handled.
SWEEP_EVERY = 500


@dataclass(frozen=True)
class Limit:
    """`max_requests` allowed in any `window_seconds` stretch."""

    max_requests: int
    window_seconds: int

    @property
    def description(self) -> str:
        per = (
            "second"
            if self.window_seconds == 1
            else "minute"
            if self.window_seconds == 60
            else "hour"
            if self.window_seconds == 3600
            else f"{self.window_seconds}s"
        )
        return f"{self.max_requests} per {per}"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    #: Seconds until the caller may retry. Zero when allowed.
    retry_after: int


class SlidingWindowLimiter:
    """A sliding window over request timestamps.

    Sliding rather than fixed: a fixed window lets someone spend their whole
    allowance at 10:59 and again at 11:00, which is twice the intended rate at
    exactly the moment it matters least to them and most to the server.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._since_sweep = 0

    def check(self, key: str, limit: Limit, *, now: float | None = None) -> Decision:
        """Record an attempt and say whether it is allowed."""
        moment = time.monotonic() if now is None else now
        cutoff = moment - limit.window_seconds

        with self._lock:
            self._maybe_sweep(moment)

            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit.max_requests:
                # The oldest hit in the window is the one that has to age out.
                retry_after = max(1, int(hits[0] + limit.window_seconds - moment) + 1)
                return Decision(allowed=False, remaining=0, retry_after=retry_after)

            hits.append(moment)
            return Decision(
                allowed=True,
                remaining=limit.max_requests - len(hits),
                retry_after=0,
            )

    def _maybe_sweep(self, moment: float) -> None:
        """Drop keys nobody has touched in a while. Called under the lock."""
        self._since_sweep += 1
        if self._since_sweep < SWEEP_EVERY:
            return
        self._since_sweep = 0

        cutoff = moment - KEY_TTL_SECONDS
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        """Clear everything. Tests only."""
        with self._lock:
            self._hits.clear()
            self._since_sweep = 0

    @property
    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)


#: Process-wide limiter. One instance so every route shares the same counters.
limiter = SlidingWindowLimiter()
