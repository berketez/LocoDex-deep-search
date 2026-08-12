# BOLUM 1: FastAPI + WebSocket Mimarisi

## 1.1 HTTP REST vs WebSocket: Bant Genisligi ve Gecikme Karsilastirmasi

### 1.1.1 Teorik Temel

HTTP/1.1 protokolunde her istek-yanit dongusunde sabit bir overhead vardir. Bu overhead, HTTP header'larindan kaynaklanir.

**HTTP/1.1 Header Overhead Hesabi:**

Tipik bir HTTP GET istegi:
```
GET /research HTTP/1.1\r\n
Host: localhost:8001\r\n
Content-Type: application/json\r\n
Accept: application/json\r\n
Connection: keep-alive\r\n
User-Agent: Mozilla/5.0...\r\n
\r\n
```

Minimum header boyutu: ~200-800 byte (ortalama ~400 byte).

Yanit header'i da benzer: ~200-600 byte.

**Toplam HTTP overhead (tek istek-yanit):**
```
C_HTTP = H_req + H_resp
C_HTTP = 400 + 400 = 800 byte (ortalama)
```

**WebSocket Frame Overhead:**

RFC 6455'e gore bir WebSocket frame'inin overhead'i:
```
- FIN + RSV + Opcode:    1 byte
- MASK + Payload length: 1 byte  (payload < 126 byte ise)
                         3 byte  (payload < 65536 byte ise)
                         9 byte  (payload >= 65536 byte ise)
- Masking key:           4 byte  (client -> server yonunde)
                         0 byte  (server -> client yonunde)
```

**Minimum WebSocket frame overhead:**
```
C_WS_client = 2 + 4 = 6 byte   (client -> server, kucuk mesaj)
C_WS_server = 2 + 0 = 2 byte   (server -> client, kucuk mesaj)
```

**Bant Genisligi Tasarruf Formulu:**

N tane mesaj icin toplam overhead karsilastirmasi:

```
HTTP toplam overhead   = N * C_HTTP = N * 800 byte
WS toplam overhead     = C_handshake + N * C_WS_avg
```

Burada C_handshake ~ 400 byte (tek seferlik HTTP Upgrade istegi).
C_WS_avg ~ 6 byte (ortalama frame overhead).

```
Tasarruf = N * 800 - (400 + N * 6) = 794N - 400 byte
```

N = 1 icin: 394 byte tasarruf (HTTP hala yakin)
N = 100 icin: 79,000 byte tasarruf (%99.5 azalma)
N = 1000 icin: 793,600 byte tasarruf

**Sonuc:** WebSocket, N >> 1 (cok mesajli) senaryolarda bariz ustun. LocoDex'te her arastirma oturumunda ortalama 30-50 progress mesaji gonderiliyor (server.py satirlari 89-282 arasindaki `send_json` cagrilari). N ~ 40 icin:

```
HTTP overhead  = 40 * 800 = 32,000 byte
WS overhead    = 400 + 40 * 6 = 640 byte
Tasarruf orani = 1 - 640/32000 = %98
```

### 1.1.2 Gecikme (Latency) Analizi

HTTP/1.1 icin her istek-yanit dongusunde:

```
T_HTTP = T_TCP_handshake + T_TLS_handshake + T_req + T_process + T_resp
       = 1 RTT + 2 RTT + T_req + T_process + T_resp      (TLS 1.2)
       = 3 RTT + T_data                                    (ilk istek)
```

Connection: keep-alive ile sonraki istekler:
```
T_HTTP_keepalive = T_req + T_process + T_resp = 1 RTT + T_data
```

WebSocket icin:
```
T_WS_handshake = T_TCP + T_TLS + T_HTTP_Upgrade = 3 RTT + 1 RTT = 4 RTT (tek seferlik)
T_WS_message   = T_frame                        = T_data (ek RTT yok!)
```

**LocoDex'teki Somut Ornek:**

server.py'de arastirma sirasinda onlarca progress mesaji gonderiliyor:
```python
await websocket.send_json({"type": "progress", "step": 0.05, "message": "..."})
# ... 30-50 arasi mesaj
await websocket.send_json({"type": "result", "data": answer})
```

Eger bu HTTP polling ile yapilsaydi (her 2 saniyede bir istek):
```
T_polling = 50 * (1 RTT + T_processing)
```

Lokal ag icin RTT ~ 0.5 ms, internet icin RTT ~ 50 ms.

Lokal agda (Docker container <-> host):
```
T_HTTP_polling = 50 * 0.5ms = 25 ms toplam overhead
T_WS_push      = 0 ms ek overhead (sunucu dogrudan push eder)
```

Internet uzerinden (uzak kullanici):
```
T_HTTP_polling = 50 * 50ms = 2500 ms = 2.5 saniye ek gecikme
T_WS_push      = 0 ms ek overhead
```

### 1.1.3 Neden WebSocket Secildi - Alternatifler

| Yontem | Avantaj | Dezavantaj | LocoDex icin Uygunluk |
|--------|---------|------------|----------------------|
| HTTP Polling | Basit implementasyon | N * overhead, gecikme | Kotu - 40+ mesaj var |
| HTTP Long Polling | Server push mumkun | Her mesajda yeni baglanti | Orta - karmasik |
| Server-Sent Events (SSE) | Hafif, tek yonlu push | Sadece server -> client | Iyi - ama client mesaji lazim |
| WebSocket | Full-duplex, dusuk overhead | Handshake karmasikligi | En iyi - bidirectional lazim |
| HTTP/2 Server Push | Multiplexed | Browser destegi kisitli | Overkill |
| gRPC Streaming | Yuksek performans | Protobuf gerektir | Overkill |

LocoDex'te client hem arastirma istegi gonderir (client -> server) hem de progress guncellemelerini alir (server -> client). Bu bidirectional gereksinim SSE'yi dislar. WebSocket dogru secim.

### 1.1.4 Hesaplama Karmasikligi

- WebSocket handshake: O(1) - tek seferlik
- Mesaj gonderme: O(L) burada L = mesaj uzunlugu (byte)
- Maskeleme: O(L) - her byte XOR islemi
- Toplam N mesaj icin: O(N * L_avg)
- HTTP'de ayni is: O(N * (H + L_avg)) burada H = header boyutu

### 1.1.5 Sinirlamalar

1. **Proxy/Firewall Uyumsuzlugu:** Bazi kurumsal proxy'ler WebSocket'i engelleyebilir (HTTP CONNECT tunnel gerekir)
2. **Durum Yonetimi:** Sunucu her baglanti icin bellek tutar. 10,000 esanlastirilmis baglanti icin ~ 10,000 * (soket tampon boyutu) ~ 10,000 * 64KB = 640 MB
3. **Yeniden Baglanti:** HTTP otomatik retry yapar; WebSocket'te client reconnection mantigi yazilmali
4. **Load Balancer:** Sticky session gerektirir (WebSocket baglantisi tek sunucuya baglidir)


---

## 1.2 WebSocket Handshake Protokolu (RFC 6455)

### 1.2.1 Handshake Mekanizmasi

WebSocket baglantisi bir HTTP Upgrade istegi ile baslar:

**Client -> Server:**
```
GET /research_ws HTTP/1.1
Host: localhost:8001
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

**Server -> Client:**
```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

### 1.2.2 Sec-WebSocket-Accept Hesaplama Algoritmasi

RFC 6455 Section 4.2.2'ye gore:

```
Sec-WebSocket-Accept = Base64(SHA-1(Sec-WebSocket-Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
```

Somut ornek:
```
Sec-WebSocket-Key = "dGhlIHNhbXBsZSBub25jZQ=="

Adim 1: Birlestir
  input = "dGhlIHNhbXBsZSBub25jZQ==" + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
  input = "dGhlIHNhbXBsZSBub25jZQ==258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

Adim 2: SHA-1 hash
  SHA-1(input) = 0xb3 0x7a 0x4f 0x2c 0xc0 0x62 0x4f 0x16 0x90 0xf6
                 0x46 0x06 0xcf 0x38 0x59 0x45 0xb2 0xbe 0xc4 0xea

Adim 3: Base64 encode
  Base64(hash) = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
```

Bu GUID ("258EAFA5-E914-47DA-95CA-C5AB0DC85B11") sabittir ve RFC 6455'te tanimlidir. Amaci: sunucunun gercekten WebSocket protokolunu anladigini dogrulamak.

### 1.2.3 Frame Formati

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|     Extended payload length continued, if payload len == 127  |
+-------------------------------+-------------------------------+
|                               |Masking-key, if MASK set to 1  |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------+-------------------------------+
|                     Payload Data continued ...                |
+---------------------------------------------------------------+
```

**Opcode degerleri:**
- 0x0: Continuation frame
- 0x1: Text frame (LocoDex'te JSON mesajlari icin kullanilir)
- 0x2: Binary frame
- 0x8: Connection close
- 0x9: Ping
- 0xA: Pong

### 1.2.4 Maskeleme Algoritmasi (XOR)

Client -> Server yonundeki tum frame'ler MASK edilmelidir:

```
masking_key = [K0, K1, K2, K3]    (4 byte rastgele)

transformed_data[i] = original_data[i] XOR masking_key[i mod 4]
```

**Neden maskeleme?** Cache poisoning saldirilarina karsi. Aracidaki proxy'lerin WebSocket verisini HTTP verisi olarak yorumlamamasi icin.

**Somut Sayisal Ornek:**

LocoDex'te tipik bir progress mesaji:
```json
{"type": "progress", "step": 0.15, "message": "Arastirma stratejisi belirleniyor..."}
```

Bu mesaj ~ 75 byte. Frame overhead:
```
FIN=1, Opcode=0x1 (text):  1 byte     -> 0x81
MASK=1, Length=75:          1 byte     -> 0xCB (1_1001011)
Masking key:                4 byte     -> rastgele
Payload:                    75 byte    -> XOR ile maskelenmis
------
Toplam:                     81 byte    (payload'in %8'i overhead)
```

### 1.2.5 Hesaplama Karmasikligi

- SHA-1 hesabi: O(n) burada n = girdi boyutu (~80 byte, sabit) -> pratikte O(1)
- Base64 encode: O(n) -> pratikte O(1)
- XOR maskeleme: O(L) burada L = payload uzunlugu
- Frame parsing: O(1) (header okuma) + O(L) (payload)


---

## 1.3 Full-Duplex Iletisim: TCP Soket Teorisi

### 1.3.1 TCP Full-Duplex Temeli

TCP (RFC 793) dogasi geregi full-duplex'tir. Her TCP baglantisi iki bagimsiz byte stream'i icerir:

```
Client -----> [Send Buffer | Receive Buffer] -----> Server
Client <----- [Receive Buffer | Send Buffer] <----- Server
```

Her yon icin ayri sequence number'lar:
```
Client -> Server: SEQ_c, ACK_c
Server -> Client: SEQ_s, ACK_s
```

WebSocket bu TCP full-duplex ozelligini HTTP'nin yarı-duplex kisitlamasindan kurtararak dogrudan kullanir.

### 1.3.2 Nagle Algoritmasi

Nagle algoritmasi (RFC 896) kucuk TCP segment'lerini birlestirerek ag verimliligini arttirir:

**Algoritma:**
```
if (unacknowledged_data_in_flight):
    buffer_new_data()      # Bekle, biriktir
    if (buffer >= MSS or ACK_received):
        send(buffer)       # Tampon dolu veya ACK geldi, gonder
else:
    send(data)             # Bos hat, hemen gonder
```

MSS (Maximum Segment Size) = MTU - IP_header - TCP_header = 1500 - 20 - 20 = 1460 byte (tipik Ethernet).

**LocoDex Icin Etkisi:**

server.py'deki progress mesajlari (50-100 byte) MSS'ten cok kucuk. Nagle algoritmasi bu mesajlari tamponlayip birlestirebilir.

Sorun: Kullanici arayuzunde progress guncelemeleri gecikmeli gorunur.

**Cozum:** TCP_NODELAY opsiyonu. uvicorn ve asyncio altyapisi varsayilan olarak TCP_NODELAY kullanir, cunku interaktif uygulamalarda dusuk gecikme onemlidir.

```
Nagle aktif:   Mesaj gonderim gecikmesi = 0 ile 200ms arasi (ACK bekleme)
Nagle deaktif: Mesaj gonderim gecikmesi ~ 0ms (hemen gonderilir)
```

**Trade-off:**
```
TCP_NODELAY = True:   Dusuk gecikme, daha fazla kucuk paket, %3-5 daha fazla bant genisligi
TCP_NODELAY = False:  Yuksek verimlilik, kucuk mesajlarda gecikme
```

LocoDex icin TCP_NODELAY dogru secim: 50 byte'lik progress mesajlarinin aninda iletilmesi kullanici deneyimi icin kritik.


---

## 1.4 Keepalive Mekanizmasi

### 1.4.1 Neden 30 Saniye?

server.py satirlari 321-329:
```python
async def keepalive_task():
    while True:
        await asyncio.sleep(30)  # Her 30 saniyede bir ping
        await websocket.send_json({"type": "keepalive"})
```

Bu 30 saniye degeri tesadufi degil. Uc katmanli analiz:

**Katman 1: TCP Keepalive**

Linux varsayilan TCP keepalive degerleri:
```
tcp_keepalive_time  = 7200 saniye (2 saat) - ilk probe'dan once bekleme
tcp_keepalive_intvl = 75 saniye            - probe'lar arasi bekleme
tcp_keepalive_probes = 9                    - toplam deneme sayisi
```

TCP keepalive cok yavas: 2 saat + 9 * 75s = 2 saat 11 dakika sonra baglanti olumunu tespit eder. Bu LocoDex icin kabul edilemez.

**Katman 2: NAT/Firewall Timeout**

Cogu NAT/firewall'un idle connection timeout'u:
```
Tipik NAT timeout   = 60-300 saniye
AWS ALB timeout     = 60 saniye (varsayilan)
Nginx proxy_timeout = 60 saniye (varsayilan)
Docker bridge       = sinursiz (lokal)
```

30 saniye < 60 saniye: En kotu durumdaki NAT timeout'undan kucuk. Bu, baglantiyi canli tutar.

**Katman 3: Kullanici Deneyimi**

Arastirma sureci 2-10 dakika surebilir. Kullanici bu surede hicbir guncelleme almamaktan rahatsiz olur. 30 saniye, "sistem hala calisiyor" mesaji icin uygun bir aralik.

### 1.4.2 TCP Keepalive vs Application-Level Keepalive Karsilastirmasi

| Ozellik | TCP Keepalive | Application-Level (LocoDex) |
|---------|--------------|---------------------------|
| Katman | Transport (L4) | Application (L7) |
| Varsayilan Aralik | 7200s | 30s |
| Tespit Suresi | ~2 saat | ~30-60s |
| NAT Traversal | Yetersiz | Yeterli |
| Uygulama Durumu | Bilinmez | Kontrol edilebilir |
| Overhead | TCP header (40 byte) | WS frame + JSON (~30 byte) |
| Proxy Destegi | Proxy goremez | Proxy JSON'u iletir |

### 1.4.3 Keepalive Bant Genisligi Maliyeti

10 dakikalik arastirma oturumunda:
```
Keepalive mesaj sayisi = (10 * 60) / 30 = 20 mesaj
Her mesaj boyutu       = {"type": "keepalive"} ~ 22 byte + WS frame overhead 6 byte = 28 byte
Toplam keepalive trafigi = 20 * 28 = 560 byte

Arastirma raporunun boyutu ~ 5,000 - 50,000 byte
Keepalive orani = 560 / 5000 = %11 (kucuk rapor) ile 560 / 50000 = %1.1 (buyuk rapor)
```

Bu ihmal edilebilir bir overhead.

### 1.4.4 Sinirlamalar

1. **Tek yonlu keepalive:** Kod sadece server -> client keepalive gonderiyor. Client tarafinin baglanti durumu kontrol edilmiyor.
2. **Ping/Pong yerine JSON:** RFC 6455 Ping (0x9) ve Pong (0xA) frame'leri tanimlar. Bunlar daha verimli (2 byte overhead vs JSON'un 28 byte'i). Ancak bazi proxy'ler Ping/Pong'u iletmeyebilir; JSON mesaji daha guvenli.
3. **Eksik:** Client tarafindan pong/ack mekanizmasi yok. Sunucu, keepalive'in client'a ulasip ulasmadigini bilemiyor.


---

## 1.5 Async/Await Concurrency Modeli

### 1.5.1 Event Loop Temeli

Python asyncio event loop'u tek thread uzerinde cooperative multitasking yapar:

```
Event Loop Dongusu:
    while True:
        events = poll_IO_events()       # epoll/kqueue syscall
        for event in events:
            ready_coroutine = find_coroutine(event)
            result = ready_coroutine.send(None)  # Coroutine'i devam ettir
            if result is StopIteration:
                cleanup(ready_coroutine)
```

**Cooperative vs Preemptive Multitasking:**

```
Cooperative (asyncio):
    Gorev1: calis... await IO... [duraklat] ...calis [duraklat]
    Gorev2:          [bekle]     calis... await IO... [duraklat]
    Gorev3:                                           calis...

    Avantaj: Context switch maliyeti ~ 0 (sadece Python stack frame degisimi)
    Dezavantaj: CPU-bound gorev tum loop'u bloklar

Preemptive (threading):
    Thread1: calis... [OS keser] ... calis [OS keser]
    Thread2:          [OS verir]  calis... [OS keser]

    Avantaj: CPU-bound gorevler otomatik paylastirilir
    Dezavantaj: Context switch maliyeti ~ 1-10 mikrosaniye
```

### 1.5.2 Coroutine Scheduling

server.py'deki research_websocket fonksiyonu:
```python
@app.websocket("/research_ws")
async def research_websocket(websocket: WebSocket):
    await websocket.accept()
    keepalive = asyncio.create_task(keepalive_task())
    # ...
    answer = await researcher.run_research(topic)
```

Burada uc coroutine paralel calisiyor:
1. `research_websocket` - ana isleyici
2. `keepalive_task` - 30 saniyede bir ping
3. `run_research` (icinde `call_local_model`, `search_web_advanced` vs.)

**Scheduling Sirasi:**

```
t=0ms:    research_websocket baslat
t=1ms:    websocket.accept() -> IO bekle -> YIELD
t=2ms:    [IO hazir] websocket.accept() tamamlandi
t=3ms:    keepalive_task olustur (asyncio.create_task)
t=4ms:    websocket.receive_text() -> IO bekle -> YIELD
          keepalive_task: asyncio.sleep(30) -> timer bekle -> YIELD
          [event loop bos - poll'da bekle]
t=100ms:  [veri geldi] receive_text() tamamlandi
t=101ms:  run_research() baslat
t=102ms:  call_local_model() -> aiohttp POST -> IO bekle -> YIELD
          [event loop diger gorevlere bakar]
t=30000ms: keepalive_task: sleep bitti -> send_json(keepalive) -> IO -> YIELD
t=30001ms: [IO hazir] keepalive gonderildi -> asyncio.sleep(30) -> YIELD
t=35000ms: [aiohttp yanit geldi] call_local_model() devam eder
```

### 1.5.3 LocoDex'teki Somut Async Akisi

server.py'de kritik bir yapi:
```python
data = await asyncio.wait_for(websocket.receive_text(), timeout=300)
```

`asyncio.wait_for` uc eylem yapar:
1. Coroutine'i Task olarak sarar
2. Bir timer baslatir (300 saniye)
3. Timer dolunca asyncio.TimeoutError firlatir

Dahili implementasyon:
```python
# asyncio.wait_for pseudo-code:
async def wait_for(coro, timeout):
    task = create_task(coro)
    timer = call_later(timeout, task.cancel)
    try:
        return await task
    except CancelledError:
        raise TimeoutError
    finally:
        timer.cancel()
```

### 1.5.4 Hesaplama Karmasikligi

Event loop'un tek iterasyonu:
- `epoll_wait` syscall: O(1) amortized (red-black tree)
- Hazir event'leri isleme: O(k) burada k = hazir event sayisi
- Timer heap'ten sonraki timer'i kontrol: O(log n) burada n = aktif timer sayisi

Toplam: O(k + log n) per iteration.

N esanli WebSocket baglantisi icin:
- Bellek: O(N) (her baglanti icin soket + tampon)
- CPU per iteration: O(k + log N) burada k = o iterasyonda hazir event sayisi

### 1.5.5 Sayisal Ornek

LocoDex'te 10 esanli arastirma oturumu dusunelim:
```
Her oturum:
  - 1 WebSocket baglantisi
  - 1 keepalive timer (30s)
  - 5-10 aiohttp istegi (web arama + model cagirma)
  - Ortalama 40 progress mesaji

Event loop'taki entity sayisi:
  - 10 WebSocket soketi
  - 10 keepalive timer'i
  - 50-100 aiohttp soketi (zirve aninda)
  - Toplam: ~120 entity

epoll per iteration: O(1) amortized
Timer heap: O(log 10) ~ 3.3 karsilastirma
Toplam: her iteration < 10 mikrosaniye

Sonuc: Tek thread, tek event loop ile 10 esanli oturum rahatlikla yonetilebilir.
100 esanli oturum: ~1200 entity, hala < 50 mikrosaniye per iteration.
```


---

## 1.6 uvicorn ASGI Server

### 1.6.1 ASGI Protokolu

ASGI (Asynchronous Server Gateway Interface), WSGI'nin asenkron versiyonudur:

```
WSGI (sync):
    def application(environ, start_response):
        # Her istek bir thread/process'te

ASGI (async):
    async def application(scope, receive, send):
        # Her istek bir coroutine'de
```

**ASGI Scope Tipleri:**
- `http`: HTTP istekleri (server.py satirlari 301-310)
- `websocket`: WebSocket baglantilari (server.py satirlari 312-418)
- `lifespan`: Uygulama yasam dongusu

### 1.6.2 uvicorn Worker Modeli

Dockerfile'daki komut:
```dockerfile
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--log-level", "debug"]
```

Bu tek worker modunda calisir. uvicorn'un worker modelleri:

```
Mod 1: Tek worker (varsayilan, LocoDex'te kullanilan)
    [uvicorn process]
       |
       +-- asyncio event loop
              |
              +-- coroutine 1 (WebSocket #1)
              +-- coroutine 2 (WebSocket #2)
              +-- coroutine N (WebSocket #N)

Mod 2: Multi-worker (gunicorn + uvicorn)
    [gunicorn master]
       |
       +-- [uvicorn worker 1] -- event loop -- coroutine'ler
       +-- [uvicorn worker 2] -- event loop -- coroutine'ler
       +-- [uvicorn worker K] -- event loop -- coroutine'ler
```

### 1.6.3 libuv vs asyncio

uvicorn `uvloop` kullanabilir (libuv'un Python binding'i):

```
asyncio varsayilan event loop:  Pure Python selector
uvloop:                         libuv (C kutuphanesi) uzerine insa edilmis

Performans karsilastirmasi (HTTP hello world benchmark):
  asyncio:  ~20,000 req/s
  uvloop:   ~70,000 req/s

  Hizlanma: ~3.5x
```

uvloop'un avantaji: libuv, epoll/kqueue/IOCP'yi C seviyesinde sariyor, Python callback overhead'ini minimuze ediyor.

LocoDex'te `uvicorn[standard]` paketi (requirements.txt satir 20) uvloop'u iceriyor.

### 1.6.4 LocoDex'te Worker Sayisi Karari

Neden tek worker?

```
CPU core sayisi = N_cores
Onerilen worker sayisi (CPU-bound):  N_cores
Onerilen worker sayisi (IO-bound):   2 * N_cores + 1

LocoDex IO-bound:
  - Web arama: network IO
  - Model cagirma: network IO (Ollama/LM Studio'ya HTTP istegi)
  - WebSocket mesajlasma: network IO

  CPU-bound islem yok (tum "dusunme" isini LLM yapiyor).
```

Tek worker yeterli cunku:
1. Tum islemler IO-bound -> asyncio tek thread'de halleder
2. WebSocket baglantilari ayni process'te olmali (shared state)
3. Docker container icinde kaynak sinirli
4. `--reload` flag'i gelistirme icin kullaniliyor (production'da kaldirilir)

### 1.6.5 Sinirlamalar

1. **Tek worker = tek process = tek CPU core:** CPU-bound islem varsa (ornegin buyuk JSON parsing) event loop'u bloklar. LocoDex'te bu sorun yok cunku agir islem LLM tarafinda.

2. **`--reload` production'da kullanilmamali:** File system watcher ek overhead yaratir. Dockerfile'daki bu flag sadece gelistirme icin.

3. **Graceful shutdown:** Uzun suren arastirma (10 dakika) sirasinda sunucu kapatilirsa, WebSocket baglantilarinin duzgun kapatilmasi icin SIGTERM handling gerekir. server.py'de finally blogu (satir 411-418) bu isi yapiyor ama keepalive.cancel() ile sinirli.

4. **Bellek siniri:** Her WebSocket baglantisi ~ 64KB buffer kullanir. Docker container'in bellek limiti (Dockerfile'da belirtilmemis) asildigi durumda OOM Killer devreye girer.
