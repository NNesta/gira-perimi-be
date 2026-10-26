import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-process limiter for brute-force protection (single API instance)."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until another attempt is allowed (0 = allowed now)."""
        now = time.monotonic()
        hits = self._prune(key, now)
        if len(hits) < self.max_attempts:
            return 0
        return max(1, int(self.window - (now - hits[0])))

    def hit(self, key: str) -> None:
        self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
