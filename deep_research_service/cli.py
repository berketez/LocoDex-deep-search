"""
LocoDex Deep Search — Terminal Arayüzü

Sunucu ya da tarayıcı gerekmeden doğrudan komut satırından derin araştırma
çalıştırır. Araştırma motoru (`verified_research`) websocket üzerinden
ilerleme mesajı yayınladığı için, burada aynı arayüzü uygulayan bir konsol
yazıcısı devreye girer.

Model seçimi üç katmanlıdır (öncelik sırasıyla):
  1. --model bayrağı
  2. LOCODEX_MODEL ortam değişkeni
  3. ~/.locodex/config.json içindeki kayıtlı varsayılan
Hiçbiri yoksa ve terminal etkileşimliyse kurulu modeller numaralı listeyle
sunulur; etkileşimsiz ortamda (boru hattı, cron) hata verilir.

Kullanım:
    locodex models
    locodex deepsearch "araştırma konusu" -m gemma4:31b
    locodex serve
"""

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".locodex" / "config.json"
OLLAMA_PORT = 11434
LM_STUDIO_PORT = 1234
DISCOVERY_TIMEOUT_SEC = 3


# ----------------------------------------------------------------------
# Terminal biçimlendirme
# ----------------------------------------------------------------------

class Style:
    """ANSI renkleri; terminal desteklemiyorsa ya da NO_COLOR ayarlıysa boşalır."""

    def __init__(self, enabled):
        codes = {
            "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
            "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
            "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
        }
        for name, code in codes.items():
            setattr(self, name, code if enabled else "")


def _make_style(force_color=None):
    if force_color is True:
        return Style(True)
    if force_color is False or os.environ.get("NO_COLOR"):
        return Style(False)
    return Style(sys.stderr.isatty())


def _fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sn"
    return f"{seconds // 60} dk {seconds % 60:02d} sn"


def _fmt_clock(seconds):
    """Geçen süreyi sabit genişlikte mm:ss olarak biçimler."""
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# Araştırma motoru ilerleme mesajlarını web arayüzü için süsler; terminalde
# düz metin tercih edildiğinden bu işaretler ayıklanır. Ok işaretleri
# (U+2190-21FF) metnin anlamını taşıdığı için korunur.
_DECOR_RE = re.compile(
    "[\U0001F000-\U0001FAFF⌀-➿⬀-⯿︀-️‍]+"
)


def _plain(text):
    """Mesajı süslerden arındırır ve fazla boşlukları toplar."""
    return re.sub(r"\s{2,}", " ", _DECOR_RE.sub("", text)).strip()


def _rule(style, width=None):
    """Bölüm ayracı çizgisi."""
    width = width or min(shutil.get_terminal_size((80, 24)).columns, 76)
    print(f"{style.dim}{'─' * width}{style.reset}", file=sys.stderr)


# ----------------------------------------------------------------------
# Konsol ilerleme yazıcısı (websocket arayüzünü taklit eder)
# ----------------------------------------------------------------------

class ConsoleProgress:
    """
    Araştırma motorunun beklediği `send_json` arayüzünü uygular ve gelen
    ilerleme mesajlarını terminale yazar.

    Motor iki tür mesaj gönderir: adım güncellemeleri (`step` alanı olan) ve
    ara bilgi satırları. Hepsi stderr'e yazılır; böylece stdout yalnızca
    nihai raporu taşır ve `locodex deepsearch ... > rapor.md` çalışır.
    """

    def __init__(self, style, quiet=False, show_bar=True):
        self.style = style
        self.quiet = quiet
        self.show_bar = show_bar and sys.stderr.isatty()
        self.start = time.monotonic()
        self.last_step = 0.0
        self.saved_path = None
        self._bar_active = False

    def _clear_bar(self):
        if self._bar_active:
            sys.stderr.write("\r\033[K")
            self._bar_active = False

    def _write_bar(self):
        if not self.show_bar:
            return
        width = min(shutil.get_terminal_size((80, 20)).columns - 30, 40)
        if width < 10:
            return
        filled = int(self.last_step * width)
        bar = "█" * filled + "░" * (width - filled)
        elapsed = _fmt_duration(time.monotonic() - self.start)
        s = self.style
        sys.stderr.write(
            f"\r{s.cyan}{bar}{s.reset} {int(self.last_step * 100):3d}% {s.dim}{elapsed}{s.reset}"
        )
        sys.stderr.flush()
        self._bar_active = True

    async def send_json(self, data):
        raw = data.get("message", "")
        if raw and "Rapor kaydedildi:" in raw:
            self.saved_path = raw.split("Rapor kaydedildi:")[-1].strip()
        if self.quiet or not raw:
            return
        step = data.get("step")
        if isinstance(step, (int, float)):
            self.last_step = max(0.0, min(1.0, float(step)))

        # Motor alt satırları boşlukla girintiler; girinti düzeyi süsler
        # ayıklanmadan önce ölçülmelidir.
        indent = len(raw) - len(raw.lstrip(" "))
        msg = _plain(raw)
        if not msg:
            return

        self._clear_bar()
        s = self.style
        if indent >= 6:
            sys.stderr.write(f"{s.dim}            {msg}{s.reset}\n")
        elif indent >= 3:
            sys.stderr.write(f"{s.dim}        ·{s.reset} {msg}\n")
        else:
            clock = _fmt_clock(time.monotonic() - self.start)
            sys.stderr.write(f"{s.dim}{clock}{s.reset}  {msg}\n")
        sys.stderr.flush()
        self._write_bar()

    def finish(self):
        self._clear_bar()


# ----------------------------------------------------------------------
# Model keşfi
# ----------------------------------------------------------------------

def _http_get_json(url, timeout=DISCOVERY_TIMEOUT_SEC):
    """Bağımlılık eklememek için stdlib ile kısa GET; hata olursa None."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _host_candidates():
    env_host = os.environ.get("OLLAMA_HOST_IP")
    hosts = [env_host] if env_host else []
    hosts.append("127.0.0.1")
    return hosts


def discover_models():
    """
    Erişilebilir Ollama ve LM Studio sunucularındaki modelleri listeler.

    Döndürülen her kayıt: {"id", "source", "size_gb", "detail"}
    """
    models = []
    for host in _host_candidates():
        data = _http_get_json(f"http://{host}:{OLLAMA_PORT}/api/tags")
        if data and isinstance(data.get("models"), list):
            for m in data["models"]:
                name = m.get("name") or m.get("model")
                if not name:
                    continue
                size_gb = round((m.get("size") or 0) / 1e9, 1)
                details = m.get("details") or {}
                params = details.get("parameter_size", "")
                quant = details.get("quantization_level", "")
                detail = " ".join(x for x in (params, quant) if x)
                models.append({
                    "id": name, "source": "Ollama",
                    "size_gb": size_gb, "detail": detail,
                })
            break

    for host in _host_candidates():
        data = _http_get_json(f"http://{host}:{LM_STUDIO_PORT}/v1/models")
        if data and isinstance(data.get("data"), list):
            for m in data["data"]:
                name = m.get("id")
                if not name:
                    continue
                models.append({
                    "id": name, "source": "LM Studio",
                    "size_gb": 0.0, "detail": "",
                })
            break

    return models


# ----------------------------------------------------------------------
# Yapılandırma
# ----------------------------------------------------------------------

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def resolve_model(args, style):
    """
    Kullanılacak modeli (id, source) olarak çözer.

    Sıra: --model → LOCODEX_MODEL → kayıtlı varsayılan → etkileşimli seçim.
    """
    available = discover_models()

    def _source_for(model_id, explicit_source):
        if explicit_source:
            return explicit_source
        for m in available:
            if m["id"] == model_id:
                return m["source"]
        # Sunucu listelemesi başarısızsa Ollama varsay; istemci yine de
        # her iki uç noktayı sırayla dener.
        return "Ollama"

    chosen = args.model or os.environ.get("LOCODEX_MODEL")
    if not chosen:
        chosen = load_config().get("model")
        if chosen:
            print(
                f"{style.dim}Kayıtlı varsayılan model kullanılıyor: "
                f"{chosen}{style.reset}", file=sys.stderr,
            )

    if chosen:
        if available and not any(m["id"] == chosen for m in available):
            print(
                f"{style.yellow}Uyarı:{style.reset} '{chosen}' kurulu modeller "
                f"arasında görünmüyor; yine de denenecek.\n"
                f"{style.dim}Kurulu modeller için: locodex models{style.reset}",
                file=sys.stderr,
            )
        return chosen, _source_for(chosen, args.source)

    if not available:
        raise SystemExit(
            f"{style.red}Hiçbir model sunucusu bulunamadı.{style.reset}\n"
            "Ollama çalışıyor mu? (ollama serve) veya LM Studio sunucusu açık mı?\n"
            "Model adını doğrudan da verebilirsin: locodex deepsearch \"konu\" -m gemma4:31b"
        )

    if not sys.stdin.isatty():
        listing = "\n".join(f"  - {m['id']}  ({m['source']})" for m in available)
        raise SystemExit(
            f"{style.red}Model seçilmedi.{style.reset} Etkileşimsiz çalışmada "
            f"-m bayrağı zorunlu.\nKullanılabilir modeller:\n{listing}"
        )

    return _interactive_pick(available, style, args.source)


def _interactive_pick(available, style, explicit_source):
    print(f"\n{style.bold}Hangi modelle araştırma yapılsın?{style.reset}\n", file=sys.stderr)
    for i, m in enumerate(available, start=1):
        size = f"{m['size_gb']} GB" if m["size_gb"] else ""
        extra = " · ".join(x for x in (m["detail"], size) if x)
        extra = f" {style.dim}({extra}){style.reset}" if extra else ""
        print(
            f"  {style.cyan}{i}{style.reset}) {m['id']} "
            f"{style.dim}[{m['source']}]{style.reset}{extra}",
            file=sys.stderr,
        )
    print("", file=sys.stderr)

    while True:
        try:
            raw = input(f"Seçim [1-{len(available)}] (Enter = 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nİptal edildi.")
        if not raw:
            raw = "1"
        if raw.isdigit() and 1 <= int(raw) <= len(available):
            picked = available[int(raw) - 1]
            print(
                f"{style.dim}Bu modeli varsayılan yapmak için: "
                f"locodex config --model {picked['id']}{style.reset}\n",
                file=sys.stderr,
            )
            return picked["id"], explicit_source or picked["source"]
        print(f"{style.red}Geçersiz seçim.{style.reset}", file=sys.stderr)


# ----------------------------------------------------------------------
# Alt komutlar
# ----------------------------------------------------------------------

def cmd_models(args):
    style = _make_style(args.color)
    models = discover_models()
    if not models:
        print(
            f"{style.red}Model bulunamadı.{style.reset} Ollama ya da LM Studio "
            "çalışmıyor olabilir.",
            file=sys.stderr,
        )
        return 1

    default = load_config().get("model") or os.environ.get("LOCODEX_MODEL")
    print(f"\n{style.bold}Kullanılabilir modeller{style.reset}\n")
    for m in models:
        mark = f" {style.green}← varsayılan{style.reset}" if m["id"] == default else ""
        size = f"{m['size_gb']} GB" if m["size_gb"] else "—"
        detail = f" {style.dim}{m['detail']}{style.reset}" if m["detail"] else ""
        print(f"  {m['id']:<28} {style.dim}{m['source']:<10}{style.reset} {size:>8}{detail}{mark}")
    print(f"\n{style.dim}Kullanım: locodex deepsearch \"konu\" -m <model>{style.reset}\n")
    return 0


def cmd_config(args):
    style = _make_style(args.color)
    config = load_config()
    if args.model:
        config["model"] = args.model
        save_config(config)
        print(f"{style.green}Varsayılan model kaydedildi:{style.reset} {args.model}")
        print(f"{style.dim}{CONFIG_PATH}{style.reset}")
        return 0
    if not config:
        print(f"{style.dim}Kayıtlı yapılandırma yok ({CONFIG_PATH}).{style.reset}")
        print("Varsayılan model atamak için: locodex config --model gemma4:31b")
        return 0
    print(f"{style.bold}Yapılandırma{style.reset} {style.dim}({CONFIG_PATH}){style.reset}")
    for k, v in config.items():
        print(f"  {k}: {v}")
    return 0


def cmd_serve(args):
    style = _make_style(args.color)
    os.environ.setdefault("RESEARCH_ENGINE", args.engine)
    # fastapi ile starlette sürümleri birbirinden bağımsız güncellenmiş bir
    # ortamda (ör. sisteme elle starlette yüklenmesi) import TypeError ile
    # patlar ve kullanıcı ham traceback görür. Burada teşhis konur ve tam
    # çözüm komutu gösterilir.
    try:
        import uvicorn
        from server import app
    except (ImportError, TypeError) as e:
        from importlib import metadata

        def _surum(paket):
            try:
                return metadata.version(paket)
            except metadata.PackageNotFoundError:
                return "yok"

        print(
            f"{style.red}Web sunucusu başlatılamadı:{style.reset} {e}\n\n"
            f"Kurulu sürümler: fastapi {_surum('fastapi')} · "
            f"starlette {_surum('starlette')} · uvicorn {_surum('uvicorn')}\n"
            f"Muhtemel neden: fastapi ile starlette sürümleri uyumsuz "
            f"(paketlerden biri tek başına güncellenmiş).\n\n"
            f"Çözüm — uyumlu çifti birlikte kur:\n"
            f"  {style.bold}python3 -m pip install --upgrade "
            f"\"fastapi>=0.110.2\" \"uvicorn[standard]>=0.29.0\"{style.reset}\n"
            f"ya da tüm bağımlılıkları tazele:\n"
            f"  {style.bold}python3 -m pip install --upgrade -r "
            f"deep_research_service/requirements.txt{style.reset}\n\n"
            f"{style.dim}Not: terminal arayüzü (locodex deepsearch) bu "
            f"paketlere ihtiyaç duymaz, çalışmaya devam eder.{style.reset}",
            file=sys.stderr,
        )
        return 2
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _apply_tuning(args, style):
    """
    Hız/derinlik ayarlarını motor modülü üzerinde geçerli kılar.

    Sabitler `verified_research` içine modül düzeyinde import edildiği için
    modül niteliğini değiştirmek çalışma zamanında etkili olur.
    """
    import verified_research as vr

    # Smart motorun sorgu/kaynak sayıları kod içinde sabittir; bu bayraklar
    # yalnızca verified motoru etkiler. Sessizce yok saymak kullanıcıyı
    # "ayar yaptım" sanrısında bırakıyordu.
    if args.engine == "smart":
        if any(v is not None for v in (args.sources, args.rounds, args.queries)):
            print(
                f"{style.yellow}Uyarı:{style.reset} smart motor "
                f"--sources/--rounds/--queries ayarlarını desteklemiyor; yok sayıldı.",
                file=sys.stderr,
            )
        return

    applied = []
    if args.sources is not None:
        vr.SEARCH_MAX_SOURCES_PER_ROUND = args.sources
        applied.append(f"tur başına kaynak: {args.sources}")
    if args.rounds is not None:
        vr.RESEARCH_MAX_ROUNDS = args.rounds
        applied.append(f"en fazla tur: {args.rounds}")
    if args.queries is not None:
        vr.SEARCH_MAX_QUERIES_PER_ROUND = args.queries
        applied.append(f"tur başına sorgu: {args.queries}")
    if applied:
        print(f"{style.dim}Ayar — {', '.join(applied)}{style.reset}", file=sys.stderr)


def cmd_deepsearch(args):
    style = _make_style(args.color)
    topic = " ".join(args.topic).strip()

    # Konu verilmediyse etkileşimli sihirbaz: sağlayıcı → model → derinlik → konu
    if not topic:
        return run_wizard(args, style)

    model_id, model_source = resolve_model(args, style)
    return _run_research(topic, model_id, model_source, args, style)


class ResearchOutcome:
    """Bir araştırma koşusunun sonucu; hem tek seferlik hem oturum kipinde kullanılır."""

    def __init__(self, report, researcher, elapsed, report_path, from_cache=False):
        self.report = report
        self.researcher = researcher
        self.elapsed = elapsed
        self.report_path = report_path
        self.from_cache = from_cache


def _run_research(topic, model_id, model_source, args, style):
    """Tek seferlik kip: araştır, raporu stdout'a yaz."""
    outcome = _execute_research(topic, model_id, model_source, args, style)
    if isinstance(outcome, int):
        return outcome
    sys.stdout.write(outcome.report)
    if not outcome.report.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _prepare_engine(args, style):
    """Ortam değişkenlerini ayarlar, motor sınıfını ve önbelleği döndürür."""
    if args.out:
        out_dir = Path(args.out).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        os.environ["RESEARCH_OUTPUT_DIR"] = str(out_dir)

    os.environ["RESEARCH_ENGINE"] = args.engine
    _apply_tuning(args, style)

    if args.engine == "smart":
        from smart_multilingual_research import SmartMultilingualResearcher as Engine
    else:
        from verified_research import VerifiedDeepResearcher as Engine

    cache = None
    if not args.no_cache:
        try:
            from utils.research_cache import research_cache
            cache = research_cache
        except ImportError:
            cache = None
    return Engine, cache


def _execute_research(topic, model_id, model_source, args, style, force_fresh=False):
    """
    Araştırmayı koşturur. Başarılıysa ResearchOutcome, hatalıysa çıkış kodu döner.

    force_fresh: önbellekte kayıt olsa bile araştırmayı baştan koşturur
    (/yeni komutu). Sonuç yine önbelleğe yazılır, eski kayıt tazelenir.
    """
    from llm_client import LLMError

    Engine, cache = _prepare_engine(args, style)
    engine = args.engine
    # Aynı konu farklı model ya da motorla sorulduğunda öncekinin cevabı
    # dönmesin diye önbellek anahtarına motor + model eklenir.
    cache_variant = f"{engine}|{model_id}"

    if cache is not None and not force_fresh:
        cached = cache.get(topic, cache_variant)
        if cached and cached.get("answer"):
            print(
                f"{style.yellow}Önbellekten geldi{style.reset} "
                f"{style.dim}(24 saat geçerli; yeniden çalıştırmak için "
                f"--no-cache){style.reset}",
                file=sys.stderr,
            )
            return ResearchOutcome(cached["answer"], None, 0.0, None, from_cache=True)

    engine_label = (
        "Doğrulamalı derin araştırma" if engine != "smart"
        else "Akıllı çok dilli araştırma"
    )
    depth_bits = []
    if args.rounds is not None:
        depth_bits.append(f"{args.rounds} tur")
    if args.sources is not None:
        depth_bits.append(f"{args.sources} kaynak")
    if args.queries is not None:
        depth_bits.append(f"{args.queries} sorgu")

    rows = [
        ("Konu", topic),
        ("Model", f"{model_id} · {model_source}"),
        ("Yöntem", engine_label),
    ]
    if depth_bits:
        rows.append(("Kapsam", " · ".join(depth_bits)))
    rows.append(("Başlangıç", datetime.now().strftime("%d.%m.%Y %H:%M")))

    _rule(style)
    for label, value in rows:
        print(f"  {style.dim}{label:<10}{style.reset}{value}", file=sys.stderr)
    _rule(style)
    print("", file=sys.stderr)

    progress = ConsoleProgress(style, quiet=args.quiet)
    researcher = Engine(
        model_name=model_id, model_source=model_source, websocket=progress
    )

    started = time.monotonic()
    try:
        report = asyncio.run(researcher.run_research(topic))
    except KeyboardInterrupt:
        progress.finish()
        print(f"\n{style.yellow}Araştırma iptal edildi.{style.reset}", file=sys.stderr)
        return 130
    except LLMError as e:
        progress.finish()
        print(
            f"\n{style.red}Model hatası:{style.reset} {e}\n"
            f"{style.dim}'{model_id}' yüklü ve sunucu açık mı? "
            f"Kontrol: locodex models{style.reset}",
            file=sys.stderr,
        )
        return 2
    finally:
        progress.finish()

    # Kaynaksız biten koşu (ağ kesintisi, arama motoru boş döndü) önbelleğe
    # yazılmaz: boş raporu 24 saat sunmak, düzelen ağda bile yeniden denemeyi
    # engelliyordu.
    fetched_sources = getattr(researcher, "sources", None)
    if cache is not None and fetched_sources != []:
        # Önbelleğe yazamamak (disk dolu, izin sorunu) tamamlanmış bir
        # araştırmayı geçersiz kılmaz; rapor yine döndürülür.
        try:
            cache.set(topic, {"answer": report, "status": "success"}, cache_variant)
        except (OSError, sqlite3.Error) as e:
            logger.warning(f"Sonuç önbelleğe yazılamadı: {e}")

    elapsed = time.monotonic() - started
    print_summary(researcher, elapsed, progress.saved_path, style)
    return ResearchOutcome(report, researcher, elapsed, progress.saved_path)


def print_summary(researcher, elapsed, report_path, style):
    """Araştırma sonrası terminale basılan özet: sayılar + öne çıkan bulgular."""
    sources = getattr(researcher, "sources", []) or []
    findings = getattr(researcher, "findings", []) or []
    skipped = getattr(researcher, "skipped", {}) or {}
    queries = getattr(researcher, "all_queries", []) or []

    overall = (
        int(round(sum(f["confidence"] for f in findings) / len(findings)))
        if findings else 0
    )
    contradicted = sum(1 for f in findings if f.get("contradicting"))

    kaynak_satiri = f"{len(sources)} doğrulandı"
    if skipped:
        kaynak_satiri += f" · {sum(skipped.values())} kullanılamadı"
    bulgu_satiri = f"{len(findings)}"
    if contradicted:
        bulgu_satiri += f" ({contradicted} çelişkili)"

    print("", file=sys.stderr)
    _rule(style)
    rows = [
        ("Durum", f"{style.green}tamamlandı{style.reset} {style.dim}· {_fmt_duration(elapsed)}{style.reset}"),
        ("Kaynak", kaynak_satiri),
        ("Bulgu", bulgu_satiri),
        ("Güven", f"%{overall}" if findings else "—"),
        ("Sorgu", str(len(queries))),
    ]
    timings = getattr(researcher, "timings", None) or {}
    dokum = " · ".join(
        f"{asama} {_fmt_duration(saniye)}" for asama, saniye in timings.items()
        if saniye >= 0.5
    )
    if dokum:
        rows.append(("Döküm", dokum))
    if report_path:
        rows.append(("Rapor", report_path))
    for label, value in rows:
        print(f"  {style.dim}{label:<10}{style.reset}{value}", file=sys.stderr)

    top = sorted(findings, key=lambda f: -f["confidence"])[:3]
    if top:
        print(f"\n  {style.dim}Öne çıkan bulgular{style.reset}", file=sys.stderr)
        for f in top:
            metin = f["statement"]
            if len(metin) > 150:
                metin = metin[:147].rstrip() + "..."
            print(
                f"    {style.dim}·{style.reset} {metin} "
                f"{style.dim}(%{f['confidence']}){style.reset}",
                file=sys.stderr,
            )
    _rule(style)
    print("", file=sys.stderr)


# ----------------------------------------------------------------------
# Etkileşimli sihirbaz
# ----------------------------------------------------------------------

# Derinlik ön ayarları: (tur, tur başına kaynak, tur başına sorgu)
DEPTH_PRESETS = {
    "fast": (1, 6, 4),
    "balanced": (2, 10, 5),
    "deep": (3, 14, 6),
}


def run_wizard(args, style):
    """
    Adım adım etkileşimli akış:
    sağlayıcı → servisi başlat → model → derinlik → konu → araştırma.
    """
    import tui

    tui.banner(style)

    providers = tui.detect_providers()
    if not providers:
        raise SystemExit(
            f"{style.red}Kurulu model sunucusu bulunamadı.{style.reset}\n"
            "Ollama (ollama.com) ya da LM Studio (lmstudio.ai) kur, sonra tekrar dene."
        )

    provider_options = [
        {
            "label": p["name"],
            "detail": (
                f"port {p['port']} · çalışıyor" if p["running"]
                else f"port {p['port']} · kapalı, başlatılacak"
            ),
            "value": p["key"],
        }
        for p in providers
    ]
    provider_key = tui.select_menu(
        "1 · Hangi model sunucusunu kullanacaksın?", provider_options, style
    )
    if provider_key is None:
        print(f"{style.dim}İptal edildi.{style.reset}", file=sys.stderr)
        return 130

    if not tui.start_provider(provider_key, style):
        return 2

    models = tui.provider_models(provider_key)
    if not models:
        raise SystemExit(
            f"{style.red}Bu sunucuda yüklü model yok.{style.reset}\n"
            "Ollama için örnek: ollama pull gemma4:31b"
        )

    default_model = load_config().get("model") or os.environ.get("LOCODEX_MODEL")
    models.sort(key=lambda m: (m["id"] != default_model, m["id"]))
    model_options = [
        {
            "label": m["id"],
            "detail": " · ".join(
                x for x in (
                    m["detail"],
                    f"{m['size_gb']} GB" if m["size_gb"] else "",
                    "varsayılan" if m["id"] == default_model else "",
                ) if x
            ),
            "value": m,
        }
        for m in models
    ]
    model = tui.select_menu("2 · Hangi model?", model_options, style)
    if model is None:
        print(f"{style.dim}İptal edildi.{style.reset}", file=sys.stderr)
        return 130

    # Kapsam komut satırında zaten belirlenmişse (--fast ya da üç bayrağın
    # da verilmesi) derinlik sorusu sorulmaz: menüden yapılan seçim bu
    # durumda sessizce yok sayılıyordu.
    if all(v is not None for v in (args.rounds, args.sources, args.queries)):
        print(
            f"{style.dim}Kapsam komut satırından alındı: {args.rounds} tur · "
            f"{args.sources} kaynak · {args.queries} sorgu{style.reset}\n",
            file=sys.stderr,
        )
        return _conversation_loop(model, args, style)

    # Sığdan derine sıralı; varsayılan olarak ortadaki (Dengeli) seçili gelir.
    depth_options = [
        {
            "label": "Hızlı",
            "detail": "1 tur · 6 kaynak — en kısa süre",
            "value": "fast",
        },
        {
            "label": "Dengeli",
            "detail": "2 tur · 10 kaynak — çoğu konu için yeterli",
            "value": "balanced",
        },
        {
            "label": "Derin",
            "detail": "3 tur · 14 kaynak — en kapsamlı, en uzun",
            "value": "deep",
        },
    ]
    depth = tui.select_menu(
        "3 · Araştırma derinliği", depth_options, style,
        hint="Süre modele göre değişir; kaynak sayısı arttıkça uzar.",
        default_index=1,
    )
    if depth is None:
        print(f"{style.dim}İptal edildi.{style.reset}", file=sys.stderr)
        return 130

    rounds, sources, queries = DEPTH_PRESETS[depth]
    # Komut satırından açıkça verilen değerler ön ayarı ezer
    if args.rounds is None:
        args.rounds = rounds
    if args.sources is None:
        args.sources = sources
    if args.queries is None:
        args.queries = queries

    return _conversation_loop(model, args, style)


# ----------------------------------------------------------------------
# Sohbet döngüsü
# ----------------------------------------------------------------------

EXIT_WORDS = {"/cikis", "/çıkış", "/exit", "/quit", "/q", "cikis", "çıkış"}
HELP_TEXT = """Komutlar
  /rapor        son raporun dosya yolunu göster
  /kaynaklar    son araştırmanın kaynak listesi
  /gecmis       bu oturumdaki araştırmalar
  /yeni <konu>  konu benzer olsa bile sıfırdan araştır
  /yardim       bu liste
  /cikis        çık

Normal yazarsan istek otomatik değerlendirilir: mevcut bulgularla
cevaplanabiliyorsa arama yapılmadan yanıtlanır, eksik yön varsa
o yöne odaklı yeni tur koşulur, ilgisiz konuysa yeni araştırma başlar."""


def _wrap(text, width=76, indent="  "):
    """Uzun metni terminale sığacak biçimde sarar."""
    import textwrap

    parts = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            parts.append("")
            continue
        parts.extend(
            textwrap.wrap(
                paragraph, width=width,
                initial_indent=indent, subsequent_indent=indent,
            ) or [indent]
        )
    return "\n".join(parts)


def _thinking(style, message):
    """
    Model beklenirken tek satırlık durum bildirimi. Terminal dışına yazarken
    (boru hattı, günlük dosyası) satır silinemeyeceği için atlanır.
    """
    if not sys.stderr.isatty():
        return
    sys.stderr.write(f"{style.dim}  {message}{style.reset}")
    sys.stderr.flush()


def _clear_line():
    if not sys.stderr.isatty():
        return
    sys.stderr.write("\r\033[K")
    sys.stderr.flush()


def _conversation_loop(model, args, style):
    """
    Araştırma bittikten sonra kapanmaz; yeni istek bekler.

    Oturum hafızası sayesinde aynı konu ikinci kez araştırılmaz: istek önce
    sınıflandırılır, mevcut bulgularla cevaplanabiliyorsa arama yapılmaz.
    """
    import tui
    from llm_client import LLMError
    from session import ResearchSession

    session = ResearchSession(model["id"], model["source"])
    first = True

    while True:
        if first:
            baslik = "4 · Neyi araştıralım?"
            ipucu = "Soru ya da konu başlığı yazabilirsin."
            ornek = "örn. gıda üretiminde yapay zeka uygulamaları 2026"
        else:
            baslik = "Sıradaki istek"
            ipucu = "Takip sorusu sorabilir ya da yeni konu yazabilirsin · /yardim"
            ornek = "takip sorusu, yeni konu ya da komut"

        istek = tui.input_box(baslik, style, placeholder=ornek, hint=ipucu)
        if istek is None:
            break
        first = False

        komut = istek.strip().lower()
        if komut in EXIT_WORDS:
            break
        if komut in ("/yardim", "/help", "/?"):
            print(f"\n{_wrap(HELP_TEXT)}\n", file=sys.stderr)
            continue
        if komut == "/rapor":
            _print_report_path(session, style)
            continue
        if komut == "/kaynaklar":
            _print_sources(session, style)
            continue
        if komut == "/gecmis":
            _print_history(session, style)
            continue

        zorla_yeni = False
        if komut.startswith("/yeni"):
            istek = istek.strip()[5:].strip()
            zorla_yeni = True
            if not istek:
                print(f"{style.dim}  /yeni komutundan sonra konu yaz.{style.reset}",
                      file=sys.stderr)
                continue

        # Niyet: takip / derinleştir / yeni
        karar = {"niyet": "yeni", "kayit": None}
        if session.entries and not zorla_yeni:
            _thinking(style, "istek değerlendiriliyor...")
            try:
                karar = asyncio.run(session.classify(istek))
            except LLMError as e:
                karar = {"niyet": "yeni", "kayit": None}
                _clear_line()
                print(
                    f"{style.dim}  İstek sınıflandırılamadı ({e}); yeni "
                    f"araştırma olarak ele alınıyor.{style.reset}",
                    file=sys.stderr,
                )
            else:
                _clear_line()

        if karar["niyet"] == "takip" and karar["kayit"] is not None:
            _answer_from_memory(session, karar["kayit"], istek, style)
            continue

        if karar["niyet"] == "derinlestir" and karar["kayit"] is not None:
            _thinking(style, "odak konusu belirleniyor...")
            try:
                istek = asyncio.run(session.focus_topic(istek, karar["kayit"]))
            except LLMError:
                istek = f"{karar['kayit'].topic} — {istek}"
            _clear_line()
            print(
                f"{style.dim}  Önceki araştırma derinleştiriliyor:{style.reset} {istek}\n",
                file=sys.stderr,
            )

        outcome = _execute_research(
            istek, model["id"], model["source"], args, style,
            force_fresh=zorla_yeni,
        )
        if isinstance(outcome, int):
            if outcome == 130:
                continue
            print(
                f"{style.dim}  Araştırma tamamlanamadı; başka bir istek "
                f"deneyebilirsin.{style.reset}\n", file=sys.stderr,
            )
            continue
        if outcome.from_cache:
            # Önbellekten gelen sonuçta bulgu/kaynak nesneleri yok; oturum
            # hafızasına eklenemez, takip sorusu bu kayıt üzerinden çalışmaz.
            print(
                f"{style.dim}  Bu konu son 24 saat içinde araştırılmış. Takip "
                f"sorusu sorabilmek için sıfırdan araştırmak gerekir:{style.reset}\n"
                f"    /yeni {istek}\n", file=sys.stderr,
            )
            continue

        session.add(
            istek, outcome.report, outcome.researcher,
            outcome.report_path, outcome.elapsed,
        )

    print(f"\n{style.dim}Oturum kapatıldı.{style.reset}\n", file=sys.stderr)
    return 0


def _answer_from_memory(session, entry, question, style):
    """Takip sorusunu kayıtlı bulgulardan yanıtlar. Arama yapılmaz."""
    from llm_client import LLMError

    print(
        f"{style.dim}  Bu soru mevcut araştırmadan yanıtlanıyor "
        f"({len(entry.findings)} bulgu, {len(entry.sources)} kaynak) — "
        f"yeni arama yapılmıyor.{style.reset}",
        file=sys.stderr,
    )
    _thinking(style, "yanıt hazırlanıyor...")
    try:
        cevap = asyncio.run(session.answer_followup(question, entry))
    except LLMError as e:
        _clear_line()
        print(f"{style.red}  Model hatası:{style.reset} {e}\n", file=sys.stderr)
        return False
    _clear_line()
    if not cevap:
        print(f"{style.dim}  Yanıt üretilemedi.{style.reset}\n", file=sys.stderr)
        return False
    print(f"\n{_wrap(cevap)}\n", file=sys.stderr)
    return True


def _print_report_path(session, style):
    entry = session.last()
    if entry is None:
        print(f"{style.dim}  Henüz araştırma yapılmadı.{style.reset}\n", file=sys.stderr)
        return
    print(f"\n  {style.dim}Konu {style.reset} {entry.topic}", file=sys.stderr)
    print(f"  {style.dim}Rapor{style.reset} {entry.report_path or 'kaydedilemedi'}\n",
          file=sys.stderr)


def _print_sources(session, style):
    entry = session.last()
    if entry is None or not entry.sources:
        print(f"{style.dim}  Kayıtlı kaynak yok.{style.reset}\n", file=sys.stderr)
        return
    print(f"\n  {style.bold}Kaynaklar{style.reset} {style.dim}— {entry.topic}{style.reset}\n",
          file=sys.stderr)
    for i, s in enumerate(entry.sources, start=1):
        tarih = s["published_at"].strftime("%d.%m.%Y") if s.get("published_at") else "tarih yok"
        guven = int(round(s.get("reliability", 0) * 100))
        print(
            f"  {i:>2}. {s.get('domain', '?'):<28} {style.dim}{tarih:<12} "
            f"güvenilirlik %{guven}{style.reset}", file=sys.stderr,
        )
        print(f"      {style.dim}{s.get('url', '')}{style.reset}", file=sys.stderr)
    print("", file=sys.stderr)


def _print_history(session, style):
    if not session.entries:
        print(f"{style.dim}  Bu oturumda henüz araştırma yapılmadı.{style.reset}\n",
              file=sys.stderr)
        return
    print(f"\n  {style.bold}Bu oturumdaki araştırmalar{style.reset}\n", file=sys.stderr)
    for i, e in enumerate(session.entries, start=1):
        print(
            f"  {i}. {e.topic}\n"
            f"     {style.dim}{len(e.sources)} kaynak · {len(e.findings)} bulgu · "
            f"güven %{e.overall_confidence()} · {e.created_at.strftime('%H:%M')} · "
            f"{len(e.followups)} takip sorusu{style.reset}",
            file=sys.stderr,
        )
    print("", file=sys.stderr)


# ----------------------------------------------------------------------
# Argüman ayrıştırma
# ----------------------------------------------------------------------

def _color_flags(parser, suppress=False):
    """
    Renk bayraklarını hem üst düzey hem alt komut düzeyinde tanımlar.

    Alt komut kopyalarında varsayılan SUPPRESS'tir; böylece bayrak
    verilmediğinde üst düzeyde okunan değeri ezmez.
    """
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument(
        "--color", dest="color", action="store_true", default=default,
        help="renkli çıktıyı zorla",
    )
    parser.add_argument(
        "--no-color", dest="color", action="store_false", default=default,
        help="renkleri kapat",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="locodex",
        description="LocoDex Deep Search — lokal modellerle derin web araştırması",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Örnekler:
  locodex models
  locodex deepsearch "gıda üretiminde yapay zeka 2026" -m gemma4:31b
  locodex deepsearch "konu" --fast > rapor.md
  locodex config --model gemma4:31b
  locodex serve
""",
    )
    _color_flags(parser)
    # Alt komutlar da renk bayraklarını kabul eder (konum bağımsız kullanım)
    common = argparse.ArgumentParser(add_help=False)
    _color_flags(common, suppress=True)

    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser(
        "deepsearch", aliases=["search", "ara"], parents=[common],
        help="bir konuda derin araştırma yap",
    )
    p_search.add_argument(
        "topic", nargs="*",
        help="araştırma konusu; boş bırakılırsa etkileşimli sihirbaz açılır",
    )
    p_search.add_argument(
        "-m", "--model",
        help="kullanılacak model (örn. gemma4:31b). Verilmezse seçim menüsü açılır",
    )
    p_search.add_argument(
        "-s", "--source", choices=["Ollama", "LM Studio"],
        help="model sunucusu; verilmezse modelden çıkarılır",
    )
    p_search.add_argument(
        "-e", "--engine", choices=["verified", "smart"], default="verified",
        help="araştırma motoru (varsayılan: verified)",
    )
    p_search.add_argument("-o", "--out", help="raporun kaydedileceği dizin")
    p_search.add_argument(
        "--sources", type=int, help="tur başına incelenecek kaynak sayısı",
    )
    p_search.add_argument("--rounds", type=int, help="en fazla araştırma turu")
    p_search.add_argument("--queries", type=int, help="tur başına arama sorgusu")
    p_search.add_argument(
        "--fast", action="store_true",
        help="hızlı ön izleme: 1 tur, 6 kaynak, 4 sorgu",
    )
    p_search.add_argument(
        "--no-cache", action="store_true", help="önbelleği yok say, baştan araştır",
    )
    p_search.add_argument(
        "-q", "--quiet", action="store_true", help="ilerleme satırlarını gizle",
    )
    p_search.set_defaults(func=cmd_deepsearch)

    p_models = sub.add_parser("models", parents=[common], help="kurulu modelleri listele")
    p_models.set_defaults(func=cmd_models)

    p_config = sub.add_parser("config", parents=[common], help="varsayılan modeli göster/ayarla")
    p_config.add_argument("-m", "--model", help="varsayılan model olarak kaydet")
    p_config.set_defaults(func=cmd_config)

    p_serve = sub.add_parser("serve", parents=[common], help="web/WebSocket sunucusunu başlat")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8001)
    p_serve.add_argument("--engine", choices=["verified", "smart"], default="verified")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # Argümansız çağrı da sihirbazı açar
        return main(["deepsearch"])
    if getattr(args, "fast", False):
        # Açıkça verilen değerler --fast ön ayarını ezer
        if args.rounds is None:
            args.rounds = 1
        if args.sources is None:
            args.sources = 6
        if args.queries is None:
            args.queries = 4
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
