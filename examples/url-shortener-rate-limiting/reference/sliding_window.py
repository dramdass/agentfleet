"""Sliding window rate limiter implementation.

This approach tracks exact timestamps of requests in a rolling window.
Most accurate but higher memory usage.
"""

import time
import threading
from typing import Dict, List


class RateLimiter:
    """Sliding window rate limiter.

    Args:
        limit: Maximum number of requests per window
        window: Time window in seconds
    """

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.requests: Dict[str, List[float]] = {}
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

            if user_id not in self.requests:
                self.requests[user_id] = []

            # Remove timestamps outside the window
            cutoff = now - self.window
            self.requests[user_id] = [
                ts for ts in self.requests[user_id] if ts > cutoff
            ]

            # Check if limit would be exceeded
            if len(self.requests[user_id]) < self.limit:
                self.requests[user_id].append(now)
                return True

            return False

    def reset(self, user_id: str) -> None:
        """Reset rate limit for a user.

        Args:
            user_id: User identifier
        """
        with self.lock:
            if user_id in self.requests:
                del self.requests[user_id]
