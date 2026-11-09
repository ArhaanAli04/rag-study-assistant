"""Client-side pacing under the eval project's free-tier limits.

Limits checked in AI Studio on 2026-11-09 for the eval project: gemini-3.5-flash-lite 15 RPM /
500 RPD; gemini-embedding-001 100 RPM / 30K TPM / 1K RPD. Pacing keeps a sliding 60-second window
of requests (and estimated tokens) under a ceiling set ~10% below each limit, so a run never
earns a 429 in the first place. A daily limit can't be paced around; callers stop on it instead.
"""
import math
import time
from collections import deque
from typing import Callable, Deque, Optional, Tuple

WINDOW_SECONDS = 60.0

GENERATION_RPM = 14
EMBEDDING_RPM = 90
EMBEDDING_TPM = 27_000


def estimate_tokens(text: str) -> int:
    """Over-estimate on purpose (English averages ~4 characters a token): a low guess would let
    the window overshoot the real TPM limit."""
    return max(1, math.ceil(len(text) / 3))


class RateLimiter:
    def __init__(
        self,
        requests_per_minute: int,
        tokens_per_minute: Optional[int] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self._clock = clock
        self._sleep = sleep
        self._window: Deque[Tuple[float, int]] = deque()
        self.waited_seconds = 0.0

    def _expire(self, now: float) -> None:
        while self._window and now - self._window[0][0] >= WINDOW_SECONDS:
            self._window.popleft()

    def _fits(self, tokens: int) -> bool:
        if len(self._window) >= self.requests_per_minute:
            return False
        if self.tokens_per_minute is None or not self._window:
            return True
        return sum(t for _, t in self._window) + tokens <= self.tokens_per_minute

    def acquire(self, tokens: int = 0) -> None:
        """Block until one more request of `tokens` fits in the window, then record it."""
        if self.tokens_per_minute is not None and tokens > self.tokens_per_minute:
            raise ValueError(f"a single request of {tokens} tokens exceeds {self.tokens_per_minute} TPM")
        while True:
            now = self._clock()
            self._expire(now)
            if self._fits(tokens):
                self._window.append((now, tokens))
                return
            wait = WINDOW_SECONDS - (now - self._window[0][0]) + 0.05
            self.waited_seconds += wait
            self._sleep(wait)
