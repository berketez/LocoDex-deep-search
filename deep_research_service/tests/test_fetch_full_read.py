"""
Sayfa gövdesinin TAMAMEN okunduğunu doğrulayan regresyon testi.

`response.content.read(N)` aiohttp'de "N bayt oku" anlamına gelmez: akıştaki
ilk parçayı döndürür. 330 KB uzunluğundaki bir sayfadan yalnızca 36 KB
gelebiliyor ve gelen kısım <head>/<nav> olduğu için parse sonrası metin
çıkmıyordu; kaynak "okunabilir metin yok" gerekçesiyle eleniyordu. Parçalı
okumaya geçilince aynı arama sonucunda okunabilen kaynak sayısı 2/14'ten
9/14'e çıktı.

Buradaki sahte akış gerçek aiohttp davranışını taklit eder: read() yalnızca ilk
parçayı verir. Kod tekrar read()'e dönerse bu test kırılır.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verified_research import VerifiedDeepResearcher  # noqa: E402

PARCA = 512


class SahteAkis:
    """aiohttp StreamReader taklidi."""

    def __init__(self, veri):
        self.veri = veri

    async def iter_chunked(self, n):
        for i in range(0, len(self.veri), PARCA):
            yield self.veri[i : i + PARCA]

    async def read(self, n=-1):
        # Gerçek aiohttp davranışı: istenen boyut ne olursa olsun eldeki ilk
        # parça döner. Hatalı kullanım bu yüzden sessizce eksik veri getiriyordu.
        return self.veri[:PARCA]


class SahteYanit:
    status = 200
    charset = "utf-8"

    def __init__(self, veri, url="https://example.com/a"):
        self.content = SahteAkis(veri)
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        # Gerçek aiohttp yanıtında yönlendirme sonrası nihai adres; motor
        # bunu özel ağ kontrolü için okur.
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class SahteOturum:
    def __init__(self, veri):
        self.veri = veri

    def get(self, url, **kwargs):
        return SahteYanit(self.veri)


def test_sayfa_govdesi_tamamen_okunur():
    # İlk parça yalnızca <head> ve gezinme içerir; asıl metin sonrasındadır.
    dolgu = "<nav>" + ("menü " * 200) + "</nav>"
    govde = "<p>" + ("Sayfanın asıl gövde metni burada yer alır. " * 200) + "</p>"
    html = f"<html><head><title>Test</title></head><body>{dolgu}{govde}</body></html>"
    assert len(html.encode()) > PARCA * 4, "test kurgusu tek parçaya sığmamalı"

    arastirmaci = VerifiedDeepResearcher("m", "LM Studio", None)
    semafor = asyncio.Semaphore(1)
    kaynak, gerekce = asyncio.run(
        arastirmaci._fetch_one(
            SahteOturum(html.encode()),
            semafor,
            {"url": "https://example.com/a", "domain": "example.com", "title": "Test"},
        )
    )

    assert gerekce == "ok", f"kaynak elendi: {gerekce}"
    # İlk parça alınsaydı metin PARCA baytın altında kalır ve
    # SEARCH_MIN_CONTENT_CHARS eşiğini geçemezdi.
    assert len(kaynak["content"]) > PARCA, "sayfa gövdesi eksik okundu"
    assert "asıl gövde metni" in kaynak["content"]
