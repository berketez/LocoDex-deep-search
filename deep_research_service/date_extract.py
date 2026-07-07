"""
LocoDex Deep Search — Deterministik Yayın Tarihi Çıkarımı ve Tazelik Skoru

Yayın tarihi sayfanın kendisinden deterministik olarak çıkarılır; LLM
tahminine bırakılmaz. Böylece eski içerik güncel içerikle aynı ağırlıkta
değerlendirilmez ve rapor tarih bilgisiyle birlikte sunulur.

Çıkarım öncelik sırası (güven yüksekten düşüğe):
1. JSON-LD  → datePublished / dateModified   (schema.org, haber siteleri)
2. Meta tag → article:published_time, og:updated_time, name="date" vb.
3. <time datetime="..."> etiketi
4. URL deseni → /2026/07/… veya /2026-07-05-…
5. Görünür metindeki tarih ifadeleri (İngilizce + Türkçe ay adları, ISO)

Dönen sonuç: (datetime | None, yöntem_adı, güven [0-1])
"""

import re
from datetime import datetime, timezone
import json as _json

try:
    from research_constants import (
        FRESHNESS_HALF_LIFE_DAYS,
        FRESHNESS_UNKNOWN_DATE,
    )
except ImportError:
    from .research_constants import (
        FRESHNESS_HALF_LIFE_DAYS,
        FRESHNESS_UNKNOWN_DATE,
    )

import math

# Ay adı → ay numarası (İngilizce tam/kısa + Türkçe)
_MONTHS = {
    "january": 1, "jan": 1, "ocak": 1,
    "february": 2, "feb": 2, "şubat": 2, "subat": 2,
    "march": 3, "mar": 3, "mart": 3,
    "april": 4, "apr": 4, "nisan": 4,
    "may": 5, "mayıs": 5, "mayis": 5,
    "june": 6, "jun": 6, "haziran": 6,
    "july": 7, "jul": 7, "temmuz": 7,
    "august": 8, "aug": 8, "ağustos": 8, "agustos": 8,
    "september": 9, "sep": 9, "sept": 9, "eylül": 9, "eylul": 9,
    "october": 10, "oct": 10, "ekim": 10,
    "november": 11, "nov": 11, "kasım": 11, "kasim": 11,
    "december": 12, "dec": 12, "aralık": 12, "aralik": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS.keys(), key=len, reverse=True))

# "5 Temmuz 2026", "July 5, 2026", "5 July 2026"
_TEXT_DATE_RE = re.compile(
    r"\b(?:(\d{1,2})\s+(" + _MONTH_ALT + r")\s+(\d{4})"          # 5 Temmuz 2026
    r"|(" + _MONTH_ALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}))\b",  # July 5, 2026
    re.IGNORECASE,
)
# ISO benzeri: 2026-07-05 (metin içinde)
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])\b")
# URL: /2026/07/ veya /2026-07-05. Ay iki haneli zorunlu; tek haneli
# segmentler (kategori ID'si, sayfa numarası) tarih sanılmasın diye.
_URL_DATE_RE = re.compile(r"/(20\d{2})[/-](0[1-9]|1[0-2])(?:[/-]([0-2]\d|3[01]|[1-9]))?(?:[/-]|$)")

_META_DATE_KEYS = [
    # (attr_adı, attr_değeri) çiftleri — öncelik sırasıyla
    ("property", "article:published_time"),
    ("property", "og:article:published_time"),
    ("property", "article:modified_time"),
    ("property", "og:updated_time"),
    ("itemprop", "datePublished"),
    ("itemprop", "dateModified"),
    ("name", "date"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("name", "publish-date"),
    ("name", "publish_date"),
    ("name", "article.published"),
    ("name", "parsely-pub-date"),
    ("name", "sailthru.date"),
    ("name", "dc.date"),
    ("name", "dc.date.issued"),
    ("name", "dcterms.date"),
    ("name", "last-modified"),
]


def _month_lookup(name):
    """
    Ay adını numaraya çevirir. Türkçe büyük İ, Python .lower() ile
    'i' + U+0307 (birleşik nokta) üretir; sözlük anahtarıyla eşleşsin
    diye birleşik nokta atılır ve I → ı dönüşümü denenir.
    """
    if not name:
        return None
    lowered = name.lower().replace("̇", "")  # İ → i + birleşik nokta; noktayı at
    month = _MONTHS.get(lowered)
    if month:
        return month
    return _MONTHS.get(name.replace("I", "ı").lower().replace("̇", ""))


def _parse_datetime_string(value):
    """ISO ve yaygın tarih string'lerini datetime'a çevirir; olmazsa None."""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None

    # ISO 8601 (Z son eki dahil). Saat dilimli tarihler yerel saate
    # çevrilip naive yapılır; karşılaştırmalar naive-yerel datetime.now()
    # ile yapıldığı için ölçekler tutarlı kalır.
    iso_candidate = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        return dt if dt.tzinfo is None else dt.astimezone().replace(tzinfo=None)
    except ValueError:
        pass

    # Kısaltılmış ISO: 2026-07-05
    m = _ISO_DATE_RE.search(value)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # RFC 2822 benzeri: "Tue, 05 Jul 2026 10:30:00 GMT"
    m = re.search(
        r"(\d{1,2})\s+(" + _MONTH_ALT + r")\s+(\d{4})", value, re.IGNORECASE
    )
    if m:
        month = _month_lookup(m.group(2))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                return None

    # "July 5, 2026"
    m = re.search(
        r"(" + _MONTH_ALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})",
        value, re.IGNORECASE,
    )
    if m:
        month = _month_lookup(m.group(1))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None

    # 05.07.2026 / 05/07/2026 — ayraç tutarlı olmalı (3.5/2026 gibi
    # sürüm+yıl karışımları elensin). Gün/ay sırası belirsizliği:
    # noktalı biçim Avrupa/TR kullanımıdır, gün-önce okunur; eğik çizgili
    # biçim yalnızca hangi alanın >12 olduğu belliyse kabul edilir.
    m = re.search(r"\b(\d{1,2})([./])(\d{1,2})\2(20\d{2})\b", value)
    if m:
        first, sep, second, year = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        day = month = None
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            day, month = second, first
        elif sep == "." and first <= 31 and second <= 12:
            day, month = first, second  # Noktalı yazımda TR/EU: gün.ay.yıl
        if day and month:
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        return None

    return None


def _sanity_check(dt, now=None, min_year=2000):
    """
    Mantıksız YAYIN tarihlerini eler (gelecek tarihler ve min_year öncesi).

    min_year varsayılanı 2000: içerikte anlatılan tarihsel tarihlerin
    (örn. "5 Temmuz 1923") yayın tarihi sanılmasını önler. Yapılandırılmış
    kaynaklar (JSON-LD, meta) bu karışıklığı yaşamadığı için 1995'e kadar
    kabul edilir. Bu filtre içeriğin KONUSU olan tarihleri etkilemez;
    yalnızca sayfanın yayın tarihi tespitine uygulanır.
    """
    if dt is None:
        return None
    now = now or datetime.now()
    if dt.year < min_year:
        return None
    # Saat dilimi kaymalarına 2 gün tolerans
    if (dt - now).total_seconds() > 2 * 86400:
        return None
    return dt


def _from_json_ld(soup, now):
    """JSON-LD bloklarından datePublished/dateModified çeker."""
    best = None
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = _json.loads(raw)
        except (ValueError, TypeError):
            continue
        # Tek nesne, liste veya @graph olabilir
        nodes = data if isinstance(data, list) else [data]
        expanded = []
        for node in nodes:
            if isinstance(node, dict):
                expanded.append(node)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    expanded.extend(n for n in graph if isinstance(n, dict))
        for node in expanded:
            for key in ("datePublished", "dateModified", "dateCreated", "uploadDate"):
                dt = _sanity_check(_parse_datetime_string(node.get(key)), now, min_year=1995)
                if dt and (best is None or key == "datePublished"):
                    best = dt
                    if key == "datePublished":
                        return best
    return best


def _from_meta_tags(soup, now):
    for attr, value in _META_DATE_KEYS:
        tag = soup.find("meta", attrs={attr: value})
        if tag:
            dt = _sanity_check(_parse_datetime_string(tag.get("content")), now, min_year=1995)
            if dt:
                return dt
    return None


def _from_time_tag(soup, now):
    for tag in soup.find_all("time"):
        dt = _sanity_check(
            _parse_datetime_string(tag.get("datetime") or tag.get_text(" ", strip=True)),
            now,
        )
        if dt:
            return dt
    return None


def _from_url(url, now):
    if not url:
        return None
    m = _URL_DATE_RE.search(url)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    day = int(m.group(3)) if m.group(3) else 15  # Gün yoksa ay ortası varsay
    try:
        return _sanity_check(datetime(year, month, day), now)
    except ValueError:
        return None


def _from_visible_text(text, now):
    """
    Sayfa metninin başındaki tarih ifadelerini arar (ilk 2500 karakter).
    İlk eşleşme geçersizse (gelecek tarih, tarihsel içerik tarihi) sonraki
    eşleşmeler de denenir.
    """
    if not text:
        return None
    head = text[:2500]

    for m in list(_ISO_DATE_RE.finditer(head))[:5]:
        try:
            dt = _sanity_check(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))), now)
            if dt:
                return dt
        except ValueError:
            continue

    for m in list(_TEXT_DATE_RE.finditer(head))[:5]:
        if m.group(1):  # "5 Temmuz 2026" biçimi
            day, month_name, year = m.group(1), m.group(2), m.group(3)
        else:           # "July 5, 2026" biçimi
            month_name, day, year = m.group(4), m.group(5), m.group(6)
        month = _month_lookup(month_name)
        if not month:
            continue
        try:
            dt = _sanity_check(datetime(int(year), month, int(day)), now)
            if dt:
                return dt
        except ValueError:
            continue
    return None


def extract_publication_date(html_soup=None, url="", visible_text="", now=None):
    """
    Yayın tarihini deterministik çıkarır.

    html_soup: BeautifulSoup nesnesi (None olabilir)
    url: kaynak URL'si
    visible_text: temizlenmiş sayfa metni
    Döner: (datetime | None, yöntem, güven)
    """
    now = now or datetime.now()

    if html_soup is not None:
        dt = _from_json_ld(html_soup, now)
        if dt:
            return dt, "json-ld", 0.95
        dt = _from_meta_tags(html_soup, now)
        if dt:
            return dt, "meta-tag", 0.90
        dt = _from_time_tag(html_soup, now)
        if dt:
            return dt, "time-etiketi", 0.80

    dt = _from_url(url, now)
    if dt:
        return dt, "url-deseni", 0.70

    dt = _from_visible_text(visible_text, now)
    if dt:
        return dt, "metin", 0.50

    return None, "bulunamadı", 0.0


def freshness_score(published_at, time_sensitivity, now=None):
    """
    Tazelik skoru [0-1]. Üstel bozunum: exp(-ln2 * yaş_gün / yarı_ömür).

    time_sensitivity: "critical" | "moderate" | "low"
    published_at None ise FRESHNESS_UNKNOWN_DATE döner (tarih doğrulanamadı).
    """
    if published_at is None:
        return FRESHNESS_UNKNOWN_DATE
    now = now or datetime.now()
    half_life = FRESHNESS_HALF_LIFE_DAYS.get(time_sensitivity, FRESHNESS_HALF_LIFE_DAYS["moderate"])
    age_days = max(0.0, (now - published_at).total_seconds() / 86400.0)
    return math.exp(-math.log(2) * age_days / half_life)
