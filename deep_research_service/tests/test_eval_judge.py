"""Eval düzeneği testleri — yargıç ve koşucu, model çağrısı olmadan."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval")
)

import judge  # noqa: E402
import kosucu  # noqa: E402


class SahteLLM:
    def __init__(self, cevap):
        self._cevap = cevap

    async def call_json(self, *args, **kwargs):
        return self._cevap


def _degerlendir(monkeypatch, cevap):
    monkeypatch.setattr(judge, "LocalLLMClient", lambda m, s: SahteLLM(cevap))
    return asyncio.run(judge.degerlendir("soru", "# Rapor", "beklenti"))


class TestYargic:
    def test_gecerli_puanlar_toplanir(self, monkeypatch):
        sonuc = _degerlendir(monkeypatch, {
            "olgusal_dogruluk": 0.8, "atif_uyumu": 0.7, "tamlik": 0.6,
            "kaynak_kalitesi": 0.9, "guncellik_durustlugu": 0.5,
            "gerekce": "iyi",
        })
        assert sonuc["toplam"] == 0.7
        assert sonuc["gecti"] is True
        assert sonuc["gerekce"] == "iyi"

    def test_olgusal_taban_gecmeyi_engeller(self, monkeypatch):
        # Toplam eşiği geçse bile olgusal doğruluk tabanın altındaysa kalır
        sonuc = _degerlendir(monkeypatch, {
            "olgusal_dogruluk": 0.3, "atif_uyumu": 1.0, "tamlik": 1.0,
            "kaynak_kalitesi": 1.0, "guncellik_durustlugu": 1.0,
        })
        assert sonuc["toplam"] >= judge.GECME_TOPLAM_ESIGI
        assert sonuc["gecti"] is False

    def test_bozuk_yanit_kalir(self, monkeypatch):
        sonuc = _degerlendir(monkeypatch, None)
        assert sonuc["gecti"] is False
        assert "hata" in sonuc

    def test_aralik_disi_puan_kirpilir(self, monkeypatch):
        sonuc = _degerlendir(monkeypatch, {
            "olgusal_dogruluk": 1.7, "atif_uyumu": -0.4, "tamlik": "0.5",
            "kaynak_kalitesi": "bozuk", "guncellik_durustlugu": 0.5,
        })
        assert sonuc["olgusal_dogruluk"] == 1.0
        assert sonuc["atif_uyumu"] == 0.0
        assert sonuc["tamlik"] == 0.5
        assert sonuc["kaynak_kalitesi"] == 0.0


class TestKosucu:
    def test_sorular_yuklenir(self):
        sorular = kosucu.sorulari_yukle()
        assert len(sorular) == 20
        assert {s["no"] for s in sorular} == set(range(1, 21))
        assert all(s["soru"] and s["tur"] and s["beklenti"] for s in sorular)

    def test_rapor_metrikleri_ayiklanir(self):
        rapor = (
            "# Derin Araştırma Raporu: x\n"
            "**Genel Güven Skoru:** %78 (orta güven)\n"
            "**Kaynak:** 12 doğrulanmış | **Sorgu:** 9 | **Süre:** 412 sn\n"
        )
        stderr = "  Döküm     analiz 21 sn · kaynak analizi 4 dk 02 sn\n"
        m = kosucu._rapor_metrikleri(rapor, stderr)
        assert m["kaynak_sayisi"] == 12
        assert m["genel_guven"] == 78
        assert "kaynak analizi" in m["sure_dokumu"]

    def test_ozet_tablo_uretilir(self):
        tablo = kosucu._ozet_tablo([
            {"no": 1, "tur": "guncel-olgu", "sure_sn": 300.0,
             "kaynak_sayisi": 10, "genel_guven": 80,
             "judge": {"toplam": 0.75, "gecti": True}},
            {"no": 2, "tur": "tuzak", "sure_sn": 200.0, "hata": "zaman aşımı"},
        ])
        assert "| 1 |" in tablo and "EVET" in tablo
        assert "2 koşu · 1 geçti" in tablo
