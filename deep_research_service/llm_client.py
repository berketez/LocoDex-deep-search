"""
LocoDex Deep Search — Ortak Lokal LLM İstemcisi

Ollama / LM Studio çağrı mantığını tek sınıfta toplar.

- Host çözümü sıralı dener: OLLAMA_HOST_IP env → host.docker.internal → localhost.
  Böylece aynı kod hem Docker container'ında hem doğrudan host üzerinde çalışır.
  DNS sorgusu event loop'u bloklamamak için thread'e alınır ve sonuç önbelleklenir.
- Reasoning ("düşünen") modellerde düşünme zinciri varsayılan olarak KAPATILIR.
  Qwen3/DeepSeek-R1 türü modeller çıktı limitini önce düşünmeye harcar; kısa
  limitli JSON çağrılarında model tek karakter JSON yazamadan kesilir ve tüm
  çağrı boşa gider. Kapatma sunucuya göre değişir: Ollama'da `think`, LM
  Studio'da `reasoning_effort`. Sunucu alanı tanımıyorsa alan düşürülür ve bu
  durum önbelleğe alınır (her çağrıda tekrar denenmez).
- call_json(): Ollama'da format=json, LM Studio'da response_format ile
  garantili JSON istenir; model yine de bozuk çıktı verirse dengeli-parantez
  tabanlı kurtarma parser'ı devreye girer. Çıktı kesilse bile eldeki kısmi
  metinden kurtarma denenir; ancak kurtarılamazsa artırılmış limitle yeniden
  çağrı yapılır.
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
    from research_constants import LLM_MAX_OUTPUT_TOKENS, TEMPERATURE_RESEARCH
except ImportError:
    from .research_constants import LLM_MAX_OUTPUT_TOKENS, TEMPERATURE_RESEARCH

logger = logging.getLogger(__name__)

OLLAMA_PORT = 11434
LM_STUDIO_PORT = 1234
DEFAULT_TIMEOUT_SEC = 300
CONNECT_TIMEOUT_SEC = 5

# Sunucunun isteği reddettiği, ancak opsiyonel bir alanı düşürerek kurtarmanın
# mümkün olduğu durumlar. 429/5xx gibi geçici hatalar bu sete dahil DEĞİLDİR:
# onlarda alan düşürmek hatayı maskeler.
CLIENT_ERROR_STATUSES = (400, 404, 415, 422)

# Reasoning modellerinin düşünme bloğu. Ollama bunu content içinde döndürür;
# LM Studio ayrı `reasoning_content` alanına koyar.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)


def _strip_reasoning(text):
    """
    Reasoning modellerinin <think> bloklarını metinden temizler.

    Kapanmış bloklar atılır. Kapanmamış blok, çıktının düşünme sırasında
    kesildiği anlamına gelir; o noktadan sonrası JSON içermez, atılır.
    """
    if not text:
        return text
    text = _THINK_BLOCK_RE.sub("", text)
    match = None
    for match in _THINK_OPEN_RE.finditer(text):
        pass
    if match is not None:
        text = text[: match.start()]
    return text.strip()

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

    Sırasıyla: reasoning bloğu soyma → doğrudan parse → markdown çiti →
    metindeki dengeli { } / [ ] blokları (ilki bozuksa sonrakiler de denenir)
    → sondaki gereksiz virgüller temizlenerek yeniden parse. Başarısızsa
    None döner.
    """
    if not text:
        return None

    # Düşünme zinciri JSON'dan önce gelir ve içinde örnek JSON parçaları
    # bulunabilir; soyulmazsa yanlış nesne kurtarılır.
    text = _strip_reasoning(text)
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
                # Doğrudan dizi içindeki string eleman tamamlandı. Bu kontrol
                # olmadan ["a", "b şeklinde kesilen string dizileri hiç
                # kurtarılamaz — alt_sorular/anahtar_terimler tam bu biçimdedir.
                if stack and stack[-1] == "[":
                    last_safe = i
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
        elif ch == "," and stack and stack[-1] == "[":
            # Virgül, dizideki bir elemanın (sayı, true/false dahil) bittiğini
            # gösterir; string ve nesne dışındaki türleri de kurtarır.
            if last_safe is None or last_safe < i - 1:
                last_safe = i - 1

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

    def __init__(self, message, status=None, truncated=False, partial=""):
        super().__init__(message)
        self.status = status
        self.truncated = truncated
        # Kesilen çağrıda modelin o ana kadar ürettiği metin. Tamamlanmış
        # kısım kurtarılabilirse yeniden çağrıya gerek kalmaz.
        self.partial = partial or ""


class LocalLLMClient:
    """Ollama ve LM Studio için tek asenkron istemci."""

    def __init__(self, model_name, model_source="Ollama", timeout_sec=DEFAULT_TIMEOUT_SEC,
                 enable_thinking=False):
        self.model_name = model_name
        self.model_source = model_source
        self.timeout_sec = timeout_sec
        # Düşünme zinciri varsayılan olarak kapalı: araştırma pipeline'ının
        # çağrıları şeması belli yapılandırılmış çıktı ister, düşünme yalnızca
        # çıktı limitini tüketir. Kaliteli sentez için açılabilir.
        self.enable_thinking = enable_thinking
        self._resolved_base = None  # (backend, host) — ilk başarılı uç nokta
        # Sunucunun kabul etmediği opsiyonel alanlar. Bir kez öğrenilir, sonraki
        # çağrılarda hiç gönderilmez (aksi halde her JSON çağrısı 2 HTTP isteği
        # eder; sunucunun tanımadığı bir alan her çağrıda bu bedeli öder).
        self._unsupported = set()

    def _timeout(self):
        return aiohttp.ClientTimeout(total=self.timeout_sec, connect=CONNECT_TIMEOUT_SEC)

    async def _post(self, session, url, payload):
        async with session.post(url, json=payload, timeout=self._timeout()) as response:
            if response.status != 200:
                body = await response.text()
                raise LLMError(f"HTTP {response.status}: {body[:300]}", status=response.status)
            return await response.json()

    async def _post_optional(self, session, url, payload, optional_fields):
        """
        İsteği gönderir; sunucu opsiyonel bir alanı tanımıyorsa o alanı
        düşürüp yeniden dener ve durumu önbelleğe alır.

        Yalnızca istemci-hatası kodlarında düşürür. Düşürme sırası
        optional_fields sırasıdır: önce vazgeçmesi en ucuz olan alan.
        """
        remaining = [f for f in optional_fields if f in payload]
        while True:
            try:
                return await self._post(session, url, payload)
            except LLMError as e:
                if e.status not in CLIENT_ERROR_STATUSES or not remaining:
                    raise
                dropped = remaining.pop(0)
                payload.pop(dropped, None)
                self._unsupported.add(dropped)
                logger.debug(f"Sunucu '{dropped}' alanını kabul etmedi, düşürüldü")

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
        if not self.enable_thinking and "think" not in self._unsupported:
            payload["think"] = False
        data = await self._post_optional(session, url, payload, ("think",))
        text = (data.get("response") or "").strip()
        # Ollama düşünme zincirini ayrı alanda döndürebilir. Yalnızca yanıt
        # tamamlandığında okunur; kesik düşünmeden JSON kurtarmak yanlış veri
        # üretir (bkz. _call_lm_studio'daki aynı gerekçe).
        if not text and data.get("done_reason") != "length":
            text = (data.get("thinking") or "").strip()
        text = _strip_reasoning(text)
        # Token limitine takılan çıktı eksiktir; eldeki kısmı çağırana taşı ki
        # tamamlanmış bölüm kurtarılabilsin.
        if data.get("done_reason") == "length":
            raise LLMError("Çıktı token limitinde kesildi", truncated=True, partial=text)
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
        if json_mode and "response_format" not in self._unsupported:
            payload["response_format"] = {"type": "json_object"}
        if not self.enable_thinking:
            # LM Studio'nun MLX motorunda düşünmeyi kapatan alan
            # reasoning_effort'tur. chat_template_kwargs, prompt'a /no_think
            # eklemek ve reasoning.enabled sessizce yok sayılır: alan kabul
            # edilmiş görünür ama üretilen tokenların tamamı düşünmeye gider.
            # chat_template_kwargs yine de gönderilir: llama.cpp motorunda ve
            # bazı sürümlerde şablona geçirilen alan odur.
            if "reasoning_effort" not in self._unsupported:
                payload["reasoning_effort"] = "none"
            if "chat_template_kwargs" not in self._unsupported:
                payload["chat_template_kwargs"] = {"enable_thinking": False}
        # Düşürme sırası önemli: önce yalnızca biçim garantisi olan alanlar
        # (kayıpları kurtarma parser'ıyla telafi edilebilir), düşünmeyi kapatan
        # reasoning_effort en sona bırakılır.
        data = await self._post_optional(
            session, url, payload,
            ("response_format", "chat_template_kwargs", "reasoning_effort"),
        )
        try:
            choice = data["choices"][0]
            message = choice["message"] or {}
            content = (message.get("content") or "").strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LM Studio beklenmeyen yanıt şeması: {e}") from e
        finish_reason = choice.get("finish_reason")
        # Yanıt TAMAMLANDIYSA ve içerik boşsa, model cevabı düşünme alanında
        # bitirmiş olabilir; oradan okumak güvenlidir. Yanıt KESİLDİYSE değildir:
        # düşünme henüz cevaba varmamıştır ve aradaki taslak JSON ("belki şöyle
        # olabilir...") gerçek cevap sanılarak sessizce yanlış veri üretir.
        if not content and finish_reason != "length":
            content = (message.get("reasoning_content") or "").strip()
        content = _strip_reasoning(content)
        if finish_reason == "length":
            raise LLMError("Çıktı token limitinde kesildi", truncated=True, partial=content)
        return content

    @staticmethod
    def _on_truncated(error, json_mode):
        """
        Kesilen çağrıyı moda göre ele alır.

        JSON modunda eksik çıktı çoğu zaman parse edilemez; hata yukarı taşınır
        ve call_json önce kurtarmayı, olmazsa artırılmış limitle yeniden
        çağrıyı dener. Serbest metinde ise yarım çıktı da kullanılabilir —
        atmak yerine uyarıyla döndürülür.
        """
        if json_mode:
            raise error
        logger.warning(
            "Çıktı token limitinde kesildi; kısmi metin kullanılıyor "
            f"({len(error.partial)} karakter)"
        )
        return error.partial

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
                        return self._on_truncated(e, json_mode)
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
                            # noktaları denemek anlamsız.
                            self._resolved_base = (backend, host)
                            return self._on_truncated(e, json_mode)
                        errors.append(f"{backend.__name__}@{host}: {e}")
                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                        errors.append(f"{backend.__name__}@{host}: {e}")

        raise LLMError("Model sunucusuna erişilemedi: " + " | ".join(errors[-4:]))

    async def call_json(self, prompt, system_prompt="", max_tokens=2000,
                        temperature=0.1, retries=1):
        """
        JSON çıktı ister ve parse edilmiş Python nesnesi döndürür.

        - Çıktı kesilirse önce eldeki kısmi metinden kurtarma denenir; bu
          başarılıysa yeni çağrı yapılmaz. Kurtarılamazsa limit artırılarak
          yeniden denenir (tavan: LLM_MAX_OUTPUT_TOKENS).
        - Hiçbir denemede model sunucusuna ERİŞİLEMEDİYSE LLMError yükseltir
          (sunucu kapalıyken sessizce None dönüp "boş ama başarılı" sonuç
          üretilmesin diye).
        """
        connectivity_error = None
        any_response = False
        current_max_tokens = max_tokens
        last_attempt = retries

        def _raise_limit(attempt, reason):
            """Kalan deneme varsa limiti büyütür; yoksa yanıltıcı log basmaz."""
            nonlocal current_max_tokens
            if attempt >= last_attempt:
                logger.warning(f"call_json {reason} (deneme {attempt + 1}), deneme hakkı bitti")
                return
            current_max_tokens = min(current_max_tokens * 2, LLM_MAX_OUTPUT_TOKENS)
            logger.warning(
                f"call_json {reason} (deneme {attempt + 1}), "
                f"limit {current_max_tokens} token'a yükseltildi"
            )

        for attempt in range(last_attempt + 1):
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
                    # Kesik de olsa gelen metinde tamamlanmış bölüm olabilir;
                    # kurtarılırsa yeni çağrı (ve yeni bekleme) gerekmez.
                    parsed = extract_json(e.partial)
                    if parsed is not None:
                        logger.warning("Çıktı kesildi; tamamlanan kısım kurtarıldı")
                        return parsed
                    _raise_limit(attempt, "çıktısı kesildi")
                    continue
                connectivity_error = e
                logger.error(f"call_json LLM hatası (deneme {attempt + 1}): {e}")
                continue
            any_response = True
            parsed = extract_json(raw)
            if parsed is not None:
                return parsed
            # Parse hatası da kesilmeden kaynaklanabilir; limiti artırarak dene
            _raise_limit(attempt, f"parse hatası, ham çıktı: {raw[:200]}")
        if not any_response and connectivity_error is not None:
            raise connectivity_error
        return None
