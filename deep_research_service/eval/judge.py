"""
LocoDex Deep Search — Rubrikli LLM-Judge

Bir araştırma raporunu beş boyutta 0-1 arası puanlar ve geçti/kaldı kararı
verir. Tek LLM çağrısıyla çalışır: çok yargıçlı kurulumlara göre tek çağrılık
rubrik değerlendirmesi insan yargısıyla daha tutarlı bulunduğu için bu biçim
seçildi.

Sınır: yargıç yalnızca rapor metnini görür; kaynak sayfaları yeniden
indirmez. "Atıf uyumu" bu yüzden rapor içi tutarlılıktır (bulgular, kaynak
tablosu ve tarih etiketleri birbirini tutuyor mu), kaynak-metin doğrulaması
değildir.

Kullanım:
    python3 judge.py --rapor rapor.md --soru "..." [--beklenti "..."] -m gemma4:31b
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from llm_client import LocalLLMClient  # noqa: E402
from research_constants import LLM_JSON_TOKENS_DEFAULT  # noqa: E402

# Rapor bu uzunlukta kırpılır; rubrik değerlendirmesi için yeterli,
# yerel modelin bağlamını taşırmayacak kadar kısa.
RAPOR_MAX_CHARS = 12000

RUBRIK_BOYUTLARI = (
    "olgusal_dogruluk",
    "atif_uyumu",
    "tamlik",
    "kaynak_kalitesi",
    "guncellik_durustlugu",
)

# Geçme koşulu: toplam eşiği VE olgusal doğruluk tabanı. Olgusal olarak çürük
# ama iyi biçimlendirilmiş rapor geçemez.
GECME_TOPLAM_ESIGI = 0.60
GECME_OLGUSAL_TABANI = 0.50


def _prompt(soru, rapor, beklenti):
    beklenti_blok = (
        f"\nDEĞERLENDİRME ÖLÇÜTÜ (bu sorunun iyi cevabının taşıması gereken nitelikler):\n{beklenti}\n"
        if beklenti else ""
    )
    return f"""Bir derin araştırma raporunu değerlendireceksin.

ARAŞTIRMA SORUSU:
{soru}
{beklenti_blok}
RAPOR:
<<<RAPOR>>>
{rapor[:RAPOR_MAX_CHARS]}
<<<RAPOR SONU>>>

Raporu şu beş boyutta 0.0-1.0 arası puanla ve şu JSON'u döndür (başka bir şey yazma):
{{
  "olgusal_dogruluk": <0.0-1.0>,
  "atif_uyumu": <0.0-1.0>,
  "tamlik": <0.0-1.0>,
  "kaynak_kalitesi": <0.0-1.0>,
  "guncellik_durustlugu": <0.0-1.0>,
  "gerekce": "<3-5 cümlelik değerlendirme: en güçlü ve en zayıf yön>"
}}

Boyut tanımları:
- olgusal_dogruluk: İddialar tutarlı ve makul mü? İç çelişki, bariz yanlış ya da uydurma var mı?
- atif_uyumu: Bulgular kaynak numaralarına bağlanmış mı? Kaynak tablosu ile metin tutarlı mı? Kaynaksız güçlü iddia var mı?
- tamlik: Soru TAMAMEN cevaplanmış mı? Önemli bir yön atlanmış mı? Eksik-ama-tam-görünen rapor cezalandırılır.
- kaynak_kalitesi: Birincil/resmî kaynak mı, SEO içeriği ve blog mu? Kaynak çeşitliliği var mı?
- guncellik_durustlugu: Tarihler belirtilmiş mi? Eski bilgi güncel gibi sunulmuş mu? Belirsizlik dürüstçe söylenmiş mi?

Katı ol: mükemmel rapor nadirdir; 0.9+ yalnız kusursuz boyuta verilir."""


def _normalize_puan(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


async def degerlendir(soru, rapor, beklenti="", model="gemma4:31b", source="Ollama"):
    """Raporu puanlar. Döner: boyut puanları + toplam + gecti + gerekce."""
    llm = LocalLLMClient(model, source)
    sonuc = await llm.call_json(
        _prompt(soru, rapor, beklenti),
        system_prompt=(
            "Sen kıdemli araştırma kalitesi denetçisisin. Raporları rubrikle, "
            "katı ve tutarlı puanlarsın. Yalnızca geçerli JSON üretirsin."
        ),
        max_tokens=LLM_JSON_TOKENS_DEFAULT,
    )
    if not isinstance(sonuc, dict):
        return {
            "hata": "yargıç geçerli JSON döndürmedi",
            "toplam": 0.0,
            "gecti": False,
        }

    puanlar = {b: _normalize_puan(sonuc.get(b)) for b in RUBRIK_BOYUTLARI}
    toplam = sum(puanlar.values()) / len(RUBRIK_BOYUTLARI)
    gecti = (
        toplam >= GECME_TOPLAM_ESIGI
        and puanlar["olgusal_dogruluk"] >= GECME_OLGUSAL_TABANI
    )
    return {
        **puanlar,
        "toplam": round(toplam, 3),
        "gecti": gecti,
        "gerekce": str(sonuc.get("gerekce", "")).strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Araştırma raporu yargıcı")
    parser.add_argument("--rapor", required=True, help="rapor dosyası (markdown)")
    parser.add_argument("--soru", required=True, help="araştırma sorusu")
    parser.add_argument("--beklenti", default="", help="değerlendirme ölçütü")
    parser.add_argument("-m", "--model", default="gemma4:31b")
    parser.add_argument("-s", "--source", default="Ollama",
                        choices=["Ollama", "LM Studio"])
    args = parser.parse_args()

    rapor = Path(args.rapor).read_text(encoding="utf-8")
    sonuc = asyncio.run(
        degerlendir(args.soru, rapor, args.beklenti, args.model, args.source)
    )
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    return 0 if sonuc.get("gecti") else 1


if __name__ == "__main__":
    sys.exit(main())
