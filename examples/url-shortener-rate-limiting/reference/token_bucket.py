"""Token bucket rate limiter implementation.

This approach accumulates tokens at a fixed rate. Each request consumes one token.
If no tokens are available, the request is rate limited.
"""

import time
import threading
from typing import Dict


class RateLimiter:
    """Token bucket rate limiter.

    Args:
        limit: Maximum number of requests per window
        window: Time window in seconds
    """

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.rate = limit / window  # Tokens per second
        self.buckets: Dict[str, Dict] = {}
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

            if user_id not in self.buckets:
                # Initialize new bucket
                self.buckets[user_id] = {
                    "tokens": self.limit,
                    "last_update": now,
                }

            bucket = self.buckets[user_id]

            # Add tokens based on time elapsed
            elapsed = now - bucket["last_update"]
            bucket["tokens"] = min(self.limit, bucket["tokens"] + elapsed * self.rate)
            bucket["last_update"] = now

            # Try to consume a token
            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True

            return False

    def reset(self, user_id: str) -> None:
        """Reset rate limit for a user.

        Args:
            user_id: User identifier
        """
        with self.lock:
            if user_id in self.buckets:
                del self.buckets[user_id]
