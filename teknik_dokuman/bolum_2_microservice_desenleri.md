# BOLUM 2: Microservice Tasarim Desenleri

## 2.1 Monolitik vs Microservice: CAP Teoremi Baglaminda

### 2.1.1 CAP Teoremi (Brewer, 2000)

Eric Brewer'in CAP teoremi su uc ozellikten en fazla ikisinin ayni anda garanti edilebilecegini belirtir:

```
C - Consistency (Tutarlilik):    Her okuma en son yazilanı dondurur
A - Availability (Erisilebilirlik):  Her istek cevap alir (hata olmadan)
P - Partition tolerance (Bolunme toleransi): Ag bolumlenmesinde sistem calisir
```

**Matematiksel Formalizasyon:**

Bir dagitik sistem S, N dugum icersin: S = {n_1, n_2, ..., n_N}

Tutarlilik: Herhangi bir okuma operasyonu R(x) icin,
```
R(x) = W_son(x)
burada W_son(x) = en son tamamlanmis yazma operasyonunun degeri
```

Erisilebilirlik: Her istek I icin,
```
P(yanit(I) != hata) = 1    (deterministik garanti)
veya pratikte:
P(yanit(I, t < T_max)) > 1 - epsilon
```

Bolunme toleransi: Ag bolunmesi Pi olustu, Si ve Sj altgrupları olustu:
```
forall n_a in Si, n_b in Sj: mesaj(n_a, n_b) = kayip
Sistem calismaya devam etmeli.
```

**CAP Imkansizlik Ispati (Sezgisel):**

Ag bolunmesi olustugunda (P kacinilmaz):
- C secersek: Yazma islemi tum dugumlere yayilmadan yanit veremeyiz -> A kirilir
- A secersek: Bolunmenis taraftaki dugumler eski veri dondurur -> C kirilir

### 2.1.2 LocoDex Mimari Analizi

LocoDex'in mimari yapisi:

```
[Kullanici Tarayicisi]
        |
        | WebSocket (ws://localhost:8001/research_ws)
        |
[Docker Container: deep_research_service]
   |-- server.py (FastAPI + WebSocket)
   |-- SmartMultilingualResearcher
   |-- RealDeepResearcher
   |-- LocalDeepResearcher
        |
        | HTTP (http://host.docker.internal:11434)
        |
[Host Makine: Ollama / LM Studio]
```

Bu yapi "modular monolith" olarak siniflandirilir:
- Tek Docker container (tek deploy birimi)
- Dahili modullere ayrilmis (SmartMultilingualResearcher, RealDeepResearcher, LocalDeepResearcher)
- Tek veritabani/state (arastirma sonuclari dosya sisteminde)

**CAP degerlendirmesi:**

LocoDex tek dugumlu bir sistem oldugu icin P (ag bolumlenmesi) icleri arasinda yok. Ancak dis servislerle iletisimde (Ollama, Google, DuckDuckGo) bolunme yasanabilir:

```
Senaryo: Ollama baglantisi koptu
  - Availability: SmartMultilingualResearcher LM Studio'ya fallback yapar (server.py satir 86-129)
  - Consistency: Farkli modelden farkli kalitede yanit gelebilir -> eventual consistency

Senaryo: Google Search calismaz
  - Availability: DuckDuckGo fallback (smart_multilingual_research.py satir 348-372)
  - Consistency: Farkli arama motoru farkli sonuclar dondurur -> relaxed consistency
```

### 2.1.3 Neden Microservice Degil?

Alternatif mimari: Her bileşen ayrı servis olarak:
```
[API Gateway]
   |-- [Search Service] (Google + DuckDuckGo)
   |-- [LLM Service] (Ollama + LM Studio)
   |-- [Analysis Service] (icerik analizi)
   |-- [Report Service] (rapor olusturma)
```

**Trade-off analizi:**

| Kriter | Modular Monolith (LocoDex) | Full Microservice |
|--------|---------------------------|-------------------|
| Deploy karmasikligi | O(1) - tek container | O(K) - K container |
| Ag gecikmesi | 0 (process ici cagri) | K * RTT (servisler arasi) |
| Hata yonetimi | try/except | Circuit breaker + retry + DLQ |
| Gelistirme hizi | Hizli - tek codebase | Yavas - K codebase |
| Olcekleme | Dikey (daha buyuk container) | Yatay (daha fazla instance) |
| Bellekkullanimi | ~100 MB (tek Python process) | K * ~100 MB |
| Tutarlilik | Strong (ayni process) | Eventual (dagitik) |

LocoDex icin modular monolith dogru secim: tek gelistirici, kucuk kullanici tabani, lokal calisma onceligi.

### 2.1.4 Hesaplama Karmasikligi

Monolith'te fonksiyon cagrisi:
```
T_monolith = T_function_call ~ 100 nanosaniye
```

Microservice'te servis cagrisi:
```
T_microservice = T_serialize + T_network + T_deserialize
               = O(L) + RTT + O(L)
               burada L = mesaj boyutu
               Lokal agda: ~1000 nanosaniye + 500,000 nanosaniye + ~1000 nanosaniye
               ~ 500 mikrosaniye = 5000x daha yavas
```


---

## 2.2 Docker Containerization

### 2.2.1 Namespace Isolation

Docker, Linux kernel namespace'lerini kullanarak izolasyon saglar:

```
Namespace Tipleri:
1. PID namespace:    Process ID izolasyonu
2. NET namespace:    Network stack izolasyonu
3. MNT namespace:    Filesystem mount izolasyonu
4. UTS namespace:    Hostname izolasyonu
5. IPC namespace:    Inter-process communication izolasyonu
6. USER namespace:   User/group ID izolasyonu
7. CGROUP namespace: Cgroup gorunurluk izolasyonu
```

LocoDex Dockerfile:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
EXPOSE 8001
```

Bu container sunlari izole eder:
- PID: Container icindeki `uvicorn` process PID 1 olarak gorunur
- NET: Container kendi IP adresini alir, sadece port 8001 disariya acik
- MNT: `/app` dizini host dosya sisteminden izole

**Host'a Erisim:**

Container'dan Ollama'ya erisim icin ozel mekanizma (real_deep_research.py satir 239):
```python
host_ip = os.environ.get('OLLAMA_HOST_IP') or socket.gethostbyname('host.docker.internal')
```

`host.docker.internal` Docker Desktop'un sundugu ozel DNS kaydi. Bunu cozen mekanizma:
```
Container DNS sorgusu:
  host.docker.internal -> 192.168.65.2 (macOS Docker Desktop)
  veya -> 172.17.0.1 (Linux Docker bridge)
```

### 2.2.2 cgroup Resource Limiting

cgroups (control groups) kaynak sinirlamasini saglar:

```
Kontrol edilebilen kaynaklar:
1. cpu:    CPU zamani siniri
2. memory: Bellek siniri (hard limit + soft limit)
3. blkio:  Disk I/O bant genisligi
4. pids:   Maksimum process sayisi
```

LocoDex Dockerfile'inda kaynak siniri belirtilmemis. Bu production icin risk:

```
Sinir olmadan:
  - Python process sinirsiz bellek kullanabilir
  - Buyuk arastirma raporlari bellekte birikir
  - OOM (Out of Memory) riski

Onerilen sinirlar:
  docker run --memory=512m --cpus=1.0 deep_research_service

  Bu durumda:
  - Bellek: 512 MB hard limit
  - CPU: 1 core (CFS scheduler ile %100 kullanim)
```

### 2.2.3 Katmanli Dosya Sistemi (UnionFS/OverlayFS)

Dockerfile'daki her komut bir katman olusturur:

```
Katman 1: FROM python:3.11-slim        (~120 MB)
Katman 2: COPY requirements.txt .       (~1 KB)
Katman 3: RUN pip install ...           (~200 MB - bagimliliklarin toplami)
Katman 4: COPY . .                      (~100 KB - uygulama kodu)
```

**Neden requirements.txt ayri kopyalaniyor?**

Docker build cache optimizasyonu. Sadece requirements.txt degistiyse Katman 3 yeniden build edilir. Uygulama kodu degistiyse sadece Katman 4 degisir:

```
Ilk build:     Katman 1 + 2 + 3 + 4 = ~320 MB, ~2 dakika
Kod degisikliginde: Katman 1(cache) + 2(cache) + 3(cache) + 4(yeni) = ~100 KB, ~1 saniye
Bagimllik degisikliginde: Katman 1(cache) + 2(yeni) + 3(yeni) + 4(yeni) = ~200 MB, ~1.5 dakika
```

Tasarruf: Tipik gelistirme dongusunde %99.97 daha az veri transfer edilir.

### 2.2.4 Hesaplama Karmasikligi

- Container baslama suresi: O(1) ~ 100-500 ms (namespace + cgroup setup)
- Image pull: O(S) burada S = image boyutu (320 MB icin ~30 saniye, 100 Mbps agda)
- Layer cache hit: O(1) ~ 0 ms
- Process izolasyonu overhead: < %1 CPU (namespace syscall overhead)


---

## 2.3 Service Discovery ve Health Check Pattern'leri

### 2.3.1 LocoDex'teki Service Discovery

LocoDex'te service discovery statik konfigurasyonla yapilir:

```python
# llms.py satirlari 9-35
OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
LMSTUDIO_HOST = os.environ.get("LMSTUDIO_HOST")

if OLLAMA_HOST:
    try:
        requests.get(OLLAMA_HOST, timeout=2)
        API_BASE = OLLAMA_HOST
        PROVIDER = "ollama"
    except requests.exceptions.RequestException:
        pass

if not API_BASE and LMSTUDIO_HOST:
    # LM Studio fallback
```

Bu "static service discovery with health check" pattern'i:
1. Servis adresleri environment variable'lardan okunur
2. Baslangicta basit HTTP GET ile erisilebilirlik kontrol edilir
3. Timeout 2 saniye (hizli basarisizlik)

### 2.3.2 Health Check Stratejileri

LocoDex'te uc seviyede health check yapilir:

**Seviye 1: Baslangiç Health Check (llms.py)**
```python
requests.get(OLLAMA_HOST, timeout=2)
```
- Amac: Hangi LLM backend'inin kullanilabilir oldugunu tespit etmek
- Frekans: Tek seferlik (uygulama baslangicinda)
- Timeout: 2 saniye
- Basarisizlik durumu: Sonraki provider'a gec

**Seviye 2: Islem Sirasi Health Check (real_deep_research.py)**
```python
async with session.post(ollama_url, json=ollama_payload, timeout=300) as response:
    if response.status == 200:
        # Basarili
    else:
        # LM Studio'ya fallback
```
- Amac: Model cagirma sirasinda erisilebilirlik kontrolu
- Frekans: Her model cagrisi oncesinde
- Timeout: 300 saniye (model uzun calisabilir)
- Basarisizlik durumu: Fallback chain

**Seviye 3: WebSocket Keepalive (server.py)**
```python
await websocket.send_json({"type": "keepalive"})
```
- Amac: Client-server baglanti canliligini dogrulamak
- Frekans: 30 saniyede bir
- Basarisizlik durumu: Exception -> keepalive_task break

### 2.3.3 Fallback Chain Yapisi

```
SmartMultilingualResearcher.call_local_model() icindeki fallback:

1. Ollama (birincil) -> 2. LM Studio (ikincil) -> 3. Hata mesaji

RealDeepResearcher.call_local_model() icindeki fallback:

1. Ollama (source == "Ollama") -> Hata
   veya
1. LM Studio (source == "LM Studio") -> 2. Ollama fallback -> Hata
   veya
1. LM Studio (source bilinmiyor) -> 2. Ollama -> Hata

RealDeepResearcher.search_web() icindeki fallback:

1. Google Search -> 2. Tavily Search -> 3. Bos liste
```

### 2.3.4 Sinirlamalar

1. **Statik discovery:** Servis adresleri sadece baslangicta okunur. Ollama'nin port'u veya IP'si degisirse yeniden baslatma gerekir.
2. **Health check eksikligi:** Periyodik health check yok. Ollama cokerse arastirma sirasinda fark edilir.
3. **Service registry yok:** Consul, etcd veya ZooKeeper gibi bir discovery servisi kullanilmiyor. Bu kucuk olcekte gereksiz ama buyume durumunda sorun olur.


---

## 2.4 Timeout Stratejileri

### 2.4.1 Neden 300 Saniye Receive Timeout?

server.py satir 338:
```python
data = await asyncio.wait_for(websocket.receive_text(), timeout=300)  # 5 dakika
```

**Matematiksel Gerekce:**

Kullanici davranisi modeli:
```
T_kullanici = T_soru_yazma + T_dusunme + T_karar_verme

Ortalama T_soru_yazma ~ 30 saniye (arastirma sorusu yazma)
T_dusunme             ~ 0-120 saniye (ne arastirmak istedigini dusunme)
T_karar_verme         ~ 0-60 saniye

P(T_kullanici < 300s) > 0.99  (kullanicilarin %99'u 5 dakika icinde soru gonderir)
```

Neden 60 saniye degil?
- Kullanici yeni sekmeye gecip geri donebilir
- Karmasik arastirma konusu formule etme suresi uzun olabilir

Neden 600 saniye (10 dakika) degil?
- Fazla uzun timeout bellek israfina yol acar
- Olusmus baglantinin unuttuldugu senaryo artar
- Sunucu kaynaklarinin gereksiz tutulmasi

### 2.4.2 Neden 600 Saniye Model Timeout?

llms.py satir 54:
```python
timeout=600,  # 10 dakika
```

Bu deger LLM cikarsama (inference) suresi icin:

**LLM Inference Suresi Modeli:**

```
T_inference = T_prefill + T_decode

T_prefill = N_input / throughput_prefill
T_decode  = N_output * T_per_token

Ornek (lokal 7B model, CPU):
  N_input  = 2000 token (prompt)
  N_output = 3000 token (yanit)
  throughput_prefill = 50 token/s (CPU)
  T_per_token = 100 ms (CPU, 7B model)

  T_prefill = 2000 / 50 = 40 saniye
  T_decode  = 3000 * 0.1 = 300 saniye

  T_toplam  = 340 saniye
```

Ornek (lokal 70B model, CPU):
```
  throughput_prefill = 5 token/s
  T_per_token = 1000 ms

  T_prefill = 2000 / 5 = 400 saniye
  T_decode  = 3000 * 1.0 = 3000 saniye

  T_toplam  = 3400 saniye  (600 saniye yetmez!)
```

Ornek (lokal 7B model, GPU - NVIDIA RTX 4090):
```
  throughput_prefill = 1000 token/s
  T_per_token = 10 ms

  T_prefill = 2000 / 1000 = 2 saniye
  T_decode  = 3000 * 0.01 = 30 saniye

  T_toplam  = 32 saniye   (600 saniye fazlasiyla yeterli)
```

**Sonuc:** 600 saniye timeout, CPU uzerinde 7B-13B arasi modeller icin yeterli. 70B modeller icin yetersiz. GPU varsa fazlasiyla yeterli.

### 2.4.3 Timeout Hiyerarsisi

LocoDex'teki timeout degerleri buyukten kucuge:

```
Seviye 1: Model timeout         = 600s (llms.py)
Seviye 2: Ollama API timeout    = 300s (smart_multilingual_research.py satir 73)
Seviye 3: LM Studio API timeout = 120s (smart_multilingual_research.py satir 100)
Seviye 4: WS receive timeout    = 300s (server.py satir 338)
Seviye 5: LLM Studio sync       = 600s (server.py satir 70)
Seviye 6: Web scraping timeout  = 15s  (smart_multilingual_research.py satir 398)
Seviye 7: Health check timeout  = 2s   (llms.py satir 17)
Seviye 8: Search rate limit     = 1s   (smart_multilingual_research.py satir 551)

Dogru hiyerarsi kurali:
  T_outer > T_inner + T_margin

  T_WS_receive (300s) < T_model (600s) -> UYARI: Model yanit vermeden WS timeout olabilir!
```

**Potansiyel Bug:** Model 600 saniyeye kadar calismaya devam ederken, WebSocket receive timeout 300 saniyede tetiklenebilir. Ancak bu farkli islevler icin: receive kullanicinin yeni mesaj gondermesini bekler, model ise mevcut arastirmayi yurur. Yani paralel calisan iki ayri timeout.


---

## 2.5 Circuit Breaker Pattern: Exponential Backoff

### 2.5.1 Matematiksel Formul

llms.py satirlari 37 ve 59:
```python
@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=15)
)
```

**Exponential Backoff Formulu:**

```
T_wait(n) = min(max(multiplier * 2^n, min), max)

burada:
  n          = deneme numarasi (0, 1, 2, ...)
  multiplier = 1
  min        = 4 saniye
  max        = 15 saniye
```

**LocoDex'teki somut degerler:**

```
Deneme 0 (ilk cagri):  Basarisiz
  T_wait(0) = min(max(1 * 2^0, 4), 15) = min(max(1, 4), 15) = min(4, 15) = 4 saniye

Deneme 1 (ikinci cagri): Basarisiz
  T_wait(1) = min(max(1 * 2^1, 4), 15) = min(max(2, 4), 15) = min(4, 15) = 4 saniye

Deneme 2 (ucuncu cagri): Basarisiz -> TAMAMEN VAZGEC
  (stop_after_attempt(3) nedeniyle)
```

Dikkat: multiplier=1 ve min=4 oldugu icin, 2^0=1 ve 2^1=2 degerleri min'den kucuk. Bu nedenle ilk iki bekleme suresi ayni: 4 saniye.

Eger multiplier=2 olsaydi:
```
T_wait(0) = min(max(2 * 1, 4), 15) = 4 saniye
T_wait(1) = min(max(2 * 2, 4), 15) = 4 saniye
T_wait(2) = min(max(2 * 4, 4), 15) = 8 saniye  (ama 3. denemede duruyor)
```

### 2.5.2 Toplam Bekleme Suresi

En kotu durum (3 denemede de basarisiz):
```
T_toplam = T_call_1 + T_wait(0) + T_call_2 + T_wait(1) + T_call_3

T_call = model timeout = 600 saniye (en kotu)

T_toplam_max = 600 + 4 + 600 + 4 + 600 = 1808 saniye ~ 30 dakika
T_toplam_min = 0.1 + 4 + 0.1 + 4 + 0.1 = 8.3 saniye (hizli basarisizlik)
```

### 2.5.3 Neden Exponential Backoff?

**Thundering Herd Problemi:**

N client ayni anda basarisiz olursa:
```
Sabit bekleme (fixed retry): t=4s'de N client yeniden dener -> sunucu cokus
Exponential backoff:          t=4s, 8s, 16s... -> yuklenme dagitilir
Exponential + jitter:         t=rand(4s), rand(8s)... -> en iyi dagilim
```

LocoDex'te jitter yok. Bu tek kullanicili senaryoda sorun degil ama cokullanucili senaryoda thundering herd riski var.

**Jitter Ekleme Formulu (onerilen iyilestirme):**
```
T_wait_jittered(n) = T_wait(n) * uniform(0.5, 1.5)

Ornek:
  T_wait(0) = 4 * uniform(0.5, 1.5) = [2, 6] saniye arasi
  T_wait(1) = 4 * uniform(0.5, 1.5) = [2, 6] saniye arasi
```

### 2.5.4 Circuit Breaker State Machine

Tam circuit breaker pattern'i 3 durumdan olusur:

```
          basari
[CLOSED] -------> [CLOSED]
    |
    | N basarisizlik
    v
[OPEN] -------> [HALF-OPEN]
   ^    T_reset     |
   |    suresi      | basari -> CLOSED
   +--- basarisiz --+
```

LocoDex'te sadece retry (CLOSED state) uygulanmis. OPEN ve HALF-OPEN durumlari yok. Bu, basarisiz bir servise surekli istek gondermesine neden olabilir:

```
LocoDex davranisi (mevcut):
  Cagri 1 basarisiz (4s bekle) -> Cagri 2 basarisiz (4s bekle) -> Cagri 3 basarisiz -> HATA

  Sonraki arastirma isteginde ayni dongu tekrar edilir!

Ideal circuit breaker davranisi:
  3 basarisizlik -> OPEN state (60s boyunca hic deneme) -> HALF-OPEN (1 deneme) -> basariliysa CLOSED
```

### 2.5.5 Hesaplama Karmasikligi

- Retry mantigi: O(K) burada K = maksimum deneme sayisi (3)
- Bekleme hesabi: O(1) per retry
- Jitter hesabi: O(1) per retry (rastgele sayi uretimi)
- Toplam: O(K) = O(1) (K sabit ve kucuk)


---

## 2.6 Backpressure ve Rate Limiting Mekanizmalari

### 2.6.1 LocoDex'teki Rate Limiting

smart_multilingual_research.py satir 551:
```python
await asyncio.sleep(1)  # Rate limiting
```

Bu en basit rate limiting: her arama sorgusundan sonra 1 saniye bekle.

**Token Bucket Algoritmasi (Teorik):**

Daha sofistike rate limiting icin token bucket:
```
Parametreler:
  R = token uretim hizi (token/saniye)
  B = kova kapasitesi (maksimum token)

Baslangiç: kova = B token

Her istek icin:
  if kova >= 1:
      kova -= 1
      IZIN VER
  else:
      REDDET veya BEKLE

Her saniye:
  kova = min(kova + R, B)
```

LocoDex'in basit `sleep(1)` yontemi aslinda rate = 1 req/s'lik sabit hiz siniri:
```
R_locodex = 1 istek / saniye
B_locodex = 1 (kova yok, her defasinda 1 saniye bekle)
```

### 2.6.2 Web Arama Rate Limiting Analizi

Google arama API'si icin onerilen hiz sinirlari:
```
Google (resmi olmayan):    ~10 istek/dakika (fazlasi CAPTCHA tetikler)
DuckDuckGo:               ~15 istek/dakika
Tavily API:                Plan bagimlı (50-1000 istek/ay)
```

LocoDex'te her arastirmada:
```
Sorgu sayisi = 4 (smart_multilingual_research.py satir 294)
Her sorgu icin sonuc = 4 (satir 548)
Bekleme = 1 saniye/sorgu

Toplam arama istegi = 4 * 4 = 16 istek
Toplam arama suresi = 4 * 1 = 4 saniye bekleme

Hiz = 16 istek / (4 saniye + islem suresi) ~ 2-3 istek/saniye
```

Bu hiz Google'in sinirini asmayabilir (kisa surede 16 istek yapilmasi riskli).

### 2.6.3 Backpressure Mekanizmasi

LocoDex'te backpressure mekanizmasi sinirli:

```
Backpressure kaynaklari:
1. WebSocket tampon dolu -> asyncio otomatik olarak send'i yavaslatir
2. aiohttp connection pool dolu -> yeni istekler kuyrukta bekler
3. Ollama yogun -> 300s timeout ile beklenir

Eksik mekanizmalar:
1. Client-side throttling: Kullanici ust uste arastirma istegi gondermesini sinirlanmiyor
2. Server-side queue: Birden fazla esanli arastirma istegi engellenmis degil
3. Memory pressure: Buyuk arastirma sonuclari bellekte birikiyor
```

**Backpressure Formulu (Little's Law):**

```
L = lambda * W

burada:
  L      = sistemdeki ortalama istek sayisi
  lambda = istek gelis hizi (istek/saniye)
  W      = ortalama islem suresi (saniye)

LocoDex icin:
  lambda = 0.1 istek/saniye (10 saniyede 1 arastirma istegi)
  W      = 120 saniye (ortalama arastirma suresi)
  L      = 0.1 * 120 = 12 esanli istek

Her istek bellekte:
  Ortalama arastirma verisi = 50 KB (10 kaynak * 5 KB analiz)
  WebSocket tampon          = 64 KB
  Python nesneleri          = ~200 KB

  Toplam per istek = ~314 KB
  12 esanli istek  = 3.8 MB

Bu kabul edilebilir. Ama lambda = 1 istek/saniye olursa:
  L = 1 * 120 = 120 esanli istek
  Bellek = 120 * 314 KB = 37 MB (hala kabul edilebilir ama artiyor)
```

### 2.6.4 Sayisal Ornek - Tam Arastirma Dongusu

Tek bir arastirma isteginin tum timeout'lari ve suresi:

```
Adim                               Timeout    Tipik Sure
------                             -------    ----------
1. WS mesaj bekle                  300s       2s
2. Dil algila                      -          0.1s
3. Sorgu olustur (LLM cagri)      300s       10-60s
4. Web arama x4                   5s/istek    8s (4*1s bekleme + islem)
5. Icerik cekme x10               15s/istek   30s
6. Kaynak degerlendirme x10       300s/istek  100s
7. Icerik analizi x10             300s/istek  200s
8. Gap analizi                    300s        30s
9. Final rapor                    300s        60s
------
TOPLAM TİPİK:                                ~440 saniye (~7.3 dakika)
TOPLAM EN KOTU:                               ~3300 saniye (~55 dakika)
TOPLAM EN IYI (GPU):                          ~60 saniye (~1 dakika)
```

Bu sureler WebSocket keepalive mekanizmasinin (30s aralik) neden gerekli oldugunu aciklar: 7 dakikalik islem sirasinda en az 14 keepalive mesaji gonderilir.
