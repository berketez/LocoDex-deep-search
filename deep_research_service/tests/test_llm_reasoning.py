"""
Reasoning ("düşünen") model davranışı testleri.

Reasoning modelleri çıktı limitini önce düşünme zincirine harcar. Limit
düşükse model cevaba hiç başlayamadan kesilir: üretilen tokenların tamamı
düşünmeye gider, JSON çıkmaz ve çağrı tamamen boşa harcanır. Limiti artırıp
yeniden çağırmak da işe yaramaz, çünkü model baştan düşünmeye başlar.

Buradaki testler üç savunma hattını sabitler:
  1. Düşünme, sunucuya uygun alanla kapatılır (Ollama: think,
     LM Studio: reasoning_effort).
  2. Sunucu alanı tanımıyorsa alan düşürülür ve durum önbelleğe alınır —
     her çağrıda iki HTTP isteği yapılmaz.
  3. Çıktı yine de kesilirse eldeki kısmi metinden kurtarma denenir;
     ancak kurtarılamazsa yeniden çağrı yapılır.
"""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import (  # noqa: E402
    LLMError,
    LocalLLMClient,
    _strip_reasoning,
    extract_json,
)
from research_constants import LLM_MAX_OUTPUT_TOKENS  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _lm_yanit(content="", finish="stop", reasoning=""):
    """LM Studio /v1/chat/completions yanıt şeması."""
    return {
        "choices": [
            {
                "message": {"content": content, "reasoning_content": reasoning},
                "finish_reason": finish,
            }
        ]
    }


class SahteGonderici:
    """_post yerine geçer; giden payload'ları kaydeder, sıradaki yanıtı döner."""

    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.payloadlar = []

    async def __call__(self, session, url, payload):
        # payload sonradan mutasyona uğradığı için anlık kopyası saklanır
        self.payloadlar.append(json.loads(json.dumps(payload)))
        sonuc = self.yanitlar.pop(0)
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc


class TestReasoningSoyma:
    def test_kapali_blok_atilir(self):
        assert _strip_reasoning('<think>düşünüyorum</think>{"a": 1}') == '{"a": 1}'

    def test_kapanmamis_blok_sonrasi_atilir(self):
        # Çıktı düşünme sırasında kesilmiş: <think> sonrası JSON içermez
        assert _strip_reasoning('{"a": 1}<think>yarım kald') == '{"a": 1}'

    def test_think_yoksa_metin_degismez(self):
        assert _strip_reasoning('{"a": 1}') == '{"a": 1}'

    def test_bos_girdi(self):
        assert _strip_reasoning("") == ""
        assert _strip_reasoning(None) is None

    def test_dusunme_icindeki_ornek_json_kurtarilmaz(self):
        # Model düşünürken örnek JSON yazarsa gerçek cevapla karışmamalı
        ham = '<think>belki {"yanlis": 1} olur</think>{"dogru": 2}'
        assert extract_json(ham) == {"dogru": 2}


class TestDusunmeKapatma:
    def test_lm_studio_reasoning_effort_none_gonderilir(self):
        # LM Studio'nun MLX motorunda düşünmeyi kapatan alan budur;
        # chat_template_kwargs sessizce yok sayıldığı için tek başına yetmez.
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([_lm_yanit('{"a": 1}')])
        istemci._post = sahte
        sonuc = _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert sonuc == '{"a": 1}'
        assert sahte.payloadlar[0]["reasoning_effort"] == "none"
        assert sahte.payloadlar[0]["chat_template_kwargs"] == {"enable_thinking": False}

    def test_ollama_think_false_gonderilir(self):
        istemci = LocalLLMClient("m", "Ollama")
        sahte = SahteGonderici([{"response": '{"a": 1}'}])
        istemci._post = sahte
        _run(istemci._call_ollama(None, "h", "p", "s", 100, 0.1, True))
        assert sahte.payloadlar[0]["think"] is False

    def test_acikca_istenirse_dusunme_kapatilmaz(self):
        istemci = LocalLLMClient("m", "LM Studio", enable_thinking=True)
        sahte = SahteGonderici([_lm_yanit('{"a": 1}')])
        istemci._post = sahte
        _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert "chat_template_kwargs" not in sahte.payloadlar[0]
        assert "reasoning_effort" not in sahte.payloadlar[0]


class TestAlanDusurme:
    def test_desteklenmeyen_alan_dusurulur_ve_onbelleklenir(self):
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([
            LLMError("HTTP 400", status=400),   # response_format reddedildi
            _lm_yanit('{"a": 1}'),
            _lm_yanit('{"b": 2}'),
        ])
        istemci._post = sahte
        _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert "response_format" in istemci._unsupported

        # İkinci çağrı reddedilen alanı hiç göndermemeli: toplam 3 istek
        # (1 ret + 1 başarı + 1 başarı), 4 değil.
        _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert len(sahte.payloadlar) == 3
        assert "response_format" not in sahte.payloadlar[2]
        assert sahte.payloadlar[2]["chat_template_kwargs"] == {"enable_thinking": False}

    def test_gecici_hatada_alan_dusurulmez(self):
        # 5xx geçicidir; alan düşürmek hatayı maskeler
        istemci = LocalLLMClient("m", "LM Studio")
        istemci._post = SahteGonderici([LLMError("HTTP 503", status=503)])
        with pytest.raises(LLMError):
            _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert not istemci._unsupported


class TestKesilmeDavranisi:
    def test_kesik_json_yeniden_cagirmadan_kurtarilir(self):
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([_lm_yanit('{"b": [{"x": 1}, {"x": 2', finish="length")])
        istemci._post = sahte
        sonuc = _run(istemci.call_json("p", max_tokens=100))
        assert [e["x"] for e in sonuc["b"]] == [1]
        assert len(sahte.payloadlar) == 1  # kurtarıldı, ikinci çağrı yok

    def test_kurtarilamayan_kesikte_limit_yukseltilip_yeniden_denenir(self):
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([
            _lm_yanit("hâlâ düşünüyorum, JSON yok", finish="length"),
            _lm_yanit('{"a": 1}'),
        ])
        istemci._post = sahte
        sonuc = _run(istemci.call_json("p", max_tokens=1000, retries=1))
        assert sonuc == {"a": 1}
        assert sahte.payloadlar[0]["max_tokens"] == 1000
        assert sahte.payloadlar[1]["max_tokens"] == 2000

    def test_limit_tavani_asilmaz(self):
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([
            _lm_yanit("düşünme", finish="length"),
            _lm_yanit('{"a": 1}'),
        ])
        istemci._post = sahte
        _run(istemci.call_json("p", max_tokens=LLM_MAX_OUTPUT_TOKENS, retries=1))
        assert sahte.payloadlar[1]["max_tokens"] == LLM_MAX_OUTPUT_TOKENS

    def test_serbest_metinde_kesik_cikti_atilmaz(self):
        # Yarım rapor, hiç rapordan iyidir
        istemci = LocalLLMClient("m", "LM Studio")
        istemci._post = SahteGonderici([_lm_yanit("Rapor yarıda", finish="length")])
        sonuc = _run(istemci.call("p", json_mode=False))
        assert sonuc == "Rapor yarıda"

    def test_tamamlanmis_yanitta_reasoning_content_yedegi(self):
        # Düşünme kapatılamadıysa model cevabı o alanda bitirmiş olabilir;
        # yanıt tamamlandığı için oradan okumak güvenlidir.
        istemci = LocalLLMClient("m", "LM Studio")
        istemci._post = SahteGonderici([_lm_yanit("", reasoning='{"a": 1}')])
        sonuc = _run(istemci._call_lm_studio(None, "h", "p", "s", 100, 0.1, True))
        assert sonuc == '{"a": 1}'

    def test_kesik_dusunmeden_json_kurtarilmaz(self):
        """
        Kesik yanıtta düşünme metni cevap sayılmamalı.

        Model düşünürken taslak JSON yazar ("belki {...} olur"); yanıt orada
        kesildiyse bu taslak gerçek cevap DEĞİLDİR. Kurtarılırsa pipeline
        sessizce yanlış veriyle devam eder — hatasız görünen bir bozulma.
        """
        istemci = LocalLLMClient("m", "LM Studio")
        sahte = SahteGonderici([
            _lm_yanit("", finish="length", reasoning='belki {"konu_turu": "taslak"} olur'),
            _lm_yanit('{"konu_turu": "gercek"}'),
        ])
        istemci._post = sahte
        sonuc = _run(istemci.call_json("p", max_tokens=100, retries=1))
        assert sonuc == {"konu_turu": "gercek"}

    def test_ollama_kesik_thinking_alanindan_kurtarilmaz(self):
        istemci = LocalLLMClient("m", "Ollama")
        istemci._post = SahteGonderici([
            {"response": "", "thinking": 'belki {"a": "taslak"}', "done_reason": "length"},
        ])
        with pytest.raises(LLMError) as hata:
            _run(istemci._call_ollama(None, "h", "p", "s", 100, 0.1, True))
        assert hata.value.truncated
        assert hata.value.partial == ""
