"""
Smart (eski) motor regresyon testleri.

Ana davranışlar: dil algılama tam kelime eşleşmesi kullanır (alt-string
araması İngilizce soruları Türkçe sanıyordu) ve model hata metinleri rapor
gövdesi olarak dönmez, LLMError yükseltilir (hata metni önbelleğe
"başarılı sonuç" diye yazılıyordu).
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import LLMError  # noqa: E402
from smart_multilingual_research import SmartMultilingualResearcher  # noqa: E402


class SahteWS:
    async def send_json(self, data):
        pass


def _motor():
    return SmartMultilingualResearcher("m", "Ollama", SahteWS())


class TestDilAlgilama:
    def test_ingilizce_soru_turkce_sanilmaz(self):
        # "ne" ⊂ "newest", "kim" ⊂ "kimchi" alt-string tuzakları
        assert asyncio.run(_motor().detect_language(
            "what is the newest iphone model")) == "english"
        assert asyncio.run(_motor().detect_language(
            "kimchi fermentation guide")) == "english"

    def test_turkce_soru_tespit_edilir(self):
        assert asyncio.run(_motor().detect_language(
            "yapay zeka nedir")) == "turkish"
        assert asyncio.run(_motor().detect_language(
            "gıda üretiminde verimlilik")) == "turkish"


class TestHataMetniRaporOlamaz:
    def test_rapor_govdesi_hata_metniyse_llmerror(self):
        motor = _motor()

        async def sahte_model(prompt, system_prompt="", max_tokens=3000):
            return "Model bağlantı hatası: sunucuya erişilemedi"

        motor.call_local_model = sahte_model
        with pytest.raises(LLMError):
            asyncio.run(motor.generate_comprehensive_report("konu", [], "turkish", []))

    def test_ic_istisna_llmerror_olarak_yukselir(self):
        motor = _motor()

        async def patla(topic):
            raise RuntimeError("beklenmedik hata")

        motor.detect_language = patla
        with pytest.raises(LLMError):
            asyncio.run(motor.run_research("konu"))
