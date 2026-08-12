# KONU 4: Dosya Yonetimi ve Kayit Sistemi

## 4.1 Safe Filename Generation

### Problem Tanimi

Kullanicinin arastirma konusu rastgele metin olabilir: "AI'nin geleceği: 2025'te ne olacak?" gibi. Bu metin dosya adi olarak kullanildiginda isletim sistemi kisitlamalarini ihlal eder.

### Koddaki Uygulamalar

LocoDex'te 3 farkli safe filename implementasyonu vardir:

**1. real_deep_research.py L903:**

```python
safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
```

Mantik: alfanumerik + bosluk + tire + alt cizgi disindaki her seyi sil. Sonra son bosluklari temizle. Max 50 karakter.

**2. smart_multilingual_research.py L736:**

```python
safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
```

Ayni implementasyon (kopyala-yapistir).

**3. path_utils.py L148-171:**

```python
def create_safe_filename(text: str, max_length: int = 50) -> str:
    invalid_chars = '<>:"/\\|?*'
    safe_text = ''.join(c for c in text if c not in invalid_chars)
    safe_text = safe_text.replace(' ', '_')
    safe_text = ''.join(c for c in safe_text if ord(c) >= 32)
    if len(safe_text) > max_length:
        safe_text = safe_text[:max_length]
    safe_text = safe_text.rstrip('.')
    if not safe_text:
        safe_text = 'untitled'
    return safe_text
```

Daha kapsamli: invalid karakterler, kontrol karakterleri, trailing dot, bos isim kontrolu.

### 4.1.1 Isletim Sistemi Kisitlamalari

**Windows:**

```
Yasak karakterler: < > : " / \ | ? *
Yasak isimler: CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9
Maksimum yol uzunlugu: 260 karakter (LEGACY) veya 32767 (long path enabled)
Maksimum dosya adi: 255 karakter
Boslukla veya nokta ile bitemez
Case-insensitive: "File.txt" = "file.TXT"
```

Windows'un en katI kisitlama oldugu aciktir. 9 yasak karakter + 22 yasak isim + trailing dot/space kurali.

**Unix/macOS:**

```
Yasak karakterler: / (yol ayirici) ve \0 (null, C string terminator)
Maksimum dosya adi: 255 byte (UTF-8'de ~63-255 karakter)
Case-sensitive: "File.txt" != "file.txt" (macOS: case-preserving ama default case-insensitive)
Hidden files: "." ile baslayanlar
```

**Karsilastirma tablosu:**

| Karakter | Windows | Unix | macOS | Koddaki Durum |
|----------|---------|------|-------|---------------|
| < | YASAK | OK | OK | path_utils: filtrelenir, others: filtrelenir (alnum degil) |
| > | YASAK | OK | OK | Ayni |
| : | YASAK | OK | YASAK (HFS+) | path_utils: filtrelenir |
| " | YASAK | OK | OK | path_utils: filtrelenir |
| / | YASAK | YASAK | YASAK | path_utils: filtrelenir |
| \ | YASAK | OK | OK | path_utils: filtrelenir |
| \| | YASAK | OK | OK | path_utils: filtrelenir |
| ? | YASAK | OK | OK | path_utils: filtrelenir |
| * | YASAK | OK | OK | path_utils: filtrelenir |
| Bosluk | OK (ama uyarilir) | OK | OK | real_deep: kalir, path_utils: _ ile degistirilir |
| Turkce (cgsuo) | OK | OK | OK | real_deep: FILTRELENIR (isalnum degil), path_utils: KALIR |

### KRITIK BUG: Turkce Karakter Kaybi

real_deep_research.py ve smart_multilingual.py'deki implementasyon:

```python
safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_'))
```

`str.isalnum()` Unicode-aware'dir, yani Turkce karakterler (c, g, i, s, u, o ve buyuk harfleri) `True` dondurur.

**Test:**
```python
>>> 'c'.isalnum()  # U+00E7 LATIN SMALL LETTER C WITH CEDILLA
True
>>> 'g'.isalnum()  # U+011F LATIN SMALL LETTER G WITH BREVE
True
```

Yani real_deep_research.py'de Turkce karakterler KORUNUR. Bu iyi.

Ancak path_utils.py'de farkli bir yaklasim var: sadece invalid_chars filtrelenir, Turkce karakterler kalir. Ama `ord(c) >= 32` kontrolu de var -- Turkce karakterler hep >= 32 oldugundan sorun yok.

**Potansiyel sorun:** Dosya adi icerisinde Turkce karakter bulunmasi:
- Windows: NTFS UTF-16 destekler, sorun yok
- macOS: HFS+/APFS NFD normalization yapar. "c" (U+00E7) bir NFC karakter, ama macOS bunu "c" + "\u0327" (NFD) olarak saklayabilir. Dosya arama yaparken sorun cikarabilir.
- Linux: ext4 byte-level, encoding agnostic. UTF-8 olarak saklar, sorun yok.

### 4.1.2 Filename Collision (Cakisma) Analizi

**Timestamp tabanli cakisma onleme:**

real_deep_research.py L902:
```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
```

Cozunurluk: 1 saniye. Ayni saniyede iki arastirma tamamlanirsa cakisma olur.

path_utils.py L179:
```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
```

Cozunurluk: 1 mikrosaniye (%f = microsecond). Cakisma olasiligi cok daha dusuk.

together_open_deep_research.py L264:
```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
```

Ayni -- mikrosaniye cozunurluk.

**Cakisma Olasiligi (Birthday Paradox):**

n dosya olusturdugumuzda, en az bir cakisma olma olasiligi:

```
P(cakisma) = 1 - prod_{i=0}^{n-1} (1 - i/N)

burada N = toplam olasi timestamp sayisi

1 saniye cozunurlukle:
  Bir gun icinde: N = 86400 (24*60*60)
  n=10 arastirma/gun: P = 1 - prod_{i=0}^{9} (1-i/86400) ~ 1 - (1 - 9*10/(2*86400)) ~ 5.2 * 10^-4

Mikrosaniye cozunurlukle:
  N = 86400 * 10^6 = 8.64 * 10^10
  n=10: P ~ 10 * 9 / (2 * 8.64 * 10^10) ~ 5.2 * 10^-10
```

Yani 1-saniye cozunurlukle bile gunde 10 arastirma icin cakisma olasiligi %0.05. Mikrosaniye ile %0.000000005. Pratikte sorun degil.

Ancak `safe_topic` kismi da cakismayi onler: farkli konularin dosya adlari farkli olacaktir (ayni saniyede iki arastirma bile yapilsa konulari muhtemelen farklidir).

---

## 4.2 Cift Kayit Stratejisi: Redundancy

### Koddaki Uygulama

real_deep_research.py L896-934:

```python
desktop_path = "/app/desktop"         # Docker'da host masaustu
research_path = "/app/research_results"  # Container ici results

# Hem masaustune hem research_results'a kaydet
with open(desktop_sources_path, 'w', encoding='utf-8') as f:
    f.write(sources_content)

with open(research_sources_path, 'w', encoding='utf-8') as f:
    f.write(sources_content)
```

Ayni dosya iki farkli konuma yazilir:
1. `/app/desktop` -> Docker volume mount ile host makinenin Desktop'ina
2. `/app/research_results` -> Container ici, container silinse kaybolur

### Redundancy Teorisi

Bilgi teorisinde redundancy, bir mesajin kaybedilme riskini azaltmak icin tekrarlanmasidir.

**Tekli kayit:**
```
P(kayip) = p  (bir diskin bozulma olasiligi)
```

**Cift kayit (bagimsiz diskler):**
```
P(kayip) = p^2  (her ikisi de ayni anda bozulmali)
```

Ornek: p = 0.01 (yillik disk arizasi orani):
```
Tekli: P = 0.01 = %1
Cift:  P = 0.01^2 = 0.0001 = %0.01
```

100x iyilestirme!

Ancak LocoDex'te redundancy farkli amaca hizmet eder:

- `/app/desktop`: Kullanicinin kolayca erisebilecegi konum (masaustu)
- `/app/research_results`: Uygulamanin kendi veri deposu (API erisiimi icin)

Bu, availability (erisebilirlik) icin redundancy'dir, reliability (guvenilirlik) degil -- cunku her iki konum da ayni fiziksel diskte olabilir.

### Docker Volume Mount Riskleri

```
Host Desktop <--mount--> /app/desktop (Container)
```

Riskler:
1. **Mount hatasi:** Docker Compose'da volume mount dogru yapilandirilmamissa, `/app/desktop` container-local olur ve host'a yansimaz.
2. **Yetki sorunu:** Container root olarak calisir, host'taki dosya izinleri farkli olabilir.
3. **Encoding farki:** Container Linux (UTF-8), host macOS (NFD normalization) veya Windows (UTF-16). Turkce dosya adlarinda sorun cikarabilir.

---

## 4.3 File I/O: Encoding ve BOM

### UTF-8 Kullanimi

Tum dosya yazma islemlerinde `encoding='utf-8'` belirtilir:

```python
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(report)
```

**Neden UTF-8?**

UTF-8 (Unicode Transformation Format - 8 bit) degisken uzunluklu bir karakter kodlamasidir:

```
Karakter Araligi        | Byte Sayisi | Bitis Deseni
U+0000 - U+007F        | 1 byte      | 0xxxxxxx
U+0080 - U+07FF        | 2 byte      | 110xxxxx 10xxxxxx
U+0800 - U+FFFF        | 3 byte      | 1110xxxx 10xxxxxx 10xxxxxx
U+10000 - U+10FFFF     | 4 byte      | 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx
```

**Turkce karakterler ve byte sayilari:**

| Karakter | Unicode Code Point | UTF-8 Bytes | Hex |
|----------|-------------------|-------------|-----|
| a | U+0061 | 1 byte | 61 |
| c | U+00E7 | 2 byte | C3 A7 |
| g | U+011F | 2 byte | C4 9F |
| i (noktasiz) | U+0131 | 2 byte | C4 B1 |
| o | U+00F6 | 2 byte | C3 B6 |
| s | U+015F | 2 byte | C5 9F |
| u | U+00FC | 2 byte | C3 BC |
| I (noktali buyuk) | U+0130 | 2 byte | C4 B0 |

Her Turkce ozel karakter 2 byte yer kaplar (ASCII'nin 1 byte'ina karsi).

**Ornek boyut hesabi:** "Yapay zeka'nin geleceği" (23 karakter):

```
ASCII karakterler: y,a,p,a,y, ,z,e,k,a,',n,i,n, ,g,e,l,e,c,e -> 21 * 1 byte = 21
Turkce: g(2), i(1, ASCII!), g(2) -> toplam 4 extra byte
Aslinda: "ğ" = 2 byte, "ğ" = 2 byte, diger hepsi ASCII
UTF-8 toplam: 21 + 2 + 2 = 25 byte (23 karakter icin)
```

### BOM (Byte Order Mark) Handling

BOM = U+FEFF, UTF-8'de `EF BB BF` (3 byte).

**Sorun:** Windows'taki bazi text editor'ler (eski Notepad) UTF-8 dosyalarin basina BOM ekler. Bu, Python'da okunan dosyanin ilk karakterinde `\ufeff` olarak gorunur.

LocoDex'te BOM handling YAPILMIYOR. `encoding='utf-8'` ile yazilan dosyalarda BOM eklenmez (Python default davranisi). Ama eger kullanici bir BOM'lu dosya verirse (ornegin konu basligI olarak), bu BOM dosya adina dahil olabilir.

**Potansiyel fix:**
```python
# BOM temizleme
topic = topic.lstrip('\ufeff')
```

Veya daha savunmaci:
```python
encoding='utf-8-sig'  # BOM'u otomatik cikarir (okumada)
```

### Error Handling Stratejisi

Koddaki try-except yaklasimi (real_deep_research.py L924-934):

```python
try:
    with open(desktop_sources_path, 'w', encoding='utf-8') as f:
        f.write(sources_content)
except Exception as e:
    logger.error(f"Desktop sources save error: {e}")

try:
    with open(research_sources_path, 'w', encoding='utf-8') as f:
        f.write(sources_content)
except Exception as e:
    logger.error(f"Research sources save error: {e}")
```

Her kayit bagimsiz try-except icinde. Birinin basarisiz olmasi digernini etkilemez. Bu, "fail-independent" redundancy saglar.

Ancak: her iki kayit da basarisiz olursa, hata sadece log'a yazilir, kullaniciya bildirilmez. Rapor sadece WebSocket uzerinden dondurulur -- dosya kaydedilmese bile arastirma sonucu kaybolmaz.

---

## 4.4 Cross-Platform Path Yonetimi

### path_utils.py Mimari Analizi

`PlatformPaths` sinifi static method'lar ile platform-agnostik yol yonetimi saglar.

**Karar agaci:**

```
Is Docker?
  Evet -> /app/ (container yollari)
  Hayir ->
    Is Windows?
      Evet -> %APPDATA%/LocoDex veya %USERPROFILE%/Desktop
      Hayir ->
        Is macOS?
          Evet -> ~/Library/Application Support/LocoDex
          Hayir (Linux) ->
            $XDG_DATA_HOME/locodex veya ~/.local/share/locodex
```

### XDG Base Directory Specification

Linux'ta standart dizin yapisi (freedesktop.org):

```
$XDG_DATA_HOME    = ~/.local/share     (kalici veri)
$XDG_CONFIG_HOME  = ~/.config          (ayar dosyalari)
$XDG_CACHE_HOME   = ~/.cache           (gecici cache)
$XDG_STATE_HOME   = ~/.local/state     (durum dosyalari)
```

path_utils.py bu standarda uyar:
- Data: `$XDG_DATA_HOME/locodex` (L50-52)
- Cache: `$XDG_CACHE_HOME/locodex` (L129-131)

### macOS Yollari

macOS kendi konvansiyonlarina sahiptir:
- Data: `~/Library/Application Support/LocoDex` (L46)
- Cache: `~/Library/Caches/LocoDex` (L125)

Bu, Apple'in "Application Support" ve "Caches" klasor yapisiyla uyumludur. macOS kullanicilari bu yollari Finder'da goremez (Library gizlidir) ama `~/Desktop` her zaman gorunurdur.

### Docker Path Mapping

```
Docker Compose (tipik):

volumes:
  - ~/Desktop:/app/desktop           # Host masaustu -> container
  - ./research_results:/app/research_results  # Proje dizini -> container
```

path_utils.py L33-35:
```python
if PlatformPaths.is_docker():
    return Path('/app')
```

Docker icinde calistiginda TUM yollar `/app/` altindadir. `is_docker()` kontrolu `/.dockerenv` dosyasinin varligina bakar (L28-29).

### Disk Alani Kontrolu

path_utils.py L187-195:

```python
def get_available_space(path: Union[str, Path]) -> int:
    import shutil
    return shutil.disk_usage(str(path)).free
```

Bu, dosya yazma oncesi "yeterli alan var mi?" kontrolu icin kullanilabilir. Ancak kodda bu kontrol arastirma sirasinda CAGIRILMIYOR -- sadece utility fonksiyonu olarak mevcut.

**Potansiyel sorun:** Docker container icinde `disk_usage()` container'in overlay filesystem'ini raporlar, host disk alanini degil. `/app/desktop` mount edilmis olsa bile `shutil.disk_usage('/app/desktop')` host disk alanini dogru gosterebilir (cunku mount point host FS'i isaret eder).

---

## 4.5 Dosya Kayit Akisi: Tam Tablo

Proje genelindeki tum dosya kayit islemlerini ozetleyelim:

| Dosya Turu | Format | Konum 1 | Konum 2 | Encoding | Dosya:Satir |
|-----------|--------|---------|---------|----------|-------------|
| Arastirma raporu | .md (Markdown) | /app/desktop | /app/research_results | utf-8 | real_deep_research.py:940-978 |
| Kaynak listesi | .txt | /app/desktop | /app/research_results | utf-8 | real_deep_research.py:906-934 |
| Akilli arastirma | .md | ~/Desktop | - | utf-8 | smart_multilingual.py:718-757 |
| Lokal arastirma | .md | - | /app/research_results | utf-8 | server.py:258-276 |
| HTML rapor | .html | parametrik | - | utf-8 | generation.py:462-486 |
| PDF rapor | .pdf | parametrik | - | binary | generation.py:8-99 |
| Podcast HTML | .html | parametrik | - | utf-8 | podcast.py:199-251 |
| Podcast audio | .mp3 | parametrik | - | binary | podcast.py:254-270 |

**Gozlemler:**

1. real_deep_research.py cift kayit yapar (desktop + research_results)
2. smart_multilingual.py sadece Desktop'a kaydeder
3. server.py (LocalDeepResearcher) sadece research_results'a kaydeder
4. Tutarsiz strateji: 3 farkli arastirma sinifi 3 farkli kayit stratejisi kullanir

### Filename Pattern Analizi

```
real_deep_research.py:
  {timestamp}_{safe_topic}_deep_research.md
  {timestamp}_{safe_topic}_sources.txt
  Ornek: 20260315_143022_AI_nin_gelecegi_deep_research.md

smart_multilingual.py:
  {timestamp}_{safe_topic}_smart_research.md
  Ornek: 20260315_143022_AI_nin_gelecegi_smart_research.md

server.py (lokal):
  {timestamp_microsecond}_{safe_topic}.md
  Ornek: 20260315_143022_123456_AI_nin_gelecegi.md

together_open_deep_research.py:
  Dosya kaydetme YAPMIYOR (sadece sonuc dondurur)
```

---

## 4.6 Sinirlamalar

1. **Tutarsiz kayit stratejisi:** 3 arastirma sinifi farkli yerlere farkli formatlarda kaydeder. Merkezi bir kayit yoneticisi olmayi.

2. **Disk alani kontrolu yok:** Dosya yazma oncesi alan kontrolu yapilmiyor. Disk doluysa hata mesaji belirsiz olabilir.

3. **Dosya kilitleme yok:** Ayni anda iki arastirma ayni dosya adini olusturabilir (teorik, timestamp ile dusuk olasilik). `filelock` sadece together_open_deep_research.py cache'inde kullanilir.

4. **Cleanup mekanizmasi yok:** Eski arastirma dosyalari otomatik silinmiyor. Zamanla disk dolabilir.

5. **BOM handling eksik:** UTF-8 BOM ile gelen girdi temizlenmiyor.

6. **macOS NFD normalization:** Turkce dosya adlari macOS'ta NFD'ye donusturulebilir, dosya arama/eslestirmede sorun cikarabilir.

7. **Windows reserved names:** path_utils.py `create_safe_filename()` reserved isimleri (CON, PRN, NUL, vb.) KONTROL ETMIYOR. Konu "CON" veya "NUL" olursa Windows'ta dosya olusturulamaz.

8. **Docker mount bagimliligi:** real_deep_research.py hardcoded `/app/desktop` kullanir. Docker volume mount yapilmamissa dosyalar host'a ulasmaz, container silindiginde kaybolur.
