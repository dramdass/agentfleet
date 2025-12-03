"""Fixed window rate limiter implementation.

This approach divides time into fixed intervals and resets counters at boundaries.
Simple but has a boundary bug—allows 2x requests at window edge.

THIS IMPLEMENTATION INTENTIONALLY HAS THE BOUNDARY BUG for demonstration purposes.
"""

import time
import threading
from typing import Dict


class RateLimiter:
    """Fixed window rate limiter with boundary bug.

    Args:
        limit: Maximum number of requests per window
        window: Time window in seconds
    """

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.windows: Dict[str, Dict] = {}
        self.lock = threading.Lock()

    def allow_request(self, user_id: str) -> bool:
        """Check if request should be allowed for user.

        Args:
            user_id: User identifier

        Returns:
            True if request allowed, False if rate limited
        """
        with self.lock:
            now = time.time()
            window_start = int(now / self.window) * self.window

            if user_id not in self.windows:
                self.windows[user_id] = {
                    "window_start": window_start,
                    "count": 0,
                }

            user_window = self.windows[user_id]

            # Check if we're in a new window
            if window_start > user_window["window_start"]:
                user_window["window_start"] = window_start
                user_window["count"] = 0

            # Check limit
            if user_window["count"] < self.limit:
                user_window["count"] += 1
                return True

            return False

    def reset(self, user_id: str) -> None:
        """Reset rate limit for a user.

        Args:
            user_id: User identifier
        """
        with self.lock:
            if user_id in self.windows:
                del self.windows[user_id]
