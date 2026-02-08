"""
Unit tests for rate limiting.
"""

import pytest
import time

from src.utils.rate_limiter import InMemoryRateLimiter


class TestInMemoryRateLimiter:
    """Tests for the in-memory rate limiter."""

    def test_allows_requests_within_limit(self):
        limiter = InMemoryRateLimiter(requests_per_minute=10, burst=5)
        allowed, headers = limiter.check_rate_limit("test-key")
        assert allowed is True
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "10"

    def test_blocks_requests_over_limit(self):
        limiter = InMemoryRateLimiter(requests_per_minute=3, burst=1)

        for _ in range(3):
            allowed, _ = limiter.check_rate_limit("test-key")
            assert allowed is True

        allowed, headers = limiter.check_rate_limit("test-key")
        assert allowed is False
        assert "Retry-After" in headers

    def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter(requests_per_minute=2, burst=1)

        for _ in range(2):
            limiter.check_rate_limit("key-1")

        # key-1 should be at limit
        allowed1, _ = limiter.check_rate_limit("key-1")
        assert allowed1 is False

        # key-2 should still be allowed
        allowed2, _ = limiter.check_rate_limit("key-2")
        assert allowed2 is True

    def test_remaining_count_decreases(self):
        limiter = InMemoryRateLimiter(requests_per_minute=5, burst=2)

        _, headers1 = limiter.check_rate_limit("test-key")
        remaining1 = int(headers1["X-RateLimit-Remaining"])

        _, headers2 = limiter.check_rate_limit("test-key")
        remaining2 = int(headers2["X-RateLimit-Remaining"])

        assert remaining2 < remaining1

    def test_headers_present(self):
        limiter = InMemoryRateLimiter(requests_per_minute=10, burst=5)
        _, headers = limiter.check_rate_limit("test-key")

        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
