"""
Domain hız sınırlayıcı testleri.

Ana davranış: bir domain'in bekleme uykusu diğer domain'lerin isteklerini
durdurmaz (kilit uyku sırasında tutulmuyordu değil, tutuluyordu — düzeltildi).
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.rate_limiter import DomainRateLimiter  # noqa: E402


def test_bir_domain_beklerken_digeri_bloklanmaz():
    async def senaryo():
        limiter = DomainRateLimiter(default_delay=0.5)
        await limiter.wait("a.com")  # ilk istek, bekleme yok

        bekleyen = asyncio.create_task(limiter.wait("a.com"))  # ~0.5 sn uyuyacak
        await asyncio.sleep(0.05)  # görevin uykuya geçmesini bekle

        t0 = time.monotonic()
        await limiter.wait("b.com")  # farklı domain: hemen dönmeli
        b_suresi = time.monotonic() - t0

        await bekleyen
        return b_suresi

    b_suresi = asyncio.run(senaryo())
    assert b_suresi < 0.3, f"b.com isteği a.com beklemesine takıldı: {b_suresi:.2f}s"


def test_ayni_domain_beklemesi_korunur():
    async def senaryo():
        limiter = DomainRateLimiter(default_delay=0.3)
        await limiter.wait("a.com")
        t0 = time.monotonic()
        await limiter.wait("a.com")
        return time.monotonic() - t0

    gecen = asyncio.run(senaryo())
    assert gecen >= 0.25, f"aynı domain beklemesi uygulanmadı: {gecen:.2f}s"
