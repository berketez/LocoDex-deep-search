"""
LocoDex Deep Search — Oturum Hafızası ve Takip Sorusu Katmanı

Bir araştırma bittiğinde bulgular, kaynaklar ve rapor oturumda tutulur. Sonraki
istek geldiğinde aynı araştırma baştan koşturulmaz; istek önce sınıflandırılır:

  takip        — mevcut bulgularla cevaplanabilir, arama yapılmaz
  derinlestir  — aynı konunun eksik kalan yönü, hedefli yeni tur koşulur
  yeni         — ilgisiz konu, tam araştırma

Sınıflandırma modele yaptırılır; model yanıt veremezse kelime örtüşmesine
dayanan yedek karar devreye girer. Takip cevabı yalnızca kayıtlı bulgulara
dayanır — model yeni bilgi uyduramaz, bilgi yetersizse bunu söyler.
"""

import logging
import re
from datetime import datetime

try:
    from llm_client import LocalLLMClient, LLMError
    from research_constants import LLM_JSON_TOKENS_SMALL, LLM_TEXT_TOKENS_ANSWER
except ImportError:
    from .llm_client import LocalLLMClient, LLMError
    from .research_constants import LLM_JSON_TOKENS_SMALL, LLM_TEXT_TOKENS_ANSWER

logger = logging.getLogger(__name__)

# Takip cevabında modele verilecek en fazla bulgu/kaynak sayısı
CONTEXT_MAX_FINDINGS = 20
CONTEXT_MAX_SOURCES = 20
# Konu örtüşmesi bu oranın üstündeyse yeni araştırma yerine aynı kayıt kullanılır
TOPIC_OVERLAP_THRESHOLD = 0.60
# Kısa takip sorularında sorgu kelimelerinin konuda geçme oranı eşiği
CONTAINMENT_THRESHOLD = 0.40

_STOPWORDS = {
    "ve", "ile", "için", "icin", "bir", "bu", "da", "de", "mi", "mu", "ne",
    "nedir", "nasıl", "nasil", "hangi", "kaç", "kac", "the", "and", "for",
    "of", "in", "on", "to", "a", "is", "are", "what", "how",
}


def _tokens(text):
    words = re.findall(r"\w+", (text or "").lower(), re.UNICODE)
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def topic_overlap(a, b):
    """İki konu arasındaki kelime örtüşme oranı (0-1, Jaccard)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def topic_containment(query, topic):
    """
    Sorgudaki kelimelerin ne kadarının konu içinde geçtiği (0-1).

    Jaccard, uzunluk farkını cezalandırdığı için kısa takip sorularını
    ("kalite kontrol kısmını açıkla") ilgisiz gösteriyordu; kapsama ölçütü
    bu durumda doğru sinyali verir.
    """
    tq, tt = _tokens(query), _tokens(topic)
    if not tq or not tt:
        return 0.0
    return len(tq & tt) / len(tq)


class ResearchEntry:
    """Tamamlanmış tek bir araştırmanın oturumdaki kaydı."""

    def __init__(self, topic, report, findings, sources, report_path, duration_sec):
        self.topic = topic
        self.report = report
        self.findings = findings or []
        self.sources = sources or []
        self.report_path = report_path
        self.duration_sec = duration_sec
        self.created_at = datetime.now()
        self.followups = []  # [(soru, cevap)]

    def overall_confidence(self):
        if not self.findings:
            return 0
        return int(round(sum(f["confidence"] for f in self.findings) / len(self.findings)))

    def top_findings(self, limit=3):
        return sorted(self.findings, key=lambda f: -f["confidence"])[:limit]

    def context_block(self):
        """Takip sorusunda modele verilecek kanıt bloğu."""
        lines = ["BULGULAR (güven skorları hesaplanmıştır, değiştirme):"]
        shown = sorted(self.findings, key=lambda x: -x["confidence"])[:CONTEXT_MAX_FINDINGS]
        referenced_ids = set()
        for i, f in enumerate(shown, start=1):
            supporting = f.get("supporting", [])
            referenced_ids.update(supporting)
            refs = ", ".join(f"[{s}]" for s in supporting)
            newest = (
                f["newest_date"].strftime("%Y-%m-%d")
                if f.get("newest_date") else "tarih yok"
            )
            celiski = " (ÇELİŞKİLİ)" if f.get("contradicting") else ""
            lines.append(
                f"{i}. {f['statement']} — güven %{f['confidence']}, "
                f"kaynaklar: {refs}, en yeni: {newest}{celiski}"
            )

        lines.append("")
        lines.append("KAYNAKLAR:")
        # Kaynak numaraları bulgu referanslarıyla aynı (konumsal) numaradır.
        # Liste kısaltılırken limitin üstünde kalan ama bir bulgunun referans
        # verdiği kaynaklar da eklenir; yoksa model [21] gibi listede olmayan
        # bir numaraya dayanmak zorunda kalıyordu.
        for i, s in enumerate(self.sources, start=1):
            if i > CONTEXT_MAX_SOURCES and i not in referenced_ids:
                continue
            tarih = (
                s["published_at"].strftime("%Y-%m-%d")
                if s.get("published_at") else "?"
            )
            lines.append(f"[{i}] {s.get('title', '')} — {s.get('domain', '')} ({tarih})")

        if self.followups:
            lines.append("")
            lines.append("ÖNCEKİ TAKİP SORULARI:")
            for soru, cevap in self.followups[-3:]:
                lines.append(f"S: {soru}")
                lines.append(f"C: {cevap[:400]}")
        return "\n".join(lines)


class ResearchSession:
    """Oturum boyunca yapılan araştırmaları tutar ve takip sorularını yanıtlar."""

    def __init__(self, model_name, model_source):
        self.model_name = model_name
        self.model_source = model_source
        self.llm = LocalLLMClient(model_name, model_source)
        self.entries = []

    # ------------------------------------------------------------------
    # Kayıt
    # ------------------------------------------------------------------

    def add(self, topic, report, researcher, report_path, duration_sec):
        entry = ResearchEntry(
            topic=topic,
            report=report,
            findings=getattr(researcher, "findings", []),
            sources=getattr(researcher, "sources", []),
            report_path=report_path,
            duration_sec=duration_sec,
        )
        self.entries.append(entry)
        return entry

    def last(self):
        return self.entries[-1] if self.entries else None

    def best_match(self, topic):
        """Kelime örtüşmesine göre en yakın önceki araştırma (yoksa None)."""
        best, best_score = None, 0.0
        for entry in self.entries:
            score = topic_overlap(topic, entry.topic)
            if score > best_score:
                best, best_score = entry, score
        return (best, best_score) if best else (None, 0.0)

    # ------------------------------------------------------------------
    # Niyet sınıflandırma
    # ------------------------------------------------------------------

    async def classify(self, user_input):
        """
        Kullanıcı isteğini sınıflandırır.

        Döner: {"niyet": "takip"|"derinlestir"|"yeni", "kayit": ResearchEntry|None}
        """
        if not self.entries:
            return {"niyet": "yeni", "kayit": None}

        # Neredeyse birebir aynı konu tekrar sorulduysa modele danışılmaz:
        # aynı araştırmayı ikinci kez koşturmak dakikalar harcar ve aynı
        # sonucu üretir. Sınıflandırıcı bunu "yeni" derse bile kayıt kullanılır.
        kayit, ortusme = self.best_match(user_input)
        if kayit is not None and ortusme >= TOPIC_OVERLAP_THRESHOLD:
            return {"niyet": "takip", "kayit": kayit}

        gecmis = "\n".join(
            f"{i}. {e.topic}" for i, e in enumerate(self.entries, start=1)
        )
        prompt = f"""Bir araştırma asistanının oturumundasın.

BU OTURUMDA TAMAMLANMIŞ ARAŞTIRMALAR:
{gecmis}

KULLANICININ YENİ İSTEĞİ:
{user_input}

Bu isteği sınıflandır. Şu JSON'u döndür (başka bir şey yazma):
{{"niyet": "takip|derinlestir|yeni", "arastirma_no": <numara ya da 0>}}

Tanımlar:
- "takip": İstek, listedeki bir araştırmanın MEVCUT bulgularıyla cevaplanabilir.
  Açıklama, özetleme, karşılaştırma, "bunu biraz daha anlat" türü sorular.
- "derinlestir": Listedeki bir araştırmanın konusuyla ilgili ama o araştırmada
  KAPSANMAMIŞ yeni bir yön. Yeni kaynak aranması gerekir.
- "yeni": Listedeki hiçbir araştırmayla ilgisi olmayan bağımsız konu.

arastirma_no: takip/derinlestir ise ilgili araştırmanın numarası, yeni ise 0."""

        sonuc = None
        try:
            sonuc = await self.llm.call_json(
                prompt,
                system_prompt="Sen niyet sınıflandırıcısın. Yalnızca geçerli JSON üretirsin.",
                max_tokens=LLM_JSON_TOKENS_SMALL,
            )
        except LLMError as e:
            logger.warning(f"Niyet sınıflandırma başarısız, yedeğe düşülüyor: {e}")

        niyet, no = None, 0
        if isinstance(sonuc, dict):
            niyet = str(sonuc.get("niyet", "")).strip().lower()
            try:
                no = int(sonuc.get("arastirma_no", 0))
            except (TypeError, ValueError):
                no = 0

        if niyet not in ("takip", "derinlestir", "yeni"):
            return self._fallback_classify(user_input)

        kayit = None
        if niyet in ("takip", "derinlestir"):
            if 1 <= no <= len(self.entries):
                kayit = self.entries[no - 1]
            else:
                kayit = self.last()
        return {"niyet": niyet, "kayit": kayit}

    def _fallback_classify(self, user_input):
        """
        Model sınıflandıramazsa kelime örtüşmesine bak.

        Yüksek örtüşme + soru kalıbı → takip; yüksek örtüşme → derinleştir;
        düşük örtüşme → yeni araştırma.
        """
        kayit, skor = self.best_match(user_input)
        if kayit is None:
            return {"niyet": "yeni", "kayit": None}

        kapsama = topic_containment(user_input, kayit.topic)
        if skor < TOPIC_OVERLAP_THRESHOLD / 2 and kapsama < CONTAINMENT_THRESHOLD:
            return {"niyet": "yeni", "kayit": None}

        soru_kalibi = bool(
            re.search(r"\?|nedir|neden|nasıl|nasil|açıkla|acikla|özetle|ozetle|"
                      r"anlat|detay|karşılaştır|karsilastir",
                      user_input.lower())
        )
        if skor >= TOPIC_OVERLAP_THRESHOLD or soru_kalibi:
            return {"niyet": "takip", "kayit": kayit}
        return {"niyet": "derinlestir", "kayit": kayit}

    # ------------------------------------------------------------------
    # Takip cevabı
    # ------------------------------------------------------------------

    async def answer_followup(self, question, entry):
        """
        Kayıtlı bulgulara dayanarak takip sorusunu yanıtlar. Yeni arama yapmaz.

        Bilgi yetersizse model bunu açıkça söyler; uydurma cevap üretmemesi
        için istem seviyesinde kısıtlanır.
        """
        prompt = f"""Bugünün tarihi: {datetime.now().strftime('%d.%m.%Y')}
Tamamlanmış araştırmanın konusu: {entry.topic}

{entry.context_block()}

KULLANICININ SORUSU:
{question}

Görev: Soruyu YALNIZCA yukarıdaki bulgulara ve kaynaklara dayanarak Türkçe
yanıtla.

Kurallar:
- Yukarıda olmayan hiçbir bilgiyi ekleme, tahmin yürütme
- Dayandığın bulgunun kaynak numarasını [n] biçiminde belirt
- Güven skoru düşük bir bulguya dayanıyorsan bunu cümlede söyle
- Bulgular soruyu cevaplamaya yetmiyorsa şunu yaz: "Mevcut bulgular bu soruyu
  cevaplamaya yetmiyor." ve hangi bilginin eksik olduğunu tek cümleyle açıkla
- Kısa ve doğrudan ol; gereksiz giriş cümlesi kurma"""

        cevap = await self.llm.call(
            prompt,
            system_prompt=(
                "Sen kanıta dayalı araştırma asistanısın. Yalnızca sana verilen "
                "bulgulara dayanırsın, bilgi uydurmazsın."
            ),
            max_tokens=LLM_TEXT_TOKENS_ANSWER,
        )
        cevap = (cevap or "").strip()
        if cevap:
            entry.followups.append((question, cevap))
        return cevap

    # ------------------------------------------------------------------
    # Derinleştirme
    # ------------------------------------------------------------------

    async def focus_topic(self, user_input, entry):
        """
        Derinleştirme isteğini, arama motoruna verilecek odaklı bir konu
        başlığına çevirir. Model başarısız olursa iki konu birleştirilir.
        """
        prompt = f"""Önceki araştırma konusu: {entry.topic}
Kullanıcının derinleştirme isteği: {user_input}

Bu ikisini birleştiren, web araması için uygun TEK bir araştırma konusu yaz.
Şu JSON'u döndür (başka bir şey yazma):
{{"konu": "..."}}

Kurallar:
- Konu tek cümle, en fazla 15 kelime
- Kullanıcının sorduğu yönü merkeze al, önceki konuyu bağlam olarak koru"""
        try:
            sonuc = await self.llm.call_json(
                prompt,
                system_prompt="Sen araştırma konusu formüle edersin. Yalnızca geçerli JSON üretirsin.",
                max_tokens=LLM_JSON_TOKENS_SMALL,
            )
            if isinstance(sonuc, dict):
                konu = str(sonuc.get("konu", "")).strip()
                if len(konu) > 5:
                    return konu
        except LLMError as e:
            logger.warning(f"Odak konusu üretilemedi: {e}")
        return f"{entry.topic} — {user_input}"

    def known_sources(self):
        """Oturumda daha önce okunmuş tüm kaynak adresleri."""
        return {s["url"] for e in self.entries for s in e.sources if s.get("url")}
