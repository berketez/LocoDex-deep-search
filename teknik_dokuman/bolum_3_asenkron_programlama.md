# BOLUM 3: Asenkron Programlama Modeli

## 3.1 Python asyncio: Event Loop Implementasyonu

### 3.1.1 Teorik Temel - I/O Multiplexing

Isletim sistemi duzeyin de I/O multiplexing'in evrimi:

```
Evrim Sirasi:
1. select() (1983, BSD)     -> O(N) her cagri, N = dosya tanimlayici sayisi
2. poll() (1997, POSIX)     -> O(N) her cagri, ama N siniri yok
3. epoll (2002, Linux 2.6)  -> O(1) amortized event bildirimi
4. kqueue (2000, FreeBSD)   -> O(1) amortized, macOS'ta kullanilir
5. IOCP (Windows)           -> O(1) tamamlanma port'lari
```

**select() Problemi:**

```c
int select(int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds, struct timeval *timeout);
```

Her cagri:
1. fd_set'i kernel'a kopyala: O(N)
2. Tum fd'leri tara: O(N)
3. Sonuclari user space'e kopyala: O(N)

N = 10,000 soket icin her cagri ~ 10,000 islem. Saniyede 1000 cagri: 10 milyon islem.

**epoll() Cozumu:**

```c
int epoll_create(int size);
int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event);  // O(log N) - red-black tree
int epoll_wait(int epfd, struct epoll_event *events, int maxevents, int timeout);  // O(k) - k = hazir event
```

Kayit bir kere: O(log N)
Her yoklama: O(k) burada k = hazir event sayisi (N degil!)

N = 10,000 soket, k = 5 hazir event:
```
select: O(10,000) per cagri
epoll:  O(5) per cagri = 2000x daha verimli
```

### 3.1.2 macOS'ta kqueue (LocoDex'in Calistigi Platform)

LocoDex macOS uzerinde Docker Desktop icinde calisir. Container icinde Linux kernel kullanir (epoll), ama native calismada macOS kqueue kullanir.

kqueue API:
```c
int kqueue(void);
int kevent(int kq, const struct kevent *changelist, int nchanges,
           struct kevent *eventlist, int nevents, const struct timespec *timeout);
```

kqueue ve epoll karsilastirmasi:
```
                epoll        kqueue
Kayit:          O(log N)     O(log N)
Yoklama:        O(k)         O(k)
Event tipleri:  Soket, dosya  Soket, dosya, sinyal, process, timer (daha zengin)
Batch islem:    Hayir         Evet (changelist + eventlist tek cagri)
```

### 3.1.3 asyncio Event Loop Ic Yapisi

Python asyncio'nun basitlestirilmis event loop implementasyonu:

```python
class EventLoop:
    def __init__(self):
        self._ready = deque()          # Hemen calistirilacak callback'ler
        self._scheduled = []           # Heap: zamanlanmis callback'ler (timer'lar)
        self._selector = selectors.DefaultSelector()  # epoll/kqueue wrapper

    def run_forever(self):
        while True:
            # 1. Zamanlanmis callback'leri kontrol et
            now = time.monotonic()
            while self._scheduled and self._scheduled[0].when <= now:
                handle = heapq.heappop(self._scheduled)
                self._ready.append(handle)

            # 2. I/O event'lerini yokla
            timeout = self._calculate_timeout()
            events = self._selector.select(timeout)
            for key, mask in events:
                self._ready.append(key.data)  # callback'i ready'ye ekle

            # 3. Hazir callback'leri calistir
            ntodo = len(self._ready)
            for _ in range(ntodo):
                handle = self._ready.popleft()
                handle._run()  # Coroutine'i bir adim ilerlet
```

**Veri Yapilari ve Karmasikliklari:**

```
_ready:     deque (cift uclu kuyruk)
  - append:  O(1)
  - popleft: O(1)
  - toplam N callback: O(N) per iteration

_scheduled: min-heap
  - push: O(log N)
  - pop:  O(log N)
  - peek: O(1)

_selector:  epoll/kqueue wrapper
  - register: O(log N)
  - select:   O(k) burada k = hazir event sayisi
```

### 3.1.4 LocoDex'te Event Loop Akisi

server.py calistiginda:

```
uvicorn baslatilir:
    -> asyncio.run() cagirilir
    -> Event Loop olusturulur
    -> uvicorn HTTP/WS server soketi register edilir

Kullanici baglanir:
    -> kqueue/epoll: yeni baglanti event'i
    -> research_websocket() coroutine olusturulur
    -> _ready kuyuruguna eklenir

research_websocket icinde:
    -> websocket.accept() cagirilir
       -> TCP accept syscall -> I/O bekle -> YIELD
       -> Event loop diger callback'lere bakar
       -> accept tamamlanir -> coroutine devam eder

    -> asyncio.create_task(keepalive_task())
       -> Yeni coroutine, _ready'ye eklenir
       -> asyncio.sleep(30) -> _scheduled heap'e eklenir (t+30s)

    -> websocket.receive_text()
       -> soket read -> I/O bekle -> YIELD
       -> 300s timeout icin _scheduled heap'e timer eklenir
```


---

## 3.2 Coroutine vs Thread vs Process: Context Switch Maliyeti

### 3.2.1 Context Switch Maliyeti Analizi

**Process Context Switch:**
```
Kaydedilecek durum:
  - CPU register'lari (RAX, RBX, ..., R15): 16 * 8 byte = 128 byte
  - Program counter (RIP): 8 byte
  - Stack pointer (RSP): 8 byte
  - Page table base register (CR3): 8 byte
  - FPU/SSE state: ~512 byte
  - Kernel stack: ~8 KB

Ek islemler:
  - TLB flush (page table degisimi): ~1000 cycle
  - Cache cold start: ~10,000 cycle (degisken)
  - Kernel mode gecisi: ~500 cycle

Toplam: 5,000 - 50,000 cycle
Sureye donusum (3 GHz CPU): 1.7 - 16.7 mikrosaniye
```

**Thread Context Switch (ayni process icinde):**
```
Kaydedilecek durum:
  - CPU register'lari: 128 byte
  - Program counter: 8 byte
  - Stack pointer: 8 byte
  - FPU/SSE state: ~512 byte

NOT kaydedilmesi gereken:
  - Page table (ayni): 0
  - TLB flush gerekmez: 0

Ek islemler:
  - Kernel mode gecisi: ~500 cycle
  - Cache hala sicak (buyuk olasilikla): ~1,000 cycle

Toplam: 1,000 - 10,000 cycle
Sureye donusum: 0.33 - 3.3 mikrosaniye
```

**Coroutine "Context Switch" (Python asyncio):**
```
Kaydedilecek durum:
  - Python frame nesnesi (local degiskenler): degisken
  - Generator/coroutine state: ~200-500 byte

NOT kaydedilmesi gereken:
  - CPU register'lari: 0 (ayni thread devam eder)
  - Stack pointer: 0 (Python stack farkli)
  - Page table: 0
  - Kernel mode gecisi: 0

Islem:
  - Python bytecode: YIELD_FROM veya SEND
  - Deque'den pop/push: O(1)

Toplam: ~100-500 Python bytecode instruction
Sureye donusum: ~1-5 mikrosaniye
```

### 3.2.2 Karsilastirma Tablosu

```
                    Process       Thread        Coroutine
Context switch      1.7-16.7 us   0.33-3.3 us   ~1-5 us*
Bellek overhead     ~2 MB/process ~64 KB/thread  ~1 KB/coroutine
Olusturma maliyeti  ~1-10 ms      ~100 us        ~1 us
Max esanli (4GB)    ~2,000        ~65,000        ~4,000,000
Paralellik          Gercek (multi-core) GIL kilit Gercek yok (tek thread)
I/O concurrency     Iyi           Iyi            En iyi
CPU concurrency     En iyi        GIL sinirli    Yok

* Coroutine switch, Python yorumlayicisi icinde gerceklesir.
  Sistem cagirisi gerektirmez ama Python bytecode yavastir.
```

### 3.2.3 LocoDex Icin Analiz

LocoDex'te esanli yapilan islemler:
1. WebSocket mesaj dinleme (I/O-bound)
2. Keepalive gonderme (I/O-bound, timer-based)
3. Web arama (I/O-bound)
4. URL'den icerik cekme (I/O-bound)
5. LLM model cagrisi (I/O-bound - Ollama'ya HTTP istegi)
6. JSON parsing (CPU-bound, ama cok kucuk)

6 islemin tamami I/O-bound. Bu durumda:

```
Thread kullanimi:
  10 esanli oturum * 10 aiohttp istegi = 100 thread
  Bellek: 100 * 64 KB = 6.4 MB
  Context switch: 100 * 3 us * 1000 switch/s = 300 ms/s CPU zamani

Coroutine kullanimi:
  10 esanli oturum * 10 aiohttp istegi = 100 coroutine
  Bellek: 100 * 1 KB = 100 KB (64x tasarruf)
  Context switch: 100 * 2 us * 1000 switch/s = 200 ms/s (benzer)
  AMA: Kernel mode gecisi yok -> pratikte daha hizli
```

### 3.2.4 Sinirlamalar

1. **CPU-bound gorevler:** Coroutine modeli CPU-bound islemlerde faydali degil. JSON parsing, string islemleri gibi CPU islemleri event loop'u bloklar.

2. **Python GIL:** Thread modeli de CPU-bound islemlerde paralellik saglamaz. Gercek CPU paralelligi icin multiprocessing gerekir.

3. **Bellek fragmentasyonu:** Cok sayida coroutine olusturulup yok edildiginde Python'un bellek yoneticisi fragmentasyona ugrabilir.


---

## 3.3 aiohttp vs requests: Connection Pooling ve TCP Connection Reuse

### 3.3.1 Temel Fark

```
requests (senkron):
    import requests
    r1 = requests.get(url1)  # TCP bagla -> istek -> yanit -> TCP kapat
    r2 = requests.get(url2)  # TCP bagla -> istek -> yanit -> TCP kapat
    # Her istek ayri TCP baglantisi (Session kullanilmazsa)

aiohttp (asenkron):
    async with aiohttp.ClientSession() as session:
        r1 = await session.get(url1)  # TCP bagla -> istek -> yanit
        r2 = await session.get(url2)  # AYNI TCP baglantisi -> istek -> yanit
        # Connection pool otomatik yonetilir
```

### 3.3.2 Connection Pool Matematigi

TCP baglantisi kurma maliyeti:
```
T_TCP = 1 RTT (SYN + SYN-ACK + ACK)
T_TLS = 2 RTT (TLS 1.2) veya 1 RTT (TLS 1.3)

Lokal ag (Docker -> Ollama): T_TCP ~ 0.5 ms, TLS yok
Internet (Google search):     T_TCP ~ 50 ms, T_TLS ~ 100 ms
```

N ardisik istek icin:
```
requests (Session yok):
  T_total = N * (T_TCP + T_TLS + T_req + T_resp)
  Internet: T_total = N * (50 + 100 + T_data) = N * (150 + T_data) ms

aiohttp (connection pool):
  T_total = T_TCP + T_TLS + N * (T_req + T_resp)  [ayni host'a]
  Internet: T_total = 150 + N * T_data ms

  Tasarruf = (N-1) * 150 ms
```

LocoDex'te her arastirmada Ollama'ya ~10 istek yapilir:
```
requests:  10 * 0.5 ms = 5 ms (TCP overhead)
aiohttp:   0.5 ms + 0 = 0.5 ms (tek baglanti, reuse)
Tasarruf:  4.5 ms (lokal agda ihmal edilebilir)
```

Ama asil fayda paralellik:
```
requests (senkron):
  T_total = sum(T_i) = T_1 + T_2 + ... + T_10
  Ortalama T_i = 30 saniye (model inference)
  T_total = 10 * 30 = 300 saniye

aiohttp (asenkron, paralel):
  T_total = max(T_i) = max(T_1, T_2, ..., T_10)
  T_total = ~30 saniye (hepsi paralel)
  Hizlanma: 10x
```

Ancak LocoDex'te model cagrilari genellikle ardisik yapiliyor (her adim oncekinin sonucuna bagli), dolayisiyla bu 10x hizlanma pratikte gerceklesmez. Paralel calisan kisim: web aramalari (smart_multilingual_research.py satir 541-551, 4 sorgu sirayla ama her sorgunun sonuclari paralel cekilebilir).

### 3.3.3 aiohttp ClientSession Ic Yapisi

```python
class ClientSession:
    def __init__(self, connector=None):
        self._connector = connector or TCPConnector(
            limit=100,           # Toplam baglanti siniri
            limit_per_host=0,    # Host basina sinir (0 = sinirsiz)
            ttl_dns_cache=10,    # DNS cache suresi (saniye)
            keepalive_timeout=15 # Idle baglanti tutma suresi
        )
```

LocoDex'te her `call_local_model` cagrisinda yeni ClientSession olusturuluyor:
```python
# smart_multilingual_research.py satir 51
async with aiohttp.ClientSession() as session:
    # ...
```

**Bu bir anti-pattern!** Her cagri icin yeni session = yeni connection pool = TCP connection reuse yok.

Dogru kullanim:
```python
class SmartMultilingualResearcher:
    def __init__(self, ...):
        self._session = aiohttp.ClientSession()

    async def call_local_model(self, ...):
        async with self._session.post(...) as response:
            # Ayni session, connection reuse mumkun
```

### 3.3.4 Hesaplama Karmasikligi

- Connection pool lookup: O(1) (hash map ile host -> connection)
- TCP connection reuse: O(1) (pool'dan cek)
- DNS cache lookup: O(1) (hash map)
- Yeni connection kurma: O(1) amortized (TCP handshake)

N istek, M benzersiz host:
```
requests (Session yok): O(N) TCP handshake
requests (Session var):  O(M) TCP handshake + O(N) istek
aiohttp:                 O(M) TCP handshake + O(N) istek (ayni, ama async)
```


---

## 3.4 concurrent.futures.ThreadPoolExecutor

### 3.4.1 LocoDex'teki Kullanim

smart_multilingual_research.py satirlari 376-379:
```python
with concurrent.futures.ThreadPoolExecutor() as executor:
    search_results = await asyncio.get_event_loop().run_in_executor(
        executor, sync_search
    )
```

Bu pattern: senkron (blocking) fonksiyonu asenkron event loop'ta calistirma.

`googlesearch` kutuphanesi senkron. Dogrudan `await googlesearch.search()` yazilamaz. Cozum: thread pool'da senkron fonksiyonu calistir, sonucu await ile bekle.

### 3.4.2 Thread Pool Sizing Stratejisi

Varsayilan thread pool boyutu (Python 3.8+):
```
default_workers = min(32, os.cpu_count() + 4)
```

**Neden bu formul?**

Amdahl Yasasi'ndan turetime:
```
S(N) = 1 / ((1 - P) + P/N)

burada:
  S(N) = N thread ile hizlanma
  P    = paralellenebilir kisim (0 ile 1 arasi)
  N    = thread sayisi

I/O-bound islemler icin P ~ 0.95 (zamanin %95'i I/O beklemede):
  S(4)  = 1 / (0.05 + 0.95/4)  = 1/0.2875 = 3.48x
  S(8)  = 1 / (0.05 + 0.95/8)  = 1/0.1688 = 5.92x
  S(16) = 1 / (0.05 + 0.95/16) = 1/0.1094 = 9.14x
  S(32) = 1 / (0.05 + 0.95/32) = 1/0.0797 = 12.55x
  S(64) = 1 / (0.05 + 0.95/64) = 1/0.0648 = 15.43x
  S(inf)= 1 / 0.05             = 20x (teorik maksimum)

32'den sonra kazanim azaliyor:
  S(32)/S(16) = 12.55/9.14 = 1.37x
  S(64)/S(32) = 15.43/12.55 = 1.23x

Diminishing returns. 32, iyi bir uzlasma noktasi.
```

### 3.4.3 Thread Pool + asyncio Entegrasyonu

`run_in_executor` dahili calismasi:

```python
# Pseudo-code
async def run_in_executor(executor, func, *args):
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    def callback(result):
        loop.call_soon_threadsafe(future.set_result, result)

    executor.submit(func, *args).add_done_callback(callback)
    return await future
```

Adimlar:
1. asyncio Future olustur (coroutine bekleyebilsin diye)
2. Thread pool'a senkron fonksiyonu gonder
3. Thread'de fonksiyon calisir (event loop bloklanmaz)
4. Tamamlaninca `call_soon_threadsafe` ile event loop'a bildir
5. Future resolve olur, `await` devam eder

**Thread-safety notu:** `call_soon_threadsafe` gerekli cunku farkli thread'den event loop'a callback eklemek thread-safe degildir. Bu fonksiyon internal bir pipe/socketpair ile event loop'u uyandirarak thread-safe erisim saglar.

### 3.4.4 LocoDex'te Neden ThreadPoolExecutor?

```
Alternatifler:
1. asyncio.to_thread (Python 3.9+): Daha modern, dahili ThreadPoolExecutor kullanir
2. ProcessPoolExecutor: CPU-bound icin, ama burada gereksiz (GIL sorunu yok, I/O-bound)
3. googlesearch'in async versiyonu: Mevcut degil

run_in_executor secimi dogru cunku:
- googlesearch senkron
- Web arama I/O-bound (network bekler)
- Thread pool'da calistirmak event loop'u bloklamaz
- Process overhead gereksiz (fork + pickle maliyeti)
```

### 3.4.5 Sinirlamalar

1. **Her cagri yeni ThreadPoolExecutor:** `with concurrent.futures.ThreadPoolExecutor() as executor:` her seferinde yeni pool olusturur. Thread olusturma maliyeti: ~100 mikrosaniye per thread. Iyilestirme: Sinif seviyesinde paylasilmis executor kullanmak.

2. **Executor boyutu belirtilmemis:** Varsayilan min(32, cpu_count+4) kullanilir. Docker container'da cpu_count() konteyner limitini degil host CPU sayisini dondurebilir. Bu, gereksiz fazla thread olusturabilir.


---

## 3.5 GIL (Global Interpreter Lock) ve I/O-Bound Tasks

### 3.5.1 GIL Nedir?

CPython'da (standart Python implementasyonu) GIL, herhangi bir anda sadece bir thread'in Python bytecode calistirmasina izin veren mutex'tir:

```
Thread 1: [Python bytecode] [GIL BIRAK] [I/O bekle] [GIL AL] [Python bytecode]
Thread 2:                   [GIL AL]    [Python BC]  [GIL BIRAK]
```

**GIL'in Matematiksel Etkisi:**

N thread, P = paralellenebilir CPU-bound oran:
```
T_ideal(N) = T_serial + T_parallel/N
T_GIL(N)   = T_serial + T_parallel * 1  (GIL nedeniyle paralellik yok)

CPU-bound (P = 1.0):
  T_ideal(4) = T/4
  T_GIL(4)   = T    (hic hizlanma yok, hatta GIL contention nedeniyle daha yavas!)

I/O-bound (CPU orani = 0.05):
  Thread I/O beklerken GIL'i birakir.
  T_GIL(N) ~ T_CPU + T_IO/N  (I/O paralellesiyor!)
```

### 3.5.2 LocoDex'te GIL Etkisi

LocoDex'in islem profili:
```
Islem Turu        CPU Zamani    I/O Zamani    Oran
------------------------------------------------------------------
Web arama          0.01s         2.0s         %0.5 CPU
Icerik cekme       0.05s         1.0s         %5 CPU
JSON parsing       0.01s         0s           %100 CPU
LLM model cagrisi  0.01s         30.0s        %0.03 CPU
WebSocket mesaj    0.001s        0.01s        %10 CPU
------------------------------------------------------------------
TOPLAM (tek arama) 0.081s        33.01s       %0.25 CPU
```

GIL'in etkisi: Zamanin %99.75'i I/O beklemede gecirildigi icin GIL pratikte SIFIR etki yapar.

Bu yuzden asyncio (coroutine) LocoDex icin ideal secim:
- GIL sorunu yok (tek thread, bytecode paralelligi gereksiz)
- I/O multiplexing ile verimli bekleme
- Thread olusturma overhead'i yok

### 3.5.3 GIL Release Mekanizmasi

GIL sunlarda birakilir:
1. I/O operasyonlari (socket.read, file.read)
2. time.sleep()
3. C extension'lari (NumPy operasyonlari vs.)
4. Her N bytecode instruction'da (Python 3.2+: GIL switch interval = 5ms)

```python
# sys.getswitchinterval() = 0.005 saniye (5 ms)
# Her 5 ms'de GIL diger thread'lere firsat verir

Thread 1: [====5ms====][GIL birak][bekle...][GIL al][====5ms====]
Thread 2:              [GIL al][====5ms====][GIL birak]
```

### 3.5.4 Python 3.13+ Free-Threaded CPython (Gelecek)

Python 3.13'ten itibaren deneysel "no-GIL" modu (PEP 703):
```
Derle: ./configure --disable-gil

Etki:
  CPU-bound threading artik paralel calisir
  Ama: Reference counting thread-safe degildir -> atomic operations eklenecek
  Performans kaybı: Tek thread'de %5-10 yavaslik (atomic operations nedeniyle)
```

LocoDex icin etki: Hemen hemen sifir. Zaten I/O-bound.


---

## 3.6 asyncio.wait_for Timeout Mekanizmasi

### 3.6.1 Zamanlayici Implementasyonu

server.py satir 338:
```python
data = await asyncio.wait_for(websocket.receive_text(), timeout=300)
```

Dahili implementasyon:

```python
async def wait_for(fut, timeout):
    loop = asyncio.get_event_loop()

    # 1. Coroutine'i Task'a sar
    if asyncio.iscoroutine(fut):
        fut = asyncio.ensure_future(fut)

    # 2. Timeout callback olustur
    waiter = loop.create_future()
    timeout_handle = loop.call_later(timeout, _cancel_and_wait, fut, waiter)

    # 3. Task tamamlaninca waiter'i resolve et
    fut.add_done_callback(functools.partial(_release_waiter, waiter))

    try:
        # 4. Bekle: ya task tamamlanir ya timeout olur
        return await waiter
    except asyncio.CancelledError:
        # 5. Timeout oldu -> TimeoutError firlat
        raise asyncio.TimeoutError()
    finally:
        timeout_handle.cancel()
```

### 3.6.2 Timer Heap Implementasyonu

asyncio timer'lari min-heap veri yapisinda saklanir:

```
Heap yapisi (ornek, 3 timer):

            Timer(t=30s, keepalive)
           /                        \
    Timer(t=300s, receive)    Timer(t=600s, model)

Heap property: parent.when <= child.when
```

**Islemler:**

```
Timer ekleme (heapq.heappush): O(log N)
  - Yeni timer heap'in sonuna eklenir
  - Sift-up ile dogru pozisyona yerlesirlir

Timer tetikleme (heapq.heappop): O(log N)
  - Root'taki (en kucuk) timer cikarilir
  - Son eleman root'a tasinir
  - Sift-down ile dogru pozisyona yerlestirilir

Timer iptal (handle.cancel): O(1)
  - Timer "iptal edildi" olarak isaretlenir
  - Heap'ten cikarilmaz (lazy deletion)
  - Pop sirasinda iptal edilmis timer'lar atlanir
```

### 3.6.3 Sayisal Ornek - LocoDex Timer Analizi

Tek arastirma oturumunda aktif timer'lar:

```
Timer 1: keepalive_task  -> asyncio.sleep(30)  -> her 30s tekrar
Timer 2: receive timeout -> wait_for(300s)      -> tek seferlik
Timer 3: model timeout   -> aiohttp timeout(300s) -> her model cagrisinda

Timer heap boyutu: 3 (kucuk)
heappush/heappop: O(log 3) = O(1.58) ~ O(1) (pratikte sabit zaman)
```

10 esanli oturum icin:
```
Timer sayisi: 10 * 3 = 30
heappush/heappop: O(log 30) = O(4.9) ~ 5 karsilastirma
Bu hala cok hizli: ~50 nanosaniye per islem
```

### 3.6.4 Timeout Kes ilismesi (Cascading Timeouts)

LocoDex'te ic ice timeout'lar:

```
[wait_for(300s)] -- WebSocket receive
    |
    +-- [run_research()]
           |
           +-- [call_local_model()]
                  |
                  +-- [aiohttp.post(timeout=300s)] -- Ollama istegi
                         |
                         +-- [TCP socket read] -- Kernel seviyesi timeout
```

Eger Ollama 300 saniye icinde yanit vermezse:
1. aiohttp.post TimeoutError firlatir
2. call_local_model exception yakalar, hata mesaji dondurur
3. run_research devam eder (rapor icindeki analiz eksik kalir)
4. wait_for 300s timeout'u AYRI: kullanicinin yeni mesaj gondermesini bekler

Bu iki 300 saniye AYRI ZAMAN DILIMLERI icin isler: biri model cagirma, digeri kullanici mesaji bekleme. Carpisma yok.

### 3.6.5 Hassasiyet ve Sinirlamalar

**Timer hassasiyeti:**
```
asyncio.sleep(30) gercek bekleme suresi:
  En iyi:  30.000 saniye (event loop bos)
  Tipik:   30.001 - 30.010 saniye (diger callback'ler calisirken)
  En kotu: 30.0 + T_blocking saniye (event loop bloklanmissa)
```

Event loop'u bloklayan islem varsa (ornegin buyuk JSON parsing):
```python
# Bu event loop'u bloklar:
data = json.loads(huge_json_string)  # 100 MB JSON -> 500 ms CPU

# Bu surede tum timer'lar gecikir:
# keepalive 30.5s'de tetiklenir (0.5s gecikme)
# timeout 300.5s'de tetiklenir
```

LocoDex'te en buyuk blocking riski: `json.loads(data)` (server.py satir 346). Tipik mesaj boyutu < 1 KB oldugu icin pratikte sorun degil. Ama arastirma sonucu 100 KB+ olabilir -> `websocket.send_json({"type": "result", "data": answer})` burada serialization ~1-5 ms surebilir.

### 3.6.6 Alternatif Timeout Mekanizmalari

| Mekanizma | Avantaj | Dezavantaj |
|-----------|---------|------------|
| asyncio.wait_for | Basit, stdlib | Coroutine'i iptal eder (geri alinamaz) |
| asyncio.wait(timeout=) | Birden fazla task icin | Daha karmasik API |
| async_timeout | 3. parti, context manager | Ek bagimllik |
| Manuel timer + CancelledError | Tam kontrol | Karmasik kod |

LocoDex'te `wait_for` dogru secim: tek coroutine, basit timeout gereksinimleri.

---

## Genel Sonuc ve Trade-off Ozeti

| Karar | Secim | Alternatif | Neden Bu? |
|-------|-------|------------|-----------|
| Iletisim | WebSocket | HTTP Polling, SSE | Full-duplex, dusuk overhead, 40+ mesaj |
| Server | uvicorn (tek worker) | gunicorn multi-worker | I/O-bound, Docker, kucuk olcek |
| Concurrency | asyncio coroutine | threading, multiprocessing | GIL irrelevant, I/O-bound, bellek verimli |
| HTTP client | aiohttp | requests, httpx | Async native, connection pool |
| Retry | tenacity exp. backoff | Manuel retry loop | Clean API, proven library |
| Container | Docker single service | Kubernetes, docker-compose multi | Tek servis, basit deploy |
| Timeout | 300-600s | Daha kisa/uzun | LLM inference suresi profili |
| Keepalive | 30s app-level | TCP keepalive, WS ping/pong | NAT traversal, proxy uyumlulugu |
| Rate limit | sleep(1) | Token bucket, leaky bucket | Basit, tek kullanici yeterli |
| Sync blocking | ThreadPoolExecutor | ProcessPoolExecutor | I/O-bound, thread yeterli |
