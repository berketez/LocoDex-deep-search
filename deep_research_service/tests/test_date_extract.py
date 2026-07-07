"""date_extract modülü birim testleri — ağ ve LLM gerektirmez."""

import math
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from date_extract import (
    extract_publication_date,
    freshness_score,
    _parse_datetime_string,
)

NOW = datetime(2026, 7, 7, 12, 0, 0)


def _soup(html):
    return BeautifulSoup(html, "html.parser")


class TestParseDatetimeString:
    def test_iso_with_z(self):
        # Aware tarihler yerel saate çevrilip naive yapılır (now() ile tutarlı)
        from datetime import timezone
        expected = (
            datetime(2026, 5, 14, 10, 30, tzinfo=timezone.utc)
            .astimezone()
            .replace(tzinfo=None)
        )
        assert _parse_datetime_string("2026-05-14T10:30:00Z") == expected

    def test_iso_date_only(self):
        assert _parse_datetime_string("2026-05-14") == datetime(2026, 5, 14)

    def test_rfc_like(self):
        assert _parse_datetime_string("Tue, 05 May 2026 10:30:00 GMT") == datetime(2026, 5, 5)

    def test_english_month_day_year(self):
        assert _parse_datetime_string("July 5, 2026") == datetime(2026, 7, 5)

    def test_turkish_date(self):
        assert _parse_datetime_string("5 Temmuz 2026") == datetime(2026, 7, 5)

    def test_dotted_turkish_format(self):
        assert _parse_datetime_string("05.03.2026") == datetime(2026, 3, 5)

    def test_turkish_uppercase_month(self):
        # Türkçe büyük İ .lower() ile 'i' + U+0307 üretir; ay yine bulunmalı
        assert _parse_datetime_string("12 NİSAN 2026") == datetime(2026, 4, 12)
        assert _parse_datetime_string("3 EKİM 2025") == datetime(2025, 10, 3)
        assert _parse_datetime_string("1 HAZİRAN 2026") == datetime(2026, 6, 1)

    def test_slash_unambiguous_day_first(self):
        assert _parse_datetime_string("25/03/2026") == datetime(2026, 3, 25)

    def test_slash_unambiguous_month_first(self):
        # ABD biçimi: ay/gün/yıl — ikinci alan >12 ise ay öncedir
        assert _parse_datetime_string("03/25/2026") == datetime(2026, 3, 25)

    def test_slash_ambiguous_rejected(self):
        # 05/03/2026 hem 5 Mart hem 3 Mayıs olabilir; yanlış tarih üretme
        assert _parse_datetime_string("05/03/2026") is None

    def test_mixed_separators_rejected(self):
        # "Sürüm 3.5/2026" gibi sürüm+yıl karışımları tarih değildir
        assert _parse_datetime_string("Sürüm 3.5/2026") is None

    def test_garbage_returns_none(self):
        assert _parse_datetime_string("hiç tarih yok burada") is None
        assert _parse_datetime_string("") is None
        assert _parse_datetime_string(None) is None


class TestExtractPublicationDate:
    def test_json_ld_date_published(self):
        html = """<html><head><script type="application/ld+json">
        {"@type": "NewsArticle", "datePublished": "2026-06-01T08:00:00Z"}
        </script></head><body>metin</body></html>"""
        dt, method, conf = extract_publication_date(_soup(html), now=NOW)
        assert dt is not None and dt.date() == datetime(2026, 6, 1).date()
        assert method == "json-ld"
        assert conf > 0.9

    def test_json_ld_graph(self):
        html = """<script type="application/ld+json">
        {"@graph": [{"@type": "WebPage"}, {"@type": "Article", "datePublished": "2026-04-10"}]}
        </script>"""
        dt, method, _ = extract_publication_date(_soup(html), now=NOW)
        assert dt == datetime(2026, 4, 10)
        assert method == "json-ld"

    def test_meta_article_published_time(self):
        html = '<meta property="article:published_time" content="2026-03-15T09:00:00+03:00">'
        dt, method, _ = extract_publication_date(_soup(html), now=NOW)
        assert dt is not None and dt.date() == datetime(2026, 3, 15).date()
        assert method == "meta-tag"

    def test_time_tag(self):
        html = '<time datetime="2026-02-20">20 Şubat 2026</time>'
        dt, method, _ = extract_publication_date(_soup(html), now=NOW)
        assert dt == datetime(2026, 2, 20)
        assert method == "time-etiketi"

    def test_url_pattern(self):
        dt, method, _ = extract_publication_date(
            None, url="https://example.com/2026/05/some-news-story", now=NOW
        )
        assert dt is not None and (dt.year, dt.month) == (2026, 5)
        assert method == "url-deseni"

    def test_url_pattern_with_day(self):
        dt, _, _ = extract_publication_date(
            None, url="https://example.com/2026/05/14/story", now=NOW
        )
        assert dt == datetime(2026, 5, 14)

    def test_url_single_digit_month_rejected(self):
        # /2024/1/ gibi segmentler çoğunlukla kategori/sayfa ID'sidir
        dt, _, _ = extract_publication_date(
            None, url="https://example.com/products/2024/1/", now=NOW
        )
        assert dt is None

    def test_visible_text_second_match_used(self):
        # İlk eşleşme (tarihsel içerik tarihi) elenirse sonraki denenmeli
        dt, _, _ = extract_publication_date(
            None,
            visible_text="24 Temmuz 1923 imzalandı. Yayın: 5 Mart 2026 tarihinde.",
            now=NOW,
        )
        assert dt == datetime(2026, 3, 5)

    def test_visible_text_turkish(self):
        dt, method, _ = extract_publication_date(
            None, visible_text="Yayınlanma: 3 Nisan 2026 Bu haberde...", now=NOW
        )
        assert dt == datetime(2026, 4, 3)
        assert method == "metin"

    def test_visible_text_english(self):
        dt, _, _ = extract_publication_date(
            None, visible_text="Published on January 12, 2026 by staff", now=NOW
        )
        assert dt == datetime(2026, 1, 12)

    def test_future_date_rejected(self):
        html = '<meta property="article:published_time" content="2027-01-01">'
        dt, method, conf = extract_publication_date(_soup(html), now=NOW)
        assert dt is None
        assert method == "bulunamadı"
        assert conf == 0.0

    def test_ancient_date_rejected(self):
        dt, _, _ = extract_publication_date(
            None, visible_text="Copyright 1997-05-01 metni", now=NOW
        )
        assert dt is None

    def test_historical_content_date_not_publication_date(self):
        # Tarihsel içerikteki tarih, yayın tarihi sanılmamalı
        dt, method, _ = extract_publication_date(
            None,
            visible_text="Lozan Antlaşması 24 Temmuz 1923 tarihinde imzalandı.",
            now=NOW,
        )
        assert dt is None
        assert method == "bulunamadı"

    def test_structured_source_accepts_90s_page(self):
        # Yapılandırılmış kaynaklarda (meta/JSON-LD) 1995 sonrası kabul edilir
        html = '<meta property="article:published_time" content="1997-08-14">'
        dt, method, _ = extract_publication_date(_soup(html), now=NOW)
        assert dt == datetime(1997, 8, 14)
        assert method == "meta-tag"

    def test_priority_json_ld_over_meta(self):
        html = """
        <script type="application/ld+json">{"datePublished": "2026-06-01"}</script>
        <meta property="article:published_time" content="2026-01-01">
        """
        dt, method, _ = extract_publication_date(_soup(html), now=NOW)
        assert dt == datetime(2026, 6, 1)
        assert method == "json-ld"

    def test_nothing_found(self):
        dt, method, conf = extract_publication_date(
            _soup("<p>tarihsiz içerik</p>"), url="https://example.com/page", now=NOW
        )
        assert dt is None and method == "bulunamadı" and conf == 0.0


class TestFreshnessScore:
    def test_fresh_critical(self):
        recent = datetime(2026, 7, 1)
        assert freshness_score(recent, "critical", now=NOW) > 0.95

    def test_old_critical_decays(self):
        old = datetime(2025, 7, 7)  # ~1 yıl önce, yarı ömür 180 gün
        age_days = (NOW - old).total_seconds() / 86400.0
        score = freshness_score(old, "critical", now=NOW)
        assert score == pytest.approx(math.exp(-math.log(2) * age_days / 180), rel=1e-6)
        assert score < 0.3

    def test_old_low_sensitivity_stays_high(self):
        old = datetime(2020, 1, 1)
        assert freshness_score(old, "low", now=NOW) > 0.98

    def test_unknown_date_default(self):
        assert freshness_score(None, "critical", now=NOW) == 0.5

    def test_half_life_exact(self):
        half = datetime(2026, 1, 8)  # ~180 gün önce
        score = freshness_score(half, "critical", now=NOW)
        assert score == pytest.approx(0.5, abs=0.01)
