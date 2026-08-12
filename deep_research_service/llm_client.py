"""
LocoDex Deep Search — Ortak Lokal LLM İstemcisi

Ollama / LM Studio çağrı mantığını tek sınıfta toplar.

- Host çözümü sıralı dener: OLLAMA_HOST_IP env → host.docker.internal → localhost.
  Böylece aynı kod hem Docker container'ında hem doğrudan host üzerinde çalışır.
  DNS sorgusu event loop'u bloklamamak için thread'e alınır ve sonuç önbelleklenir.
- call_json(): Ollama'da format=json, LM Studio'da response_format ile
  garantili JSON istenir; model yine de bozuk çıktı verirse dengeli-parantez
  tabanlı kurtarma parser'ı devreye girer. Çıktı token limitine takılıp
  kesilirse yeniden deneme artırılmış limitle yapılır.
- Model sunucusuna hiçbir denemede erişilemezse LLMError yükseltilir;
  sessizce hata metni döndürülmez.
"""

import asyncio
import json
import logging
import os
import re
import socket

import aiohttp

try:
    from research_constants import TEMPERATURE_RESEARCH
except ImportError:
    from .research_constants import TEMPERATURE_RESEARCH

logger = logging.getLogger(__name__)

OLLAMA_PORT = 11434
LM_STUDIO_PORT = 1234
DEFAULT_TIMEOUT_SEC = 300
CONNECT_TIMEOUT_SEC = 5

_host_candidates_cache = None


def _resolve_host_candidates():
    """Model sunucusuna erişilebilecek host adaylarını sırayla döndürür (önbellekli)."""
    global _host_candidates_cache
    if _host_candidates_cache is not None:
        return _host_candidates_cache

    candidates = []
    env_host = os.environ.get("OLLAMA_HOST_IP")
    if env_host:
        candidates.append(env_host)
    try:
        candidates.append(socket.gethostbyname("host.docker.internal"))
    except (socket.gaierror, OSError):
        pass
    candidates.append("127.0.0.1")
    # Sırayı koruyarak tekrarları at
    seen = set()
    unique = []
    for host in candidates:
        if host not in seen:
            seen.add(host)
            unique.append(host)
    _host_candidates_cache = unique
    return unique


def _iter_balanced_blocks(text, open_ch, close_ch):
    """Metindeki tüm dengeli open/close bloklarını sırayla üretir."""
    search_from = 0
    while True:
        start = text.find(open_ch, search_from)
        if start == -1:
            return
        depth = 0
        in_string = False
        escape = False
        end = None
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            return
        yield text[start : end + 1]
        search_from = start + 1


def extract_json(text):
    """
    LLM çıktısından JSON nesnesi/dizisi kurtarır.

    Sırasıyla: doğrudan parse → markdown çiti → metindeki dengeli { } / [ ]
    blokları (ilki bozuksa sonrakiler de denenir) → sondaki gereksiz
    virgüller temizlenerek yeniden parse. Başarısızsa None döner.
    """
    if not text:
        return None

    def _try(s):
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return None

    result = _try(text.strip())
    if result is not None:
        return result

    # Markdown kod çitini soy
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        result = _try(fence.group(1).strip())
        if result is not None:
            return result
        text = fence.group(1)

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        for candidate in _iter_balanced_blocks(text, open_ch, close_ch):
            result = _try(candidate)
            if result is not None:
                return result
            # Sondaki gereksiz virgülleri temizle
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            result = _try(cleaned)
            if result is not None:
                return result

    # Çıktı token limitinde kesildiyse dengeli blok hiç bulunamaz. Bu durumda
    # tamamlanmış eleman sayısı kadarını kurtarmak, tüm turu boşa harcamaktan
    # iyidir: son tam elemandan sonrası atılır, açık yapılar kapatılır.
    repaired = _repair_truncated(text)
    if repaired is not None:
        result = _try(repaired)
        if result is not None:
            logger.warning("JSON çıktısı kesik geldi; tamamlanan kısım kurtarıldı")
            return result
    return None


def _repair_truncated(text):
    """
    Yarıda kesilmiş JSON metninden son tam elemana kadar olan kısmı onarır.

    Dizi içindeki eksik son eleman atılır, açık kalan parantezler kapatılır.
    Kurtarılacak tam eleman yoksa None döner.
    """
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        return None
    text = text[start:]

    stack = []
    in_string = False
    escape = False
    last_safe = None  # Bir dizi elemanının kapandığı son konum
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if stack and stack[-1] == "[":
                last_safe = i

    if last_safe is None:
        return None

    head = text[: last_safe + 1]
    # Kalan açık yapıları sırayla kapat
    open_stack = []
    in_string = False
    escape = False
    for ch in head:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            open_stack.append(ch)
        elif ch in "}]" and open_stack:
            open_stack.pop()

    closers = {"{": "}", "[": "]"}
    return head + "".join(closers[ch] for ch in reversed(open_stack))


class LLMError(Exception):
    """Model sunucusuna erişilemedi ya da geçersiz yanıt döndü."""

    def __init__(self, message, status=None, truncated=False):
        super().__init__(message)
        self.status = status
        self.truncated = truncated


class LocalLLMClient:
    """Ollama ve LM Studio için tek asenkron istemci."""

    def __init__(self, model_name, model_source="Ollama", timeout_sec=DEFAULT_TIMEOUT_SEC):
        self.model_name = model_name
        self.model_source = model_source
        self.timeout_sec = timeout_sec
        self._resolved_base = None  # (backend, host) — ilk başarılı uç nokta

    def _timeout(self):
        return aiohttp.ClientTimeout(total=self.timeout_sec, connect=CONNECT_TIMEOUT_SEC)

    async def _post(self, session, url, payload):
        async with session.post(url, json=payload, timeout=self._timeout()) as response:
            if response.status != 200:
                body = await response.text()
                raise LLMError(f"HTTP {response.status}: {body[:300]}", status=response.status)
            return await response.json()

    async def _call_ollama(self, session, host, prompt, system_prompt, max_tokens,
                           temperature, json_mode):
        url = f"http://{host}:{OLLAMA_PORT}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        data = await self._post(session, url, payload)
        text = (data.get("response") or "").strip()
        # Token limitine takılan JSON çıktısı parse edilemez; kesildiyse bildir
        if json_mode and data.get("done_reason") == "length":
            raise LLMError("Çıktı token limitinde kesildi", truncated=True)
        return text

    async def _call_lm_studio(self, session, host, prompt, system_prompt, max_tokens,
                              temperature, json_mode):
        url = f"http://{host}:{LM_STUDIO_PORT}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = await self._post(session, url, payload)
        except LLMError as e:
            # response_format'ı yalnızca istemci-hatası (eski sürüm şemayı
            # bilmiyor) durumunda düşür; 429/5xx gibi geçici hatalarda düşürme.
            if json_mode and e.status in (400, 404, 415, 422):
                payload.pop("response_format", None)
                data = await self._post(session, url, payload)
            else:
                raise
        try:
            choice = data["choices"][0]
            content = (choice["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LM Studio beklenmeyen yanıt şeması: {e}") from e
        if json_mode and choice.get("finish_reason") == "length":
            raise LLMError("Çıktı token limitinde kesildi", truncated=True)
        return content

    async def call(self, prompt, system_prompt="", max_tokens=3000,
                   temperature=TEMPERATURE_RESEARCH, json_mode=False):
        """
        Modeli çağırır, yanıt metnini döndürür. Tüm uç noktalar başarısız
        olursa LLMError fırlatır; çağıran taraf hatayı ayırt edebilir.
        """
        if self.model_source == "Ollama":
            backends = [self._call_ollama, self._call_lm_studio]
        elif self.model_source == "LM Studio":
            backends = [self._call_lm_studio, self._call_ollama]
        else:
            backends = [self._call_lm_studio, self._call_ollama]

        hosts = await asyncio.to_thread(_resolve_host_candidates)
        errors = []
        async with aiohttp.ClientSession() as session:
            # Daha önce çalışan uç nokta varsa önce onu dene
            if self._resolved_base is not None:
                backend, host = self._resolved_base
                try:
                    return await backend(session, host, prompt, system_prompt,
                                         max_tokens, temperature, json_mode)
                except LLMError as e:
                    if e.truncated:
                        raise
                    errors.append(f"{host}: {e}")
                    self._resolved_base = None
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                    errors.append(f"{host}: {e}")
                    self._resolved_base = None

            for backend in backends:
                for host in hosts:
                    try:
                        result = await backend(session, host, prompt, system_prompt,
                                               max_tokens, temperature, json_mode)
                        self._resolved_base = (backend, host)
                        return result
                    except LLMError as e:
                        if e.truncated:
                            # Sunucu çalışıyor ama çıktı kesildi; diğer uç
                            # noktaları denemek anlamsız, çağırana bildir.
                            self._resolved_base = (backend, host)
                            raise
                        errors.append(f"{backend.__name__}@{host}: {e}")
                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                        errors.append(f"{backend.__name__}@{host}: {e}")

        raise LLMError("Model sunucusuna erişilemedi: " + " | ".join(errors[-4:]))

    async def call_json(self, prompt, system_prompt="", max_tokens=2000,
                        temperature=0.1, retries=1):
        """
        JSON çıktı ister ve parse edilmiş Python nesnesi döndürür.

        - Parse hatası ya da kesilme durumunda artırılmış token limitiyle
          yeniden dener; yine olmazsa None döner.
        - Hiçbir denemede model sunucusuna ERİŞİLEMEDİYSE LLMError yükseltir
          (sunucu kapalıyken sessizce None dönüp "boş ama başarılı" sonuç
          üretilmesin diye).
        """
        connectivity_error = None
        any_response = False
        current_max_tokens = max_tokens
        for attempt in range(retries + 1):
            try:
                raw = await self.call(
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=current_max_tokens,
                    temperature=temperature,
                    json_mode=True,
                )
            except LLMError as e:
                if e.truncated:
                    any_response = True
                    current_max_tokens = min(current_max_tokens * 2, 8000)
                    logger.warning(
                        f"call_json çıktısı kesildi (deneme {attempt + 1}), "
                        f"limit {current_max_tokens} token'a yükseltildi"
                    )
                    continue
                connectivity_error = e
                logger.error(f"call_json LLM hatası (deneme {attempt + 1}): {e}")
                continue
            any_response = True
            parsed = extract_json(raw)
            if parsed is not None:
                return parsed
            # Parse hatası da kesilmeden kaynaklanabilir; limiti artırarak dene
            current_max_tokens = min(current_max_tokens * 2, 8000)
            logger.warning(
                f"call_json parse hatası (deneme {attempt + 1}), ham çıktı: {raw[:200]}"
            )
        if not any_response and connectivity_error is not None:
            raise connectivity_error
        return None
