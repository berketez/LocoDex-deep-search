"""
LocoDex Deep Search — Merkezi Sabitler

Bu dosya, projedeki birden fazla pipeline tarafından kullanılan sayısal
sabitleri tek bir yerde toplar. Aynı kavramın farklı dosyalarda farklı
değer almasını önlemek için tüm pipeline'lar bu dosyadan import etmelidir.

Önemli not: Geçmişte iki paralel pipeline farklı ölçeklerde
(0–100 vs 1–10) güvenilirlik eşiği tanımlıyordu. Tek normalize ölçek
(0–1) altında birleştirildi. Pipeline kendi ham ölçeğine bu sabitten
türevlenir.
"""

# === GÜVENİLİRLİK EŞİĞİ ===
# Kaynak güvenilirlik skoru için normalize edilmiş eşik (0-1 ölçeği).
# Bu, kaynakların filtrelenmesi için kullanılan tek doğru kaynaktır.
RELIABILITY_THRESHOLD_NORMALIZED = 0.30  # eski real_deep_research.py:788 = 30/100 ile uyumlu

# Pipeline-spesifik ham eşikler (RELIABILITY_THRESHOLD_NORMALIZED'dan türevlenmiş):
RELIABILITY_THRESHOLD_100 = int(round(RELIABILITY_THRESHOLD_NORMALIZED * 100))  # 30
RELIABILITY_THRESHOLD_10 = int(round(RELIABILITY_THRESHOLD_NORMALIZED * 10))    # 3 (eskiden 6 idi — değiştirildi)

# DİKKAT: smart_multilingual_research.py daha önce score >= 6 kullanıyordu
# (yani normalize 0.60). Tek normalize ölçek altında 0.30'a indirildi
# (mevcut "real_deep_research" eşiğiyle birleşti). Eğer "smart_multilingual"
# için daha sıkı bir filtre isteniyorsa, RELIABILITY_THRESHOLD_NORMALIZED
# değerini yukarıda değiştirmek yeterlidir; her iki pipeline da uyumlu kalır.

# === RETRY/BACKOFF AYARLARI ===
# tenacity.wait_exponential parametreleri
RETRY_MAX_ATTEMPTS = 3
RETRY_WAIT_MULTIPLIER = 1
RETRY_WAIT_MIN_SEC = 4
RETRY_WAIT_MAX_SEC = 15
# Not: multiplier=1 ile gerçek bekleme = 4 + 4 = 8 s (min floor üstel artışı boğar).
# Daha agresif backoff için multiplier=4 kullanılmalı.

# === LLM PARAMETRELERİ ===
LLM_TIMEOUT_SEC = 600        # LiteLLM (10 dakika)
LLM_HEALTH_TIMEOUT_SEC = 2   # /health probe
TEMPERATURE_PRECISE = 0.0    # llms.py
TEMPERATURE_RESEARCH = 0.3   # real_deep_research.py
TEMPERATURE_BALANCED = 0.7   # server.py (orta yaratıcılık)

# === BM25 (kullanılırsa) ===
BM25_K1 = 1.2
BM25_B = 0.75

# ============================================================
# VERIFIED RESEARCH PIPELINE SABİTLERİ (verified_research.py)
# ============================================================

# === ARAMA AYARLARI ===
SEARCH_MAX_QUERIES_PER_ROUND = 6      # Tur başına en fazla sorgu
SEARCH_RESULTS_PER_QUERY = 6          # Sorgu başına ham sonuç
SEARCH_MAX_SOURCES_PER_ROUND = 14     # Tur başına incelenecek en fazla kaynak
SEARCH_MAX_PER_DOMAIN = 2             # Aynı domain'den en fazla kaynak (çeşitlilik)
SEARCH_FETCH_CONCURRENCY = 5          # Paralel sayfa indirme limiti
SEARCH_FETCH_TIMEOUT_SEC = 15         # Sayfa indirme zaman aşımı
SEARCH_FETCH_MAX_BYTES = 3_000_000    # Sayfa başına indirilecek en fazla bayt
SEARCH_CONTENT_MAX_CHARS = 6000       # Kaynak başına analiz edilecek metin uzunluğu

# === LLM DAYANIKLILIK ===
LLM_MAX_CONSECUTIVE_FAILURES = 3      # Üst üste bu kadar LLM hatasında araştırma durur

# === İTERASYON (gerçek araştırma döngüsü) ===
RESEARCH_MAX_ROUNDS = 3               # 1 ana tur + en fazla 2 boşluk-kapatma turu
RESEARCH_MIN_SOURCES_FOR_REPORT = 3   # Bundan az güvenilir kaynakla rapor yazma, tur ekle

# === TAZELİK (freshness) YARI ÖMÜRLERİ (gün) ===
# Konu zaman duyarlılığına göre üstel bozunum: freshness = exp(-yaş / yarı_ömür)
FRESHNESS_HALF_LIFE_DAYS = {
    "critical": 180,    # AI modelleri, fiyatlar, sürümler, güncel haberler
    "moderate": 730,    # framework'ler, şirket bilgileri, istatistikler
    "low": 100000,      # tarih, matematik, temel bilim — fiilen bozunmaz
}
FRESHNESS_UNKNOWN_DATE = 0.5          # Tarihi saptanamayan kaynak için varsayılan tazelik
FRESHNESS_STALE_WARNING_DAYS = {      # Rapora "bilgi eski olabilir" uyarısı eşiği
    "critical": 120,
    "moderate": 540,
    "low": 100000,
}

# === KAYNAK GÜVENİLİRLİK ÖNCELLERİ (domain prior, 0-1) ===
DOMAIN_PRIOR_HIGH = 0.90
DOMAIN_PRIOR_MEDIUM = 0.65
DOMAIN_PRIOR_LOW = 0.40
DOMAIN_PRIOR_UNKNOWN = 0.50
DOMAIN_PRIOR_UNTRUSTED = 0.10

# Güvenilir kaynak listeleri (real_deep_research.py'den merkezileştirildi)
TRUSTED_DOMAINS = {
    "high": [
        "arxiv.org", "nature.com", "science.org", "pubmed.ncbi.nlm.nih.gov",
        "ieee.org", "acm.org", "academic.oup.com", "springer.com",
        "cambridge.org", "mit.edu", "stanford.edu", "harvard.edu",
        "openai.com", "deepmind.com", "anthropic.com", "microsoft.com",
        "google.com", "apple.com", "nvidia.com", "meta.com",
        "reuters.com", "apnews.com", "bbc.com", "bloomberg.com",
        "nytimes.com", "wsj.com", "ft.com", "economist.com",
        "github.com", "stackoverflow.com",
        "huggingface.co", "kaggle.com", "paperswithcode.com",
        "who.int", "cdc.gov", "nasa.gov", "fda.gov", "sec.gov", "europa.eu",
        "tuik.gov.tr", "tcmb.gov.tr", "resmigazete.gov.tr",
    ],
    "medium": [
        "wikipedia.org", "techcrunch.com", "arstechnica.com", "wired.com",
        "theverge.com", "zdnet.com", "cnn.com", "engadget.com",
        "venturebeat.com", "forbes.com", "businessinsider.com",
        "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
        "blog.google", "engineering.fb.com", "blogs.microsoft.com",
        "aa.com.tr", "trthaber.com", "ntv.com.tr", "hurriyet.com.tr",
        "sozcu.com.tr", "cnnturk.com", "haberturk.com", "dunya.com",
        "webtekno.com", "shiftdelete.net", "donanimhaber.com",
    ],
    "low": [
        "reddit.com", "quora.com", "medium.com", "substack.com",
        "wordpress.com", "blogspot.com", "tumblr.com",
        "yahoo.com", "answers.com", "ehow.com", "pinterest.com",
    ],
}
UNTRUSTED_DOMAIN_PATTERNS = [
    "clickbait", "affiliate", "coupon", "promo-", "-promo",
]

# === GÜVEN SKORU (claim confidence) AĞIRLIKLARI ===
# source_reliability = W_DOMAIN * domain_prior + W_LLM * llm_skoru(0-1)
CONFIDENCE_W_DOMAIN = 0.6
CONFIDENCE_W_LLM = 0.4
# İddia taban güveni: 1 - Π(1 - reliability_i * CONFIDENCE_SINGLE_SOURCE_CAP)
# (tek kaynak asla %90'ın üzerine çıkamaz; bağımsız kaynak sayısı arttıkça yükselir)
CONFIDENCE_SINGLE_SOURCE_CAP = 0.80
# Zaman duyarlı iddialarda tazelik çarpanı: (FLOOR + (1-FLOOR) * tazelik)
CONFIDENCE_FRESHNESS_FLOOR = 0.6
# Çelişki cezaları
CONFIDENCE_CONTRADICTION_PENALTY = 0.15   # Zayıf kaynak çelişiyorsa düşülecek pay
CONFIDENCE_CONTRADICTED_CAP = 0.40        # Daha güçlü/güncel kaynak çelişiyorsa tavan
# Rapor etiket eşikleri (0-100)
CONFIDENCE_LABEL_HIGH = 85     # "yüksek güven"
CONFIDENCE_LABEL_MEDIUM = 60   # "orta güven"; altı "düşük güven"

# === İDDİA ÇIKARIMI ===
CLAIMS_PER_SOURCE = 4          # Kaynak başına en fazla iddia
CLAIMS_MAX_TOTAL = 48          # Konsolidasyona girecek en fazla toplam iddia
