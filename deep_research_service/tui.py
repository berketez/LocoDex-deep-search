"""
LocoDex Deep Search — Etkileşimli Terminal Arayüzü

Bağımlılık eklemeden (yalnızca stdlib) ok tuşlarıyla gezilebilen menüler ve
metin giriş kutusu sağlar. Terminal ham (raw) kipe alınamıyorsa — boru hattı,
cron, IDE konsolu — otomatik olarak numaralı seçim kipine düşer.

Sağlayıcı katmanı, kurulu model sunucularını (Ollama, LM Studio) tespit eder,
kapalıysa başlatır ve hazır olmasını bekler.
"""

import contextlib
import json
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

OLLAMA_PORT = 11434
LM_STUDIO_PORT = 1234
SERVICE_START_TIMEOUT_SEC = 40
SERVICE_POLL_INTERVAL_SEC = 0.5

_LMS_CLI_CANDIDATES = (
    Path.home() / ".lmstudio" / "bin" / "lms",
    Path("/usr/local/bin/lms"),
    Path("/opt/homebrew/bin/lms"),
)


# ----------------------------------------------------------------------
# Terminal temelleri
# ----------------------------------------------------------------------

def supports_raw_input():
    """Ok tuşu okumak için terminalin ham kipe alınabilir olması gerekir."""
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    return True


@contextlib.contextmanager
def raw_mode():
    """
    Terminali tuş tuş okuma kipine alır, çıkışta eski ayarı geri yükler.

    Kip her tuş için değil, tüm etkileşim boyunca bir kez kurulur: aksi hâlde
    tuşlar arasındaki kısa satır kipi penceresinde gelen karakterler ekrana
    yankılanıyor ve kaçış dizileri bölünüyordu.

    setraw yerine setcbreak kullanılır; böylece çıktı sonrası işleme açık kalır
    ve satır sonları terminali bozmadan çalışır.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    eski = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, eski)


def _read_char(fd):
    """
    Tek karakter okur; çok baytlı UTF-8 dizilerini eksiksiz alır.

    Tek bayt okumak Türkçe karakterleri (ı, ğ, ü, ş, ö, ç) bozuyordu.
    """
    ilk = os.read(fd, 1)
    if not ilk:
        return ""
    bayt = ilk[0]
    if bayt >= 0xF0:
        ek = 3
    elif bayt >= 0xE0:
        ek = 2
    elif bayt >= 0xC0:
        ek = 1
    else:
        ek = 0
    while ek > 0:
        devam = os.read(fd, ek)
        if not devam:
            break
        ilk += devam
        ek -= len(devam)
    return ilk.decode("utf-8", errors="ignore")


def read_key(fd=None):
    """
    Tek tuş okur ve normalize eder. Terminal ham kipte olmalıdır (raw_mode).

    Döner: "up", "down", "enter", "esc", "backspace", "ctrl-c" ya da karakter.
    """
    if fd is None:
        fd = sys.stdin.fileno()
    try:
        ch = _read_char(fd)
    except OSError:
        return "ctrl-d"
    if not ch:
        return "ctrl-d"
    if ch == "\x1b":
        # Kaçış dizisi mi yoksa yalnız ESC mi: kısa süre daha veri bekle
        if select.select([fd], [], [], 0.05)[0]:
            seq = os.read(fd, 2).decode("utf-8", errors="ignore")
            return {
                "[A": "up", "[B": "down", "[C": "right", "[D": "left",
            }.get(seq, "esc")
        return "esc"
    if ch in ("\r", "\n"):
        return "enter"
    if ch in ("\x7f", "\b"):
        return "backspace"
    if ch == "\x03":
        return "ctrl-c"
    if ch == "\x04":
        return "ctrl-d"
    return ch


def _w(text):
    sys.stderr.write(text)
    sys.stderr.flush()


def hide_cursor():
    if sys.stderr.isatty():
        _w("\033[?25l")


def show_cursor():
    if sys.stderr.isatty():
        _w("\033[?25h")


def term_width(default=80):
    return shutil.get_terminal_size((default, 24)).columns


def banner(style):
    """Üst başlık kutusu. Dolgu, ANSI kodları hariç görünür uzunluktan hesaplanır."""
    title = "LocoDex Deep Search"
    subtitle = "Lokal modellerle doğrulamalı derin araştırma"
    width = min(term_width(), 72)
    inner = width - 2
    line = "─" * inner

    def row(text, decor):
        pad = " " * max(inner - len(text) - 1, 0)
        return (f"{style.cyan}│{style.reset} {decor}{text}{style.reset}{pad}"
                f"{style.cyan}│{style.reset}\n")

    _w(
        f"\n{style.cyan}╭{line}╮{style.reset}\n"
        + row(title, style.bold)
        + row(subtitle, style.dim)
        + f"{style.cyan}╰{line}╯{style.reset}\n\n"
    )


# ----------------------------------------------------------------------
# Menü
# ----------------------------------------------------------------------

def select_menu(title, options, style, hint=None, default_index=0):
    """
    Ok tuşlarıyla gezilen tek seçimli menü.

    options: [{"label": str, "detail": str (ops.), "value": any}]
    default_index: açılışta seçili gelen öğe. Seçenekler mantıksal sırada
        dururken (ör. hızlıdan yavaşa) önerilen seçenek ortada olabilir.
    Döner: seçilen öğenin "value" alanı. İptalde None.
    """
    if not options:
        return None
    if len(options) == 1:
        _w(f"{style.bold}{title}{style.reset}\n")
        _w(f"  {style.green}▸{style.reset} {options[0]['label']} "
           f"{style.dim}(tek seçenek){style.reset}\n\n")
        return options[0]["value"]

    if not 0 <= default_index < len(options):
        default_index = 0

    if not supports_raw_input():
        return _numbered_fallback(title, options, style, default_index)

    index = default_index
    _w(f"{style.bold}{title}{style.reset}\n")
    if hint:
        _w(f"{style.dim}{hint}{style.reset}\n")
    _w(f"{style.dim}↑/↓ ile seç, Enter ile onayla{style.reset}\n\n")

    iptal = False
    hide_cursor()
    try:
        with raw_mode() as fd:
            _render_menu(options, index, style, first=True)
            while True:
                try:
                    key = read_key(fd)
                except KeyboardInterrupt:
                    iptal = True
                    break
                if key == "up":
                    index = (index - 1) % len(options)
                elif key == "down":
                    index = (index + 1) % len(options)
                elif key.isdigit() and 1 <= int(key) <= len(options):
                    index = int(key) - 1
                    _render_menu(options, index, style)
                    time.sleep(0.08)
                    break
                elif key == "enter":
                    break
                elif key in ("ctrl-c", "esc", "q", "ctrl-d"):
                    iptal = True
                    break
                else:
                    continue
                _render_menu(options, index, style)
    finally:
        show_cursor()

    _render_menu(options, index, style)
    _w("\n")
    return None if iptal else options[index]["value"]


def _render_menu(options, index, style, first=False):
    if not first:
        _w(f"\033[{len(options)}A")
    # Etiketler sabit genişliğe getirilir, böylece açıklamalar alt alta hizalanır.
    label_width = max(len(opt["label"]) for opt in options)
    for i, opt in enumerate(options):
        pad = " " * (label_width - len(opt["label"]))
        detail = opt.get("detail", "")
        detail = f"{pad}  {style.dim}{detail}{style.reset}" if detail else ""
        if i == index:
            _w(f"\r\033[K  {style.green}▸{style.reset} "
               f"{style.bold}{opt['label']}{style.reset}{detail}\n")
        else:
            _w(f"\r\033[K    {opt['label']}{detail}\n")


def _numbered_fallback(title, options, style, default_index=0):
    _w(f"{style.bold}{title}{style.reset}\n")
    label_width = max(len(opt["label"]) for opt in options)
    for i, opt in enumerate(options, start=1):
        pad = " " * (label_width - len(opt["label"]))
        detail = f"{pad}  {style.dim}{opt.get('detail', '')}{style.reset}" if opt.get("detail") else ""
        _w(f"  {style.cyan}{i}{style.reset}) {opt['label']}{detail}\n")
    default_no = default_index + 1
    while True:
        try:
            raw = input(f"Seçim [1-{len(options)}] (Enter = {default_no}): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw:
            raw = str(default_no)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            _w("\n")
            return options[int(raw) - 1]["value"]
        _w(f"{style.red}Geçersiz seçim.{style.reset}\n")


# ----------------------------------------------------------------------
# Metin giriş kutusu
# ----------------------------------------------------------------------

def input_box(title, style, placeholder="", hint=None):
    """
    Çerçeveli tek satırlık metin giriş kutusu. Boş girdi kabul edilmez.

    Ham kip yoksa düz `input()` kullanılır.
    """
    if not supports_raw_input():
        _w(f"\n{style.bold}{title}{style.reset}\n")
        if hint:
            _w(f"{style.dim}{hint}{style.reset}\n")
        while True:
            try:
                text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if text:
                return text
            _w(f"{style.red}Boş olamaz.{style.reset}\n")

    width = min(term_width() - 4, 68)
    inner = width - 2
    buffer = ""

    _w(f"\n{style.bold}{title}{style.reset}\n")
    if hint:
        _w(f"{style.dim}{hint}{style.reset}\n")
    _w(f"{style.dim}Enter ile başlat, Esc ile çık{style.reset}\n\n")

    top = f"{style.cyan}╭{'─' * inner}╮{style.reset}\n"
    bottom = f"{style.cyan}╰{'─' * inner}╯{style.reset}\n"
    _w(top)
    _w(f"{style.cyan}│{style.reset}{' ' * inner}{style.cyan}│{style.reset}\n")
    _w(bottom)

    try:
        with raw_mode() as fd:
            while True:
                # İmleci kutunun içine taşı ve satırı yeniden çiz
                _w("\033[2A\r")
                visible = buffer[-(inner - 3):] if len(buffer) > inner - 3 else buffer
                if visible:
                    content = f" {visible}"
                    dolgu = inner - 1 - len(visible)
                else:
                    ornek = placeholder[:inner - 3]
                    content = f" {style.dim}{ornek}{style.reset}"
                    dolgu = inner - 1 - len(ornek)
                _w(f"{style.cyan}│{style.reset}{content}{' ' * max(dolgu, 0)}"
                   f"{style.cyan}│{style.reset}\n")
                _w("\n")

                try:
                    key = read_key(fd)
                except KeyboardInterrupt:
                    _w("\n")
                    return None
                if key == "enter":
                    if buffer.strip():
                        _w("\n")
                        return buffer.strip()
                    continue
                if key in ("ctrl-c", "esc", "ctrl-d"):
                    _w("\n")
                    return None
                if key == "backspace":
                    buffer = buffer[:-1]
                elif len(key) == 1 and key.isprintable():
                    buffer += key
    finally:
        show_cursor()


def confirm(question, style, default=True):
    """Evet/hayır sorusu; ham kip yoksa input() ile sorar."""
    suffix = "[E/h]" if default else "[e/H]"
    if not supports_raw_input():
        try:
            raw = input(f"{question} {suffix} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if not raw:
            return default
        return raw in ("e", "evet", "y", "yes")

    _w(f"{question} {style.dim}{suffix}{style.reset} ")
    with raw_mode() as fd:
      while True:
        key = read_key(fd)
        if key in ("ctrl-c", "esc", "ctrl-d"):
            _w("\n")
            return False
        if key == "enter":
            _w("evet\n" if default else "hayır\n")
            return default
        low = key.lower()
        if low in ("e", "y"):
            _w("evet\n")
            return True
        if low == "h" or low == "n":
            _w("hayır\n")
            return False


# ----------------------------------------------------------------------
# Sağlayıcı tespiti ve başlatma
# ----------------------------------------------------------------------

def _http_get_json(url, timeout=2):
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _host():
    return os.environ.get("OLLAMA_HOST_IP") or "127.0.0.1"


def _lms_cli():
    for path in _LMS_CLI_CANDIDATES:
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    found = shutil.which("lms")
    return found


def ollama_running():
    return _http_get_json(f"http://{_host()}:{OLLAMA_PORT}/api/tags") is not None


def lm_studio_running():
    return _http_get_json(f"http://{_host()}:{LM_STUDIO_PORT}/v1/models") is not None


def ollama_installed():
    return shutil.which("ollama") is not None


def lm_studio_installed():
    return _lms_cli() is not None or Path("/Applications/LM Studio.app").exists()


def detect_providers():
    """Kurulu model sunucularını ve çalışma durumlarını döndürür."""
    providers = []
    if ollama_installed():
        providers.append({
            "key": "ollama", "name": "Ollama",
            "running": ollama_running(), "port": OLLAMA_PORT,
        })
    if lm_studio_installed():
        providers.append({
            "key": "lmstudio", "name": "LM Studio",
            "running": lm_studio_running(), "port": LM_STUDIO_PORT,
        })
    return providers


def start_provider(key, style):
    """
    Seçilen sağlayıcıyı başlatır ve API'si yanıt verene kadar bekler.

    Zaten çalışıyorsa hiçbir şey yapmaz. Başlatılamazsa False döner.
    """
    if key == "ollama":
        if ollama_running():
            return True
        _w(f"{style.dim}Ollama başlatılıyor...{style.reset} ")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, FileNotFoundError) as e:
            _w(f"{style.red}başarısız: {e}{style.reset}\n")
            return False
        return _wait_ready(ollama_running, style)

    if key == "lmstudio":
        if lm_studio_running():
            return True
        cli = _lms_cli()
        if not cli:
            _w(
                f"{style.yellow}LM Studio sunucusu kapalı ve 'lms' komutu yok."
                f"{style.reset}\n{style.dim}LM Studio uygulamasını açıp "
                f"Developer sekmesinden sunucuyu başlat.{style.reset}\n"
            )
            return False
        _w(f"{style.dim}LM Studio sunucusu başlatılıyor...{style.reset} ")
        try:
            subprocess.run(
                [cli, "server", "start"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            _w(f"{style.red}başarısız: {e}{style.reset}\n")
            return False
        return _wait_ready(lm_studio_running, style)

    return False


def _wait_ready(check_fn, style):
    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    deadline = time.monotonic() + SERVICE_START_TIMEOUT_SEC
    i = 0
    while time.monotonic() < deadline:
        if check_fn():
            _w(f"\r\033[K{style.green}✓{style.reset} sunucu hazır\n")
            return True
        _w(f"\r{style.dim}bekleniyor {spinner[i % len(spinner)]}{style.reset}")
        i += 1
        time.sleep(SERVICE_POLL_INTERVAL_SEC)
    _w(f"\r\033[K{style.red}✗ sunucu {SERVICE_START_TIMEOUT_SEC} saniyede "
       f"hazır olmadı{style.reset}\n")
    return False


def provider_models(key):
    """Seçilen sağlayıcıdaki modelleri listeler."""
    models = []
    if key == "ollama":
        data = _http_get_json(f"http://{_host()}:{OLLAMA_PORT}/api/tags", timeout=5)
        for m in (data or {}).get("models", []):
            name = m.get("name") or m.get("model")
            if not name:
                continue
            details = m.get("details") or {}
            models.append({
                "id": name,
                "source": "Ollama",
                "size_gb": round((m.get("size") or 0) / 1e9, 1),
                "detail": " ".join(
                    x for x in (details.get("parameter_size", ""),
                                details.get("quantization_level", "")) if x
                ),
            })
    elif key == "lmstudio":
        data = _http_get_json(f"http://{_host()}:{LM_STUDIO_PORT}/v1/models", timeout=5)
        for m in (data or {}).get("data", []):
            if m.get("id"):
                models.append({
                    "id": m["id"], "source": "LM Studio",
                    "size_gb": 0.0, "detail": "",
                })
    return models
