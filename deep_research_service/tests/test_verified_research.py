"""verified_research ve llm_client birim testleri — ağ ve LLM gerektirmez."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_client import extract_json
from research_constants import (
    CONFIDENCE_CONTRADICTED_CAP,
    CONFIDENCE_SINGLE_SOURCE_CAP,
    DOMAIN_PRIOR_HIGH,
    DOMAIN_PRIOR_LOW,
    DOMAIN_PRIOR_MEDIUM,
    DOMAIN_PRIOR_UNKNOWN,
    DOMAIN_PRIOR_UNTRUSTED,
)
from verified_research import (
    VerifiedDeepResearcher,
    as_bool,
    compute_claim_confidence,
    confidence_label,
    domain_of,
    domain_prior,
    source_reliability,
)


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_in_fence(self):
        text = 'Cevap:\n```json\n{"sorgular": ["x", "y"]}\n```\nbitti'
        assert extract_json(text) == {"sorgular": ["x", "y"]}

    def test_json_with_prefix_text(self):
        text = 'İşte JSON: {"ilgili": true, "guvenilirlik": 7, "iddialar": []}'
        assert extract_json(text) == {"ilgili": True, "guvenilirlik": 7, "iddialar": []}

    def test_trailing_comma_recovery(self):
        text = '{"a": [1, 2,], "b": {"c": 3,},}'
        assert extract_json(text) == {"a": [1, 2], "b": {"c": 3}}

    def test_array(self):
        assert extract_json("sonuç: [1, 2, 3]") == [1, 2, 3]

    def test_nested_braces_in_string(self):
        text = '{"metin": "süslü } parantez { içerir", "n": 1}'
        assert extract_json(text) == {"metin": "süslü } parantez { içerir", "n": 1}

    def test_invalid_first_block_then_valid(self):
        # İlk dengeli blok bozuksa metnin devamındaki geçerli JSON bulunmalı
        text = '{bozuk: değer} ama sonra {"a": 1} geliyor'
        assert extract_json(text) == {"a": 1}

    def test_garbage_returns_none(self):
        assert extract_json("hiç json yok") is None
        assert extract_json("") is None
        assert extract_json(None) is None


class TestDomainHelpers:
    def test_domain_of_strips_www(self):
        assert domain_of("https://www.example.com/path?q=1") == "example.com"

    def test_domain_of_invalid(self):
        assert domain_of("not a url") == ""

    def test_prior_high(self):
        assert domain_prior("reuters.com") == DOMAIN_PRIOR_HIGH

    def test_prior_subdomain_matches(self):
        assert domain_prior("blog.reuters.com") == DOMAIN_PRIOR_HIGH

    def test_prior_medium_turkish_news(self):
        assert domain_prior("aa.com.tr") == DOMAIN_PRIOR_MEDIUM

    def test_prior_low(self):
        assert domain_prior("reddit.com") == DOMAIN_PRIOR_LOW

    def test_prior_unknown(self):
        assert domain_prior("rastgele-site-123.net") == DOMAIN_PRIOR_UNKNOWN

    def test_prior_gov_tr(self):
        assert domain_prior("mevzuat.gov.tr") == DOMAIN_PRIOR_HIGH

    def test_prior_untrusted_pattern(self):
        assert domain_prior("best-affiliate-deals.com") == DOMAIN_PRIOR_UNTRUSTED

    def test_akademik_alt_alan_kurumsal_oncel_alir(self):
        assert domain_prior("kent.edu.tr") == DOMAIN_PRIOR_HIGH
        assert domain_prior("cs.stanford.edu") == DOMAIN_PRIOR_HIGH

    def test_pazarlama_alt_alani_kurumsal_oncel_almaz(self):
        # Üniversitenin sertifika/kurs satış sayfası akademik yayın değildir
        assert domain_prior("sertifika.kent.edu.tr") == DOMAIN_PRIOR_UNKNOWN
        assert domain_prior("egitim.ornek.edu.tr") == DOMAIN_PRIOR_UNKNOWN
        assert domain_prior("shop.ornek.edu") == DOMAIN_PRIOR_UNKNOWN

    def test_kurumsal_listede_olan_alan_etkilenmez(self):
        # Açıkça güvenilir listesindeki alanlar alt alan kuralından etkilenmez
        assert domain_prior("news.mit.edu") == DOMAIN_PRIOR_HIGH

    def test_source_reliability_blend(self):
        # 0.6 * 0.9 + 0.4 * 0.8 = 0.86
        assert source_reliability(0.9, 8) == pytest.approx(0.86)

    def test_source_reliability_clamps_llm(self):
        assert source_reliability(0.5, 99) == pytest.approx(0.6 * 0.5 + 0.4 * 1.0)

    def test_source_reliability_zero_score_not_defaulted(self):
        # 0 puan geçerli bir değerlendirmedir; 5'e yuvarlanmamalı
        assert source_reliability(0.1, 0) == pytest.approx(0.06)
        assert source_reliability(0.1, 0) < source_reliability(0.1, 1)

    def test_source_reliability_none_defaults_to_5(self):
        assert source_reliability(0.5, None) == pytest.approx(0.6 * 0.5 + 0.4 * 0.5)


class TestBulguGecerliligi:
    """Bozuk model çıktısından gelen anlamsız parçalar bulgu sayılmamalı."""

    @staticmethod
    def _v(metin):
        from verified_research import _is_valid_finding

        return _is_valid_finding(metin)

    def test_tam_cumle_kabul_edilir(self):
        assert self._v(
            "Yapay zeka destekli görüntüleme sistemleri kusurları tespit eder."
        )

    def test_bozuk_json_parcasi_elenir(self):
        assert not self._v("ownset")
        assert not self._v("ifade ownset")

    def test_bos_ifade_elenir(self):
        assert not self._v("")
        assert not self._v("   ")

    def test_cok_kisa_kelime_dizisi_elenir(self):
        assert not self._v("ab cd ef gh")


class TestKaynakSecimSirasi:
    """Tur bütçesi önce güvenilir alan adlarına harcanmalıdır."""

    @staticmethod
    def _kos(ham, limit=None):
        import asyncio

        import verified_research as vr

        class Sessiz:
            async def send_json(self, _d):
                pass

        eski = vr.SEARCH_MAX_SOURCES_PER_ROUND
        if limit is not None:
            vr.SEARCH_MAX_SOURCES_PER_ROUND = limit
        try:
            arastirmaci = vr.VerifiedDeepResearcher("m", "Ollama", Sessiz())
            arastirmaci._search_sync = lambda *a, **k: ham
            secilen = asyncio.run(arastirmaci.search_round(["sorgu"], "moderate"))
        finally:
            vr.SEARCH_MAX_SOURCES_PER_ROUND = eski
        return [s["domain"] for s in secilen]

    def test_guvenilir_alan_adi_one_gecer(self):
        ham = [
            {"url": "https://seo-ciftligi.example/1"},
            {"url": "https://baska-spam.example/2"},
            {"url": "https://arxiv.org/abs/2501.00001"},
        ]
        assert self._kos(ham)[0] == "arxiv.org"

    def test_butce_dolunca_dusuk_kaliteli_kaynak_disarida_kalir(self):
        ham = [
            {"url": "https://seo-ciftligi.example/1"},
            {"url": "https://reddit.com/r/x"},
            {"url": "https://www.reuters.com/haber"},
        ]
        secilen = self._kos(ham, limit=1)
        assert secilen == ["reuters.com"]

    def test_ayni_oncelde_arama_sirasi_korunur(self):
        ham = [
            {"url": "https://bilinmeyen-bir.example/1"},
            {"url": "https://bilinmeyen-iki.example/2"},
        ]
        assert self._kos(ham) == ["bilinmeyen-bir.example", "bilinmeyen-iki.example"]

    def test_tekrarlanan_url_bir_kez_alinir(self):
        ham = [
            {"url": "https://arxiv.org/abs/1#bolum"},
            {"url": "https://arxiv.org/abs/1/"},
        ]
        assert len(self._kos(ham)) == 1

    def test_domain_basina_limit_korunur(self):
        ham = [{"url": f"https://arxiv.org/abs/{i}"} for i in range(5)]
        # SEARCH_MAX_PER_DOMAIN kadar alınır, fazlası elenir
        from research_constants import SEARCH_MAX_PER_DOMAIN

        assert len(self._kos(ham)) == SEARCH_MAX_PER_DOMAIN


class TestAsBool:
    def test_real_bools(self):
        assert as_bool(True) is True
        assert as_bool(False) is False

    def test_string_false_variants(self):
        for v in ("false", "False", "hayır", "hayir", "no", "0", ""):
            assert as_bool(v, default=True) is False, v

    def test_string_true_variants(self):
        for v in ("true", "True", "evet", "yes", "1"):
            assert as_bool(v, default=False) is True, v

    def test_unknown_uses_default(self):
        assert as_bool("belki", default=False) is False
        assert as_bool(None, default=True) is True
        assert as_bool({}, default=False) is False


class TestPrivateTargetGuard:
    def test_blocks_private(self):
        for url in (
            "http://localhost:8001/x",
            "http://127.0.0.1/x",
            "https://192.168.1.10/a",
            "http://10.0.0.5/",
            "http://172.16.3.2/x",
            "http://[::1]/x",
            "http://printer.local/x",
        ):
            assert VerifiedDeepResearcher._is_private_target(url) is True, url

    def test_allows_public(self):
        assert VerifiedDeepResearcher._is_private_target("https://example.com/a") is False
        assert VerifiedDeepResearcher._is_private_target("https://172.201.5.5/x") is False


class TestMdSafe:
    def test_strips_pipes_and_newlines(self):
        assert "|" not in VerifiedDeepResearcher._md_safe("a | b\nc")

    def test_replaces_brackets(self):
        out = VerifiedDeepResearcher._md_safe("[Breaking] news")
        assert "[" not in out and "]" not in out


def _src(reliability=0.8, freshness=1.0, domain="a.com"):
    return {"reliability": reliability, "freshness": freshness, "domain": domain}


class TestClaimConfidence:
    def test_no_support_zero(self):
        assert compute_claim_confidence([], [], False) == 0

    def test_single_source_capped(self):
        score = compute_claim_confidence([_src(reliability=1.0)], [], False)
        assert score <= int(CONFIDENCE_SINGLE_SOURCE_CAP * 100)

    def test_more_independent_sources_increase_confidence(self):
        one = compute_claim_confidence([_src(domain="a.com")], [], False)
        two = compute_claim_confidence(
            [_src(domain="a.com"), _src(domain="b.com")], [], False
        )
        three = compute_claim_confidence(
            [_src(domain="a.com"), _src(domain="b.com"), _src(domain="c.com")], [], False
        )
        assert one < two < three

    def test_same_domain_counts_once(self):
        one = compute_claim_confidence([_src(domain="a.com")], [], False)
        dup = compute_claim_confidence(
            [_src(domain="a.com"), _src(domain="a.com")], [], False
        )
        assert dup == one

    def test_stale_source_hurts_time_sensitive_claim(self):
        fresh = compute_claim_confidence([_src(freshness=1.0)], [], True)
        stale = compute_claim_confidence([_src(freshness=0.05)], [], True)
        assert stale < fresh

    def test_freshness_ignored_for_timeless_claim(self):
        fresh = compute_claim_confidence([_src(freshness=1.0)], [], False)
        stale = compute_claim_confidence([_src(freshness=0.05)], [], False)
        assert fresh == stale

    def test_stronger_contradiction_caps_score(self):
        # Destek: eski/zayıf; çelişki: yeni/güçlü → tavan uygulanır
        score = compute_claim_confidence(
            [_src(reliability=0.5, freshness=0.2)],
            [_src(reliability=0.9, freshness=1.0, domain="c.com")],
            True,
        )
        assert score <= int(CONFIDENCE_CONTRADICTED_CAP * 100)

    def test_weak_contradiction_small_penalty(self):
        base = compute_claim_confidence(
            [_src(reliability=0.9, freshness=1.0)], [], True
        )
        contra = compute_claim_confidence(
            [_src(reliability=0.9, freshness=1.0)],
            [_src(reliability=0.2, freshness=0.1, domain="c.com")],
            True,
        )
        assert base - 20 < contra < base

    def test_score_bounds(self):
        low = compute_claim_confidence(
            [_src(reliability=0.01, freshness=0.01)],
            [_src(reliability=0.99, freshness=1.0, domain="x.com")],
            True,
        )
        high = compute_claim_confidence(
            [_src(reliability=0.99, domain=f"d{i}.com") for i in range(10)], [], False
        )
        assert 2 <= low <= 99
        assert 2 <= high <= 99


class TestConfidenceLabel:
    def test_labels_tr(self):
        assert confidence_label(90) == "yüksek güven"
        assert confidence_label(70) == "orta güven"
        assert confidence_label(30) == "düşük güven"

    def test_labels_en(self):
        assert confidence_label(90, "en") == "high confidence"
        assert confidence_label(30, "en") == "low confidence"
