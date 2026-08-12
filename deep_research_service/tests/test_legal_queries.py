"""
Mevzuat sorularında birincil kaynak hedefleme testi.

Mevzuat sorularında serbest arama doğru cevabı bulsa bile kanıtı ikincil
kaynaklara (blog, haber) dayandırıyor; birincil mevzuat metni sonuçlara hiç
girmiyor. Aynı içerik `site:` operatörüyle ilk denemede doğrudan resmî
yayından geliyor. Kuralın ne olduğu sorulduğunda kanunun kendisi, hakkında
yazılan yorumdan üstündür; sorgu üretimi bunu hedeflemek zorunda.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_constants import DOMAIN_PRIOR_HIGH  # noqa: E402
from verified_research import VerifiedDeepResearcher, domain_prior  # noqa: E402


def _analiz(konu_turu):
    return {
        "konu_turu": konu_turu,
        "zaman_duyarliligi": "moderate",
        "alt_sorular": ["alt soru"],
        "anahtar_terimler": ["terim"],
    }


def _prompt_yakala(arastirmaci):
    """LLM'i çağırmadan üretilen prompt'u yakalar."""
    yakalanan = {}

    async def sahte_call_json(prompt, **kwargs):
        yakalanan["prompt"] = prompt
        return {"sorgular": ["ornek sorgu"]}

    arastirmaci.llm.call_json = sahte_call_json
    return yakalanan


def test_hukuk_konusunda_birincil_mevzuat_hedeflenir():
    arastirmaci = VerifiedDeepResearcher("m", "LM Studio", None)
    yakalanan = _prompt_yakala(arastirmaci)

    asyncio.run(arastirmaci.generate_queries("etiketleme kuralı", _analiz("hukuk")))

    prompt = yakalanan["prompt"]
    assert "site:eur-lex.europa.eu" in prompt, "AB mevzuat kaynağı hedeflenmeli"
    assert "site:mevzuat.gov.tr" in prompt, "Türk mevzuat kaynağı hedeflenmeli"
    assert "KANUN METNİNİ" in prompt


def test_hukuk_disi_konuda_kural_eklenmez():
    # Her soruya site: operatörü eklemek genel araştırmayı daraltır.
    arastirmaci = VerifiedDeepResearcher("m", "LM Studio", None)
    yakalanan = _prompt_yakala(arastirmaci)

    asyncio.run(arastirmaci.generate_queries("bir teknoloji konusu", _analiz("teknoloji")))

    assert "site:eur-lex.europa.eu" not in yakalanan["prompt"]


def test_birincil_mevzuat_kaynaklari_en_yuksek_oncele_sahip():
    """
    Liste üyeliği değil, sonuçtaki öncel test edilir: eur-lex ve mevzuat.gov.tr
    zaten `europa.eu` / `.gov.tr` kurallarıyla kapsanır, ayrıca yazılmaları
    gerekmez. Önemli olan hangi yoldan geldikleri değil, blogun önüne
    geçmeleridir.
    """
    for alan in ("eur-lex.europa.eu", "gesetze-im-internet.de",
                 "mevzuat.gov.tr", "resmigazete.gov.tr"):
        assert domain_prior(alan) == DOMAIN_PRIOR_HIGH, f"{alan} yüksek öncelli olmalı"
        # Mevzuat bulgusunun aksi halde dayanacağı blog türü kaynak
        assert domain_prior(alan) > domain_prior("ma435ze.wordpress.com")
