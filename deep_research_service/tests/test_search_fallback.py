"""
Arama yedek motoru testi.

Varsayılan motor arka arkaya sorguda geçici olarak boş dönebiliyor: koşu
sırasında 0 sonuç veren bir sorgu kısa süre sonra hem varsayılan hem yedek
motorlarda sonuç veriyor. Boşluk kalıcı değil geçici olduğu için, bir sorgu
tek bir motorun anlık davranışı yüzünden kaybedilmemelidir.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verified_research import VerifiedDeepResearcher  # noqa: E402


def _sahte_ddgs_modulu(cagrilar, sonuc_veren):
    """Yalnızca `sonuc_veren` motorunda sonuç dönen sahte ddgs modülü."""

    class SahteDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=None, timelimit=None, backend=None):
            cagrilar.append(backend)
            if backend == sonuc_veren:
                return [{"title": "Başlık", "href": "https://ornek.com/a", "body": "gövde"}]
            return []

        def news(self, *args, **kwargs):
            return []

    modul = types.ModuleType("ddgs")
    modul.DDGS = SahteDDGS
    return modul


def test_varsayilan_bos_donerse_yedek_motor_denenir(monkeypatch):
    cagrilar = []
    monkeypatch.setitem(sys.modules, "ddgs", _sahte_ddgs_modulu(cagrilar, "bing"))

    arastirmaci = VerifiedDeepResearcher("m", "LM Studio", None)
    sonuc = arastirmaci._search_sync("sorgu", "moderate", want_news=False)

    assert cagrilar[0] is None, "önce varsayılan motor denenmeli"
    assert "bing" in cagrilar, "varsayılan boş dönünce yedek denenmeli"
    assert len(sonuc) == 1
    assert sonuc[0]["engine"] == "ddgs-bing", "sonucun hangi motordan geldiği kayıtlı olmalı"


def test_varsayilan_sonuc_verirse_yedek_denenmez(monkeypatch):
    # Yedekler yalnızca gerektiğinde çalışmalı; her sorguda 5 motora gitmek
    # aramayı yavaşlatır ve gereksiz istek üretir.
    cagrilar = []
    monkeypatch.setitem(sys.modules, "ddgs", _sahte_ddgs_modulu(cagrilar, None))

    arastirmaci = VerifiedDeepResearcher("m", "LM Studio", None)
    sonuc = arastirmaci._search_sync("sorgu", "moderate", want_news=False)

    assert cagrilar == [None], f"gereksiz yedek çağrısı: {cagrilar}"
    assert len(sonuc) == 1
