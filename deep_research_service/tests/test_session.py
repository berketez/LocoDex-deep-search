"""
Oturum hafızası testleri.

Ana davranış: aynı konu ikinci kez sorulduğunda araştırma tekrar koşturulmaz,
mevcut bulgulardan yanıtlanır.
"""

import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session import (  # noqa: E402
    ResearchEntry,
    ResearchSession,
    topic_overlap,
)


def _kayit(konu="gıda üretiminde yapay zeka kalite kontrol"):
    return ResearchEntry(
        topic=konu,
        report="# Rapor",
        findings=[
            {"statement": "Görüntü işleme kusur tespitinde kullanılıyor.",
             "confidence": 81, "supporting": [1], "contradicting": [],
             "newest_date": datetime(2026, 5, 1)},
            {"statement": "Talep tahmininde iyileşme %10-40.",
             "confidence": 55, "supporting": [2], "contradicting": [1],
             "newest_date": datetime(2026, 4, 1)},
        ],
        sources=[
            {"domain": "reuters.com", "url": "https://reuters.com/a",
             "title": "A", "published_at": datetime(2026, 5, 1)},
            {"domain": "arxiv.org", "url": "https://arxiv.org/b",
             "title": "B", "published_at": None},
        ],
        report_path="/tmp/r.md",
        duration_sec=120.0,
    )


class TestTopicOverlap:
    def test_ayni_konu_tam_ortusur(self):
        assert topic_overlap("yapay zeka gıda", "yapay zeka gıda") == 1.0

    def test_ilgisiz_konular_ortusmez(self):
        assert topic_overlap("yapay zeka gıda", "roket motoru tasarımı") == 0.0

    def test_durak_kelimeler_sayilmaz(self):
        # "ve", "ile", "bir" örtüşmeyi şişirmemeli
        assert topic_overlap("bu ve bir ile", "bu ve bir ile") == 0.0

    def test_bos_girdi_sifir(self):
        assert topic_overlap("", "yapay zeka") == 0.0


class TestEntry:
    def test_genel_guven_ortalamasi(self):
        assert _kayit().overall_confidence() == 68

    def test_en_guclu_bulgular_once(self):
        ust = _kayit().top_findings(1)
        assert ust[0]["confidence"] == 81

    def test_baglam_bloklari_bulgu_ve_kaynak_icerir(self):
        blok = _kayit().context_block()
        assert "BULGULAR" in blok and "KAYNAKLAR" in blok
        assert "reuters.com" in blok
        assert "ÇELİŞKİLİ" in blok  # ikinci bulgu çelişkili işaretli


class TestSiniflandirma:
    def test_gecmis_yokken_yeni_arastirma(self):
        oturum = ResearchSession("m", "Ollama")
        karar = asyncio.run(oturum.classify("herhangi bir konu"))
        assert karar["niyet"] == "yeni"

    def test_ayni_konu_tekrar_arastirilmaz(self):
        """Model çağrılmadan, örtüşmeye bakarak mevcut kayda yönlendirilmeli."""
        oturum = ResearchSession("m", "Ollama")
        oturum.entries.append(_kayit())
        karar = asyncio.run(
            oturum.classify("gıda üretiminde yapay zeka kalite kontrol")
        )
        assert karar["niyet"] == "takip"
        assert karar["kayit"] is oturum.entries[0]

    def test_yedek_siniflandirma_ilgisiz_konuyu_yeni_sayar(self):
        oturum = ResearchSession("m", "Ollama")
        oturum.entries.append(_kayit())
        karar = oturum._fallback_classify("roket motoru nozul tasarımı")
        assert karar["niyet"] == "yeni"

    def test_yedek_siniflandirma_soru_kalibini_takip_sayar(self):
        oturum = ResearchSession("m", "Ollama")
        oturum.entries.append(_kayit())
        karar = oturum._fallback_classify("kalite kontrol kısmını açıkla")
        assert karar["niyet"] == "takip"


class TestOturumKaydi:
    def test_kayit_eklenir_ve_son_kayit_dondurulur(self):
        class SahteArastirmaci:
            findings = [{"statement": "x", "confidence": 50,
                         "supporting": [1], "contradicting": [],
                         "newest_date": None}]
            sources = [{"domain": "a.com", "url": "https://a.com",
                        "title": "A", "published_at": None}]

        oturum = ResearchSession("m", "Ollama")
        oturum.add("konu", "# Rapor", SahteArastirmaci(), "/tmp/x.md", 10.0)
        assert len(oturum.entries) == 1
        assert oturum.last().topic == "konu"

    def test_bilinen_kaynaklar_toplanir(self):
        oturum = ResearchSession("m", "Ollama")
        oturum.entries.append(_kayit())
        assert oturum.known_sources() == {
            "https://reuters.com/a", "https://arxiv.org/b",
        }


class TestBaglamKaynakNumaralari:
    def test_limit_ustu_referansli_kaynak_listeye_girer(self):
        # 25 kaynak, bulgu 23 numaralı kaynağa dayanıyor. Liste 20 ile
        # kısaltılırken referans verilen 23 atlanmamalı; yoksa model listede
        # olmayan bir numaraya dayanmak zorunda kalıyordu.
        kaynaklar = [
            {"title": f"K{i}", "domain": f"d{i}.com", "published_at": None,
             "url": f"https://d{i}.com"}
            for i in range(1, 26)
        ]
        bulgular = [{
            "statement": "Yirmi üçüncü kaynağa dayanan bulgu.",
            "confidence": 90, "supporting": [23], "contradicting": [],
            "newest_date": None,
        }]
        kayit = ResearchEntry(
            topic="k", report="r", findings=bulgular, sources=kaynaklar,
            report_path=None, duration_sec=1.0,
        )
        blok = kayit.context_block()
        assert "[23] K23" in blok
        assert "[20] K20" in blok        # limit içi kaynaklar duruyor
        assert "[25] K25" not in blok    # limit üstü ve referanssız
