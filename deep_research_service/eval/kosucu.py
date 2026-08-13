"""
LocoDex Deep Search — Eval Koşucusu

sorular.json'daki soruları motor üzerinden koşturur, raporları kaydeder,
yargıcı (judge.py) çağırır ve özet tablo üretir. Her koşu --no-cache ile
yapılır; süre dökümü CLI'nin stderr özetinden toplanır.

Kullanım:
    python3 kosucu.py -m gemma4:31b                  # 20 sorunun tümü
    python3 kosucu.py -m gemma4:31b --sorular 1,13   # alt küme (duman testi)
    python3 kosucu.py -m gemma4:31b --etiket baseline
"""

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_SERVICE_DIR = _EVAL_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import judge  # noqa: E402  (eval dizininden)

KOSU_TIMEOUT_SEC = 1800  # tek soru için üst sınır (30 dk); asılmayı keser

_KAYNAK_RE = re.compile(r"\*\*Kaynak:\*\* (\d+) doğrulanmış")
_GUVEN_RE = re.compile(r"\*\*Genel Güven Skoru:\*\* %(\d+)")
_DOKUM_RE = re.compile(r"Döküm\s+(.+)")


def sorulari_yukle():
    data = json.loads((_EVAL_DIR / "sorular.json").read_text(encoding="utf-8"))
    return data["sorular"]


def _motoru_kostur(soru, model, source, rapor_yolu):
    """Tek soruyu CLI üzerinden koşturur; (süre, stderr_metni, hata) döner."""
    cmd = [
        sys.executable, str(_SERVICE_DIR / "cli.py"), "deepsearch", soru,
        "-m", model, "-s", source, "--no-cache", "--no-color",
    ]
    t0 = time.monotonic()
    try:
        sonuc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=KOSU_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return time.monotonic() - t0, "", f"zaman aşımı ({KOSU_TIMEOUT_SEC} sn)"
    sure = time.monotonic() - t0
    if sonuc.returncode != 0:
        return sure, sonuc.stderr, f"çıkış kodu {sonuc.returncode}"
    rapor_yolu.write_text(sonuc.stdout, encoding="utf-8")
    return sure, sonuc.stderr, None


def _rapor_metrikleri(rapor_metni, stderr_metni):
    kaynak = _KAYNAK_RE.search(rapor_metni)
    guven = _GUVEN_RE.search(rapor_metni)
    dokum = _DOKUM_RE.search(stderr_metni)
    return {
        "kaynak_sayisi": int(kaynak.group(1)) if kaynak else None,
        "genel_guven": int(guven.group(1)) if guven else None,
        "sure_dokumu": dokum.group(1).strip() if dokum else None,
    }


def _ozet_tablo(sonuclar):
    satirlar = [
        "| # | Tür | Süre | Kaynak | Güven | Judge | Geçti |",
        "|---|-----|------|--------|-------|-------|-------|",
    ]
    for s in sonuclar:
        judge_puan = s.get("judge", {}).get("toplam")
        satirlar.append(
            f"| {s['no']} | {s['tur']} | {s['sure_sn']:.0f} sn "
            f"| {s.get('kaynak_sayisi', '—')} | "
            f"{'%' + str(s['genel_guven']) if s.get('genel_guven') is not None else '—'} | "
            f"{judge_puan if judge_puan is not None else '—'} | "
            f"{'EVET' if s.get('judge', {}).get('gecti') else 'hayır' if 'judge' in s else '—'} |"
        )
    gecen = sum(1 for s in sonuclar if s.get("judge", {}).get("gecti"))
    puanli = [s["judge"]["toplam"] for s in sonuclar if s.get("judge", {}).get("toplam") is not None]
    ort = sum(puanli) / len(puanli) if puanli else 0.0
    toplam_sure = sum(s["sure_sn"] for s in sonuclar)
    satirlar.append("")
    satirlar.append(
        f"**Özet:** {len(sonuclar)} koşu · {gecen} geçti · "
        f"ortalama judge {ort:.2f} · toplam süre {toplam_sure / 60:.0f} dk"
    )
    return "\n".join(satirlar)


def main():
    parser = argparse.ArgumentParser(description="Eval koşucusu")
    parser.add_argument("-m", "--model", required=True)
    parser.add_argument("-s", "--source", default="Ollama",
                        choices=["Ollama", "LM Studio"])
    parser.add_argument("--sorular", default="",
                        help="virgüllü soru numaraları (boş = hepsi)")
    parser.add_argument("--etiket", default="",
                        help="koşu klasörü adına eklenecek etiket (örn. baseline)")
    parser.add_argument("--judge-model", default="",
                        help="yargıç modeli (boş = koşu modeliyle aynı)")
    args = parser.parse_args()

    sorular = sorulari_yukle()
    if args.sorular:
        istenen = {int(x) for x in args.sorular.split(",") if x.strip()}
        sorular = [s for s in sorular if s["no"] in istenen]
    if not sorular:
        print("Koşulacak soru yok.", file=sys.stderr)
        return 1

    zaman = datetime.now().strftime("%Y%m%d_%H%M")
    etiket = f"_{args.etiket}" if args.etiket else ""
    kosu_dizini = _EVAL_DIR / "kosular" / f"{zaman}{etiket}"
    kosu_dizini.mkdir(parents=True, exist_ok=True)
    judge_model = args.judge_model or args.model

    sonuclar = []
    for soru in sorular:
        no = soru["no"]
        print(f"[{no:02d}/{len(sorular)}] {soru['soru'][:70]}...", file=sys.stderr)
        rapor_yolu = kosu_dizini / f"soru_{no:02d}.md"
        sure, stderr_metni, hata = _motoru_kostur(
            soru["soru"], args.model, args.source, rapor_yolu
        )
        kayit = {"no": no, "tur": soru["tur"], "soru": soru["soru"],
                 "sure_sn": round(sure, 1)}
        if hata:
            kayit["hata"] = hata
            print(f"    HATA: {hata}", file=sys.stderr)
        else:
            rapor_metni = rapor_yolu.read_text(encoding="utf-8")
            kayit.update(_rapor_metrikleri(rapor_metni, stderr_metni))
            print(f"    {sure:.0f} sn, yargıç değerlendiriyor...", file=sys.stderr)
            kayit["judge"] = asyncio.run(judge.degerlendir(
                soru["soru"], rapor_metni, soru.get("beklenti", ""),
                judge_model, args.source,
            ))
        sonuclar.append(kayit)
        # Ara sonuçlar her soruda diske yazılır; uzun koşu yarıda kesilirse
        # o ana kadarki veri kaybolmaz.
        (kosu_dizini / "sonuclar.json").write_text(
            json.dumps(sonuclar, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    ozet = _ozet_tablo(sonuclar)
    (kosu_dizini / "OZET.md").write_text(
        f"# Eval Koşusu — {zaman}{etiket}\n\n"
        f"Model: {args.model} ({args.source}) · Yargıç: {judge_model}\n\n"
        + ozet + "\n", encoding="utf-8",
    )
    print("\n" + ozet)
    print(f"\nÇıktılar: {kosu_dizini}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
