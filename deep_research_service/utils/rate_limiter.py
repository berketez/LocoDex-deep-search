"""
Async per-domain rate limiter for web requests.

Prevents hammering the same domain by enforcing a minimum delay
between consecutive requests to each host.

Usage:
    from utils.rate_limiter import rate_limiter

    await rate_limiter.wait("arxiv.org")
    async with session.get(url) as resp:
        ...
"""

import asyncio
import time
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """Track last request time per domain and sleep if needed."""

    def __init__(self, default_delay: float = 2.0):
        """
        Args:
            default_delay: Minimum seconds between requests to the same domain.
        """
        self.default_delay = default_delay
        self._last_request: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, domain: str, delay: float | None = None) -> None:
        """Wait until it is safe to make a request to *domain*.

        If the last request to this domain was less than *delay* seconds ago,
        sleep the remaining time.  Otherwise return immediately.

        Args:
            domain: The target hostname (e.g. "arxiv.org").
            delay:  Per-call override; falls back to ``self.default_delay``.
        """
        if delay is None:
            delay = self.default_delay

        # Uyku kilit DIŞINDA yapılır: kilit altında uyumak, bir domain'in
        # beklemesinin tüm diğer domain'lere yapılan istekleri de durdurması
        # demekti. Uyandıktan sonra süre yeniden kontrol edilir; aynı domain'i
        # bekleyen birden çok görev sırayla geçer.
        while True:
            async with self._lock:
                now = time.monotonic()
                last = self._last_request.get(domain, 0.0)
                remaining = delay - (now - last)
                if remaining <= 0:
                    self._last_request[domain] = now
                    return

            logger.debug(
                "Rate limiter: sleeping %.2fs before hitting %s",
                remaining,
                domain,
            )
            await asyncio.sleep(remaining)

    def reset(self, domain: str | None = None) -> None:
        """Clear tracked timestamps.

        Args:
            domain: Reset a single domain.  ``None`` resets all.
        """
        if domain is None:
            self._last_request.clear()
        else:
            self._last_request.pop(domain, None)


def extract_domain(url: str) -> str:
    """Return the hostname from a URL, or the string itself as fallback."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or url
    except Exception:
        return url


# Module-level singleton so every module can ``from utils.rate_limiter import rate_limiter``
rate_limiter = DomainRateLimiter(default_delay=2.0)
