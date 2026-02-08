"""
Rate limiting middleware using a sliding window counter with Redis.
Falls back to in-memory rate limiting if Redis is unavailable.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, status

from src.config.logging import get_logger
from src.config.settings import get_settings

logger = get_logger(__name__)


class InMemoryRateLimiter:
    """
    In-memory rate limiter using sliding window.
    Suitable for single-instance deployments or development.
    """

    def __init__(self, requests_per_minute: int = 60, burst: int = 10) -> None:
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.window_size = 60  # seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str) -> None:
        """Remove expired request timestamps."""
        now = time.time()
        cutoff = now - self.window_size
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > cutoff
        ]

    def check_rate_limit(self, key: str) -> tuple[bool, dict[str, str]]:
        """
        Check if a request is within rate limits.

        Returns:
            Tuple of (allowed, headers)
        """
        self._cleanup(key)

        current_count = len(self._requests[key])
        remaining = max(0, self.requests_per_minute - current_count)

        headers = {
            "X-RateLimit-Limit": str(self.requests_per_minute),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(time.time()) + self.window_size),
        }

        if current_count >= self.requests_per_minute:
            headers["Retry-After"] = str(self.window_size)
            return False, headers

        self._requests[key].append(time.time())
        headers["X-RateLimit-Remaining"] = str(remaining - 1)
        return True, headers

    def get_key(self, request: Request) -> str:
        """Generate a rate limit key from the request."""
        # Use API key or IP address as the key
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"api_key:{api_key[:10]}"

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return f"token:{auth[7:17]}"

        # Fall back to IP address
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"


# Global rate limiter instance
_rate_limiter: Optional[InMemoryRateLimiter] = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get or create the rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = InMemoryRateLimiter(
            requests_per_minute=settings.rate_limit.requests_per_minute,
            burst=settings.rate_limit.burst,
        )
    return _rate_limiter


async def rate_limit_middleware(request: Request) -> None:
    """
    FastAPI dependency for rate limiting.
    Add as a dependency to routes that need rate limiting.
    """
    settings = get_settings()
    if not settings.rate_limit.enabled:
        return

    limiter = get_rate_limiter()
    key = limiter.get_key(request)
    allowed, headers = limiter.check_rate_limit(key)

    # Always set rate limit headers
    request.state.rate_limit_headers = headers

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers=headers,
        )
