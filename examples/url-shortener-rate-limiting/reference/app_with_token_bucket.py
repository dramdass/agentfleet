"""API service WITH rate limiting using Token Bucket approach.

This shows how to integrate a token bucket rate limiter into the existing app.
"""

from flask import Flask, request, jsonify, redirect
import hashlib
import time
import threading
from typing import Dict, Optional

app = Flask(__name__)

# In-memory storage for URL mappings
url_store: Dict[str, str] = {}
url_stats: Dict[str, int] = {}


class TokenBucketRateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.rate = limit / window
        self.buckets: Dict[str, Dict] = {}
        self.lock = threading.Lock()

    def allow_request(self, user_id: str) -> bool:
        with self.lock:
            now = time.time()

            if user_id not in self.buckets:
                self.buckets[user_id] = {
                    "tokens": self.limit,
                    "last_update": now,
                }

            bucket = self.buckets[user_id]
            elapsed = now - bucket["last_update"]
            bucket["tokens"] = min(self.limit, bucket["tokens"] + elapsed * self.rate)
            bucket["last_update"] = now

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
            return False

    def reset(self, user_id: str) -> None:
        with self.lock:
            if user_id in self.buckets:
                del self.buckets[user_id]


# Initialize rate limiters for different endpoints
shorten_limiter = TokenBucketRateLimiter(limit=10, window=60)
redirect_limiter = TokenBucketRateLimiter(limit=100, window=60)


def shorten_url(long_url: str) -> str:
    """Generate a short hash for a URL."""
    hash_object = hashlib.md5(long_url.encode())
    return hash_object.hexdigest()[:8]


@app.route("/shorten", methods=["POST"])
def create_short_url():
    """Create a shortened URL with rate limiting (10/min per user)."""
    data = request.get_json()

    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' in request"}), 400

    long_url = data["url"]
    user_id = data.get("user_id", "anonymous")

    # Check rate limit
    if not shorten_limiter.allow_request(user_id):
        return jsonify({"error": "Rate limit exceeded. Max 10 requests per minute."}), 429

    short_code = shorten_url(long_url)
    url_store[short_code] = long_url
    url_stats[short_code] = 0

    return jsonify({
        "short_url": f"http://short.url/{short_code}",
        "long_url": long_url
    })


@app.route("/<short_code>", methods=["GET"])
def redirect_to_url(short_code: str):
    """Redirect to the original URL with rate limiting (100/min per user)."""
    user_id = request.args.get("user_id", "anonymous")

    # Check rate limit
    if not redirect_limiter.allow_request(user_id):
        return jsonify({"error": "Rate limit exceeded. Max 100 requests per minute."}), 429

    if short_code not in url_store:
        return jsonify({"error": "URL not found"}), 404

    url_stats[short_code] += 1
    return redirect(url_store[short_code])


@app.route("/stats/<short_code>", methods=["GET"])
def get_stats(short_code: str):
    """Get statistics for a shortened URL."""
    if short_code not in url_store:
        return jsonify({"error": "URL not found"}), 404

    return jsonify({
        "short_code": short_code,
        "long_url": url_store[short_code],
        "clicks": url_stats[short_code]
    })


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "urls_stored": len(url_store)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
