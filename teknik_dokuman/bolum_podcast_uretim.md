# KONU 3: Podcast Uretim Sistemi (TTS Pipeline)

## 3.1 Text-to-Speech (TTS) Temelleri

### 3.1.1 Mel Spectrogram: Frekans -> Mel Olcegi Donusumu

Insan kulagI frekanslari lineer degil, logaritmik algilar. 100 Hz ile 200 Hz arasindaki fark, 5000 Hz ile 5100 Hz arasindaki farktan cok daha belirgindir. Mel olcegi bu algisal farkliligi modellemek icin gelistirilmistir (Stevens, Volkmann & Newman, 1937).

**Mel donusum formulu:**

```
mel(f) = 2595 * log_10(1 + f/700)
```

**Turetme:**

Bu formul semiempirik'tir -- psikofiziksel deneylerden turetilmistir. Temel mantik:

1. Dusuk frekanslarda (f << 700 Hz), log_10(1+f/700) ~ f/(700*ln(10)), yani mel olcegi yaklasik lineer.

2. Yuksek frekanslarda (f >> 700 Hz), log_10(1+f/700) ~ log_10(f/700), yani mel olcegi yaklasik logaritmik.

3. Gecis bolgesI f ~ 700 Hz civarindadir. Bu, insan konusma sesinin temel frekans araligi ile uyumludur (erkek sesi ~85-180 Hz, kadin sesi ~165-255 Hz, formant frekanslari 300-3000 Hz).

**Ters donusum:**

```
f = 700 * (10^(mel/2595) - 1)
```

**Sayisal ornekler:**

| Frekans (Hz) | Mel Degeri | Yorum |
|-------------|-----------|-------|
| 0 | 0.000 | Sessizlik |
| 100 | 150.5 | Derin erkek sesi |
| 200 | 283.2 | Orta erkek sesi |
| 440 | 549.6 | A4 nota (la) |
| 700 | 781.9 | Referans frekans |
| 1000 | 999.9 | ~1000 mel (neredeyse lineer!) |
| 2000 | 1521.0 | Konusma formant bolgesinin ustu |
| 4000 | 2146.1 | |
| 8000 | 2840.0 | |
| 16000 | 3508.5 | Insan duyma siniri civari |
| 22050 | 3815.0 | Nyquist (44100 Hz icin) |

Dikkat: 0-1000 Hz arasindaki 1000 Hz'lik aralik ~1000 mel'e karsilik gelirken, 8000-16000 Hz arasindaki 8000 Hz'lik aralik sadece ~668 mel'e karsilik gelir. Bu, kulaginiza dusuk frekanslarin daha "onemli" oldugunu gosterir.

### Mel Filterbank

Mel spectrogram olusturmak icin:

1. Ses sinyaline Short-Time Fourier Transform (STFT) uygula
2. Guc spektrumunu hesapla: |STFT(x)|^2
3. Mel filterbank ile filtrele: N adet ucgensel filtre, mel olceginde esit aralikli
4. Her filtrenin ciktisini log olcege donustur

```
Mel_spectrogram[n][t] = log(sum_f (H_n(f) * |STFT(x, t, f)|^2))

burada H_n(f) = n. mel filtre fonksiyonu (ucgensel)
```

Tipik parametreler:
- N = 80 mel filtre (Cartesia Sonic icin tipik)
- STFT window = 1024 sample (23.2ms @ 44100 Hz)
- Hop length = 256 sample (5.8ms @ 44100 Hz)
- Frekans araligi: 0 - 22050 Hz (Nyquist)

### 3.1.2 WaveNet / Vocoder: Autoregressive Audio Generation

Klasik TTS pipeline:

```
Text -> Linguistic Features -> Acoustic Model -> Mel Spectrogram -> Vocoder -> Waveform
```

**WaveNet (DeepMind, 2016):**

Autoregressive model: her ses orneglemi onceki orneklerden uretilir.

```
P(x_1, x_2, ..., x_T) = prod_{t=1}^{T} P(x_t | x_1, ..., x_{t-1})
```

WaveNet dilated causal convolution kullanir:

```
y_t = sum_{k=0}^{K-1} w_k * x_{t - d*k}

burada d = dilation factor (1, 2, 4, 8, 16, ...)
```

Dilation sayesinde receptive field ustel olarak buyur:
```
Receptive_field = K * sum_{l=0}^{L-1} 2^l = K * (2^L - 1)

K=2, L=10: RF = 2 * 1023 = 2046 sample = 46.4ms @ 44100 Hz
```

**Modern Vocoderlar:**
- HiFi-GAN: GAN-based, real-time
- VITS: end-to-end (text -> waveform)
- Cartesia Sonic: neural TTS (LocoDex'te kullanilan)

---

## 3.2 Cartesia Sonic Model ve LocoDex Entegrasyonu

### Koddaki Uygulama

`podcast.py` (L36-55):

```python
def _generate_audio_segment(text: str, voice: str) -> bytes:
    url = "https://api.together.ai/v1/audio/generations"
    data = {
        "input": "-" + text,    # Kisa duraklama icin tire ekleme
        "voice": voice,
        "response_format": "mp3",
        "sample_rate": 44100,
        "stream": False,
        "model": "cartesia/sonic",
    }
    response = requests.post(url, headers=headers, json=data)
    return response.content
```

### Voice Embedding Space

Neural TTS modelleri ses karakteristigini bir "embedding vector" olarak temsil eder.

```
voice_embedding = f: Voice -> R^d

burada d = embedding boyutu (tipik olarak 128-512)
```

LocoDex'te iki ses kullanilir:
```python
AVAILABLE_VOICES = [
    "laidback woman",       # Host icin
    "customer support man",  # Guest icin
]
```

Bu isimler, Cartesia'nin onces tanimlanmis voice embedding'lerine karsilik gelir. Her ses embedding, su akustik ozellikleri kodlar:
- Pitch (ses perdesi): temel frekans F0
- Timbre (tini): formant yapisI
- Speaking rate (konusma hizi)
- Prosody (vurgu/tonlama kaliplari)

### Host/Guest Voice Modelleme

Podcast formatinda iki farkli sesin olmasi **kontrast** saglar:

1. **Frekans ayrisimi:** Host (kadin, ~200-300 Hz F0) vs Guest (erkek, ~100-200 Hz F0). Farkli frekans bantlari kullagIn ayrimini kolaylastirir.

2. **Temporal interleaving:** Konusmacilarin sirali degismesi (turn-taking), dinleyicinin "kim konusuyor" sorusunu otomatik cevaplar.

Koddaki ses atama (podcast.py L81):
```python
voice = script.host_voice if line.speaker == "Host" else script.guest_voice
```

---

## 3.3 Script Generation: LLM Dialogue Creation

### Pydantic Schema Validation

podcast.py Pydantic modelleri kullanarak LLM ciktisini yapisal olarak kisitlar:

```python
class LineItem(BaseModel):
    speaker: Literal["Host", "Guest"]
    text: str

class Script(BaseModel):
    script_data: List[LineItem]
```

LLM cagrisi (L110-118):
```python
response = single_shot_llm_call(
    model="together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    system_prompt=system_prompt,
    message=input_text,
    response_format={
        "type": "json_object",
        "schema": Script.model_json_schema(),
    },
)
llm_script = Script.model_validate_json(response)
```

### Schema'nin JSON Karsiligi

`Script.model_json_schema()` su JSON Schema'yi uretir:

```json
{
  "title": "Script",
  "type": "object",
  "properties": {
    "script_data": {
      "title": "Script Data",
      "type": "array",
      "items": {
        "title": "LineItem",
        "type": "object",
        "properties": {
          "speaker": {
            "title": "Speaker",
            "enum": ["Host", "Guest"],
            "type": "string"
          },
          "text": {
            "title": "Text",
            "type": "string"
          }
        },
        "required": ["speaker", "text"]
      }
    }
  },
  "required": ["script_data"]
}
```

Bu, LLM'in ciktisini su formata zorlar:
```json
{
  "script_data": [
    {"speaker": "Host", "text": "Bugun AI'yi konusacagiz."},
    {"speaker": "Guest", "text": "Harika bir konu!"},
    ...
  ]
}
```

**Neden Pydantic?**

1. **Type safety:** `speaker` sadece "Host" veya "Guest" olabilir. LLM "Moderator" veya "Speaker1" yazamaz.
2. **Validation:** `model_validate_json()` invalid JSON'u reddeder, `ValidationError` firlatir.
3. **Schema generation:** `model_json_schema()` otomatik olarak JSON Schema uretir, manuel yazmaya gerek yok.

### Speaker Alternation: Turn-Taking Modeli

Ideal bir podcast diyalogunda konusmaci degisimleri su kaliplari izler:

**Adjacency pairs (bitisik ciftler):**
```
Host: Soru  -> Guest: Cevap
Guest: Iddia -> Host: Yorum/Soru
Host: Ozet  -> Guest: Onay/Duzeltme
```

Bu, conversation analysis literaturundeki Schegloff & Sacks (1973) modeline dayanir.

**Ortalama turn uzunlugu:**

Podcast icin tipik degerler:
- Host turn: 15-30 kelime (soru veya yonlendirme)
- Guest turn: 30-80 kelime (aciklama veya detay)
- Toplam turn sayisi: arasstirma icerik uzunluguna bagimli (~20-40 turn)

**Alternation entropy:**

Konusmaci sirasinin ne kadar "duzenli" oldugunu olcmek icin:

```
P(Host->Guest) = p, P(Guest->Host) = q

Ideal podcast: p ~ 0.8, q ~ 0.8 (cogunlukla degisimli)
Monoton: p ~ 0.5, q ~ 0.5 (rastgele)
Tek kisitli: p ~ 1.0 (Host hep Guest'e verir ama Guest bazen devam eder)
```

Shannon entropy:
```
H = -p*log2(p) - (1-p)*log2(1-p)

p=0.8: H = -0.8*(-0.322) - 0.2*(-2.322) = 0.258 + 0.464 = 0.722 bit
p=0.5: H = 1.0 bit (maximum belirsizlik)
```

Dusuk entropy = daha on gorulebilir = daha iyi podcast akisi.

---

## 3.4 Audio Segment Concatenation

### MP3 Bytearray Birlestirme

podcast.py L78-85:

```python
audio_data = bytearray()
for line in script.dialogue:
    voice = script.host_voice if line.speaker == "Host" else script.guest_voice
    segment_audio = _generate_audio_segment(line.text, voice)
    audio_data.extend(segment_audio)
return bytes(audio_data)
```

**Neden bytearray?**

`bytearray` mutable'dir, `bytes` ise immutable. Her `extend()` operasyonu O(k) (k = eklenen bytes sayisi). N segment icin:

```
T_concat = sum_{i=1}^{N} O(k_i) = O(K_total)
    K_total = toplam audio bytes
```

Alternatif: `b"".join(segments)` -- bu da O(K_total) ama tek seferde allocation yapar, daha verimli olabilir.

**KRITIK SORUN: MP3 frame boundary'leri**

MP3 dosyalarini bitistirmek (concatenation) her zaman dogru calismaz. Her MP3 frame kendi header'ina sahiptir:

```
MP3 Frame Yapisi:
[Sync Word: 12 bit] [Version: 2 bit] [Layer: 2 bit] [Bitrate: 4 bit] [Sample Rate: 2 bit] ...
[Audio Data: degisken]
```

Iki MP3 dosyasini bitistirdiginde:
- Frame header'lari dogru sekilde hizalanmis olabilir (sans)
- Veya frame ortasindan kesilip yanlis decode edilebilir (hata)

Pratikte cogu MP3 decoder toleranslidir ve frame sync word'u arar, ama gapless playback garanti degildir. Kisa sessizlikler veya "click" sesleri duyulabilir.

**Daha iyi yontem:** Her segment'i ayri tutup ffmpeg ile birlestirmek:
```bash
ffmpeg -i "concat:seg1.mp3|seg2.mp3|..." -c copy output.mp3
```

Veya PCM'e donusturup birlestirip tekrar encode etmek.

### 3.4.1 Sample Rate: 44100 Hz ve Nyquist Teoremi

**Nyquist-Shannon Ornekleme Teoremi (1928/1949):**

Bir surekli sinyali tamamen geri kazanabilmek icin:

```
f_sample >= 2 * f_max
```

burada f_max, sinyaldeki en yuksek frekans bilesendir.

**Turetme:**

Bu teoremin sezgisel anlami: bir sinyali orneklerken, her dalga periyodunda en az 2 ornek alinmalidir. 1 ornek dalganin "var" oldugunu, 2. ornek dalganin "yone" ait oldugunu belirler.

Formal turetme, Whittaker-Shannon interpolation formuluyle yapilir:

```
x(t) = sum_{n=-inf}^{inf} x[n] * sinc(f_s * t - n)

burada sinc(x) = sin(pi*x) / (pi*x)
```

Bu formul, sadece f_max < f_s/2 kosulu saglandiginda dogru sonuc verir.

**Neden 44100 Hz?**

Insan kulagI 20 Hz - 20000 Hz arasini duyabilir (ideal sartlar). Nyquist'e gore:

```
f_sample >= 2 * 20000 = 40000 Hz (minimum)
```

Neden tam 44100?

1. CD standardi 1979'da belirlendi (Sony/Philips).
2. O donemde video tape'e digital kayit yapiliyordu.
3. PAL video: 294 satir * 50 fps * 3 ornek/satir = 44100
4. NTSC video: 245 satir * 60 fps * 3 ornek/satir = 44100

Bu sayinin hem PAL hem NTSC ile uyumlu olmasi tesaduf degildir -- muhendislik karari.

```
f_nyquist = 44100 / 2 = 22050 Hz

Bu, 20000 Hz'lik insan isitme sinirinin %10 ustundedir.
Ekstra %10 = anti-aliasing filtre icin headroom.
```

**LocoDex'teki kullanim:**

podcast.py L49: `"sample_rate": 44100`

Konusma sesi icin 44100 Hz overkill'dir. Konusma sesi ~8000 Hz'in altinda yogunlasir:
- Temel frekans (F0): 85-255 Hz
- Formantlar (F1-F3): 300-3000 Hz
- Susturucular (s, sh, f): 4000-8000 Hz

Bu nedenle 16000 Hz sample rate konusma icin yeterlidir (Nyquist: f_max=8000 Hz). 44100 Hz kullanmak dosya boyutunu 2.75x artirir. Ancak MP3 sikistirma bunu telafi eder.

---

## 3.5 PCM -> WAV Donusumu: ffmpeg Pipeline

### PCM Format

podcast.py L153-182:

```python
def pcm_to_wav_bytes(pcm_data, sample_rate=44100):
    cmd = [
        "ffmpeg",
        "-y",                   # Overwrite
        "-f", "f32le",          # Input: 32-bit float, little-endian
        "-ar", str(sample_rate), # Sample rate
        "-ac", "1",             # Mono (1 kanal)
        "-i", pcm_file.name,    # Input file
        wav_file.name           # Output file
    ]
```

**PCM (Pulse Code Modulation):**

Analog sesin dijitale donusturuldugu en temel format. Her ornek, o andaki ses dalga genliginin sayisal karsilgidir.

```
Analog sinyal: x(t) surekli fonksiyon
Ornekleme:     x[n] = x(n * T_s), T_s = 1/f_s
Kuantalama:    x_q[n] = round(x[n] * 2^(b-1)) / 2^(b-1)
    burada b = bit derinligi
```

**Float32le formati:**

- float32 = 32-bit IEEE 754 floating point
- le = little-endian (dusuk byte'lar once)
- Deger araligi: [-1.0, +1.0] (normalize edilmis)
- Dinamik aralik: ~1530 dB (pratikte ~144 dB SNR)

Karsilastirma:
```
int16 (CD kalitesi): 2^16 = 65536 seviye, SNR = 6.02*16 + 1.76 = 98.1 dB
int24 (stüdyo):      2^24 = 16.7M seviye, SNR = 6.02*24 + 1.76 = 146.2 dB
float32:             ~2^24 mantissa, SNR ~ 144 dB (int24'e yakin ama farkli)
```

### WAV Format

WAV = RIFF container + PCM data. Header yapisi:

```
Offset  Boyut  Aciklama
0       4      "RIFF" (ASCII)
4       4      Dosya boyutu - 8 (little-endian)
8       4      "WAVE" (ASCII)
12      4      "fmt " (format chunk)
16      4      Format chunk boyutu (16 for PCM)
20      2      Audio format (1 = PCM)
22      2      Kanal sayisi (1 = mono, 2 = stereo)
24      4      Sample rate (44100)
28      4      Byte rate (sample_rate * channels * bits/8)
32      2      Block align (channels * bits/8)
34      2      Bits per sample (16, 24, 32)
36      4      "data"
40      4      Data chunk boyutu
44      ...    [PCM data baslar]
```

**Sayisal ornek:** 1 saniyelik mono float32 @ 44100 Hz:

```
Data boyutu = 44100 samples * 4 bytes/sample * 1 kanal = 176400 bytes
Header = 44 bytes
Toplam WAV boyutu = 176444 bytes ~ 172 KB

1 dakikalik podcast: 172 KB * 60 = 10.3 MB (sikistirilmamis)
```

### ffmpeg Pipeline

ffmpeg doneusumu su asamalardan gecer:

```
float32le PCM -> Demux -> Decode (identity) -> Resample? -> Encode (PCM int16) -> Mux (WAV)
```

ffmpeg burada cok az is yapar: float32 -> int16 donusumu + WAV header ekleme. Bu O(N) islem (N = sample sayisi).

---

## 3.6 Base64 Encoding: Binary -> Text Donusumu

### Koddaki Uygulama

podcast.py L185-196:

```python
def get_base64_audio(audio_bytes: bytes) -> str:
    encoded = base64.b64encode(audio_bytes).decode('utf-8')
    return f"data:audio/mp3;base64,{encoded}"
```

### Base64 Algoritmasi

Base64, 6-bit gruplama kullanir:

```
Girdi:  8-bit byte'lar (0-255)
Cikti:  6-bit karakterler (A-Z, a-z, 0-9, +, /) = 64 karakter

3 byte (24 bit) -> 4 karakter (24 bit)
```

**Encode sureci:**

```
Girdi: 3 byte = b1, b2, b3 (her biri 8 bit)

Birlestir: 24-bit deger = b1<<16 | b2<<8 | b3

Bol: 4 adet 6-bit deger:
  c1 = (24-bit >> 18) & 0x3F
  c2 = (24-bit >> 12) & 0x3F
  c3 = (24-bit >> 6) & 0x3F
  c4 = (24-bit >> 0) & 0x3F

Lookup tablosu ile karakter donusumu:
  0-25  -> A-Z
  26-51 -> a-z
  52-61 -> 0-9
  62    -> +
  63    -> /
```

**Boyut artisi:**

```
3 byte girdi -> 4 byte cikti (ASCII)
Oran = 4/3 = 1.333... = %33.3 artis
```

Padding: Eger girdi 3'un kati degilse "=" karakteri eklenir:
- 1 byte kaldi: 2 base64 char + "=="
- 2 byte kaldi: 3 base64 char + "="

**Sayisal ornek:** 1 dakikalik MP3 podcast (MP3 bitrate = 128 kbps):

```
MP3 boyutu = 128000 bits/sec * 60 sec / 8 = 960000 bytes = 937.5 KB

Base64 boyutu = 960000 * 4/3 = 1280000 bytes = 1250 KB = 1.22 MB

Artis = 1.22 - 0.94 = 0.28 MB (%33)
```

10 dakikalik podcast icin:
```
MP3: 9.375 MB
Base64: 12.5 MB
```

### Neden Base64?

HTML icine gomme (data URI scheme) icin binary veriler text'e donusturulmek zorunda. podcast.py L196:

```python
return f"data:audio/mp3;base64,{encoded}"
```

Bu, `<audio src="data:audio/mp3;base64,..." />` olarak HTML'e gomulur. Avantaj: ayri dosya gerektirmez, tek HTML dosyasinda her sey var. Dezavantaj: %33 boyut artisi + browser bellek kullanimi (12 MB audio data DOM'da tutulur).

**Alternatifler:**

| Yontem | Boyut Artisi | Uyumluluk | Ayri Dosya? |
|--------|-------------|-----------|-------------|
| Base64 data URI | %33 | Evrensel | Hayir |
| Blob URL | %0 | Modern browser | Hayir (bellekte) |
| Ayri MP3 dosyasi | %0 | Evrensel | Evet |
| Base85 encoding | %25 | Sinirli | Hayir |

generation.py'deki HTML raporda (L397-402) audio gomme:

```python
f'<audio controls>'
f'<source src="{base64_audio}" type="audio/mp3">'
```

---

## 3.7 Full Pipeline Ozeti

```
Arastirma Raporu (Markdown text)
        |
        v
[generate_podcast_script()]
  LLM Cagri: text -> JSON (Pydantic validated)
  Cikti: PodcastScript (title, host_voice, guest_voice, dialogue[])
        |
        v
[generate_podcast_audio()]
  Her dialogue satiri icin:
    [_generate_audio_segment()]
      Cartesia Sonic API -> MP3 bytes
  bytearray.extend() ile birlestirme
  Cikti: bytes (raw MP3 concatenation)
        |
        v
[get_base64_audio()]
  base64.b64encode() -> "data:audio/mp3;base64,..."
        |
        v
HTML rapora gomme (<audio> tag)
```

### Pipeline Zaman Analizi

| Asama | Sure (tahmin) | I/O Bound? |
|-------|--------------|------------|
| Script generation | 10-30s | Network (LLM API) |
| Audio generation (per segment) | 1-3s | Network (TTS API) |
| Audio generation (30 segment) | 30-90s | Network |
| Base64 encoding | < 0.1s | CPU |
| HTML gomme | < 0.01s | CPU |
| **TOPLAM** | **40-120s** | |

Darbogaz: TTS API cagrilari. Her segment seri olarak uretilir. Paralellestirme (asyncio.gather) ile 3-5x hizlanma mumkun ama API rate limiting bunu sinirlar.

---

## 3.8 Sinirlamalar

1. **MP3 concatenation sorunu:** Frame boundary hizalamasI garanti degil. Kisa click'ler veya bosluklar olusabilir.

2. **Seri segment uretimi:** Her dialogue satiri icin ayri API cagri. 30 satirlik podcast icin 30 HTTP request.

3. **Sabit ses secenekleri:** Sadece 2 ses var ("laidback woman", "customer support man"). Ses cesitliligi sinirli.

4. **Prozodia kontrolu yok:** Vurgu, tonlama, duraklama LLM tarafindan metin uzerinden kontrol edilir (ornegin "-" ekleyerek duraklama), ama native prosody kontrolu yok.

5. **Base64 boyut artisi:** %33 ek boyut. Uzun podcastlerde HTML dosyasi cok buyuyebilir (10 dk podcast icin 12 MB data URI).

6. **Sample rate overkill:** 44100 Hz konusma icin gereksiz yuksek. 16000 Hz yeterli olur ve dosya boyutunu %64 azaltir.

7. **Mono cikti:** Stereo kanal kullanilmiyor. Stereo panning ile Host sol, Guest sag kanala yerlestirilebilir -- bu, konusmaci ayrimini kolaylastirir.

8. **Streaming yok:** Tum podcast bellekte olusturulur, sonra kullaniciya gonderilir. Buyuk podcastler icin streaming yaklasimi daha iyi olur.
