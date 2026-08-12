# KONU 1: Iteratif Arastirma Pipeline Tasarimi

## 1.1 Pipeline Asamalari ve Zaman Karmasikligi Analizi

LocoDex Deep Search pipeline'i asagidaki 8 asamadan olusur. Her asama icin koddaki somut karsiliklari ve zaman karmasikligini inceliyoruz.

### Asama 1: Topic Analysis (Konu Analizi)

**Koddaki karsiligi:** `detect_language()` (real_deep_research.py L504-540) + LLM cagri (ilk arama stratejisi prompt'u, L565-591)

**Islem detayi:**
- Dil algilama: karakter ve kelime listesi tarama. Turkce karakterler (c, g, i, s, u, o) icin O(|chars| * |text|), kelime eslestirme icin O(|words| * |text|).
- LLM ile konu analizi: sabit sureli bir inference cagri. API latency + token generation suresi.

**Zaman karmasikligi:**

```
T_topic = T_lang_detect + T_llm_inference

T_lang_detect = O(k * n)
    k = toplam dil karakter sayisi (~30)
    n = metin uzunlugu (karakter)

T_llm_inference = O(L_api + t_gen * max_tokens)
    L_api = network latency (sabit, ~50-200ms)
    t_gen = token basina uretim suresi (~30-80ms/token, model bagimlI)
    max_tokens = sistem parametresi
```

**Sayisal ornek:** n=200 karakter sorgu, k=30 karakter -> 6000 karsilastirma (< 1ms). LLM cagri: L_api=100ms, 200 token * 50ms = 10s. Toplam: ~10s. Dil algilama ihmal edilebilir.

### Asama 2: Query Generation (Sorgu Olusturma)

**Koddaki karsiligi:** `generate_smart_queries()` (smart_multilingual.py L213-298), `generate_research_queries()` (together_open_deep_research.py L237-257)

**Islem detayi:** LLM'e konu verilir, Q adet arama sorgusu olusturulur. Iki sinif:
- SmartMultilingualResearcher: Tek LLM cagri -> 4 sorgu
- DeepResearcher: Iki LLM cagri (planning + JSON parsing) -> degisken sorgu sayisi

**Zaman karmasikligi:**

```
T_query_gen = c * T_llm_inference
    c = LLM cagri sayisi (1 veya 2)
```

DeepResearcher icin:
```
T_query_gen = T_planning_llm + T_json_parsing_llm
            = 2 * (L_api + t_gen * max_tokens)
```

**Sayisal ornek:** Iki LLM cagri, her biri ~10s -> T_query_gen ~ 20s.

### Asama 3: Web Search (Web Aramasi)

**Koddaki karsiligi:** `search_web()` (real_deep_research.py L363-430), `search_web_advanced()` (smart_multilingual.py L300-386), `_search_engine_call()` (together_open_deep_research.py L344-395)

**Islem detayi:** Q sorgu icin her biri R sonuc donduren web aramasi yapilir. Google Search oncelikli, Tavily/DuckDuckGo fallback.

**Zaman karmasikligi:**

```
T_search = Q * (T_google + T_rate_limit)
    Q = sorgu sayisi (4-5)
    T_google = Google API latency (~1-3s)
    T_rate_limit = asyncio.sleep(1) = 1s (sabit)

Toplam: T_search = Q * (T_google + 1)
```

Eger Google basarisiz olursa fallback eklenir:
```
T_search_fallback = Q * (T_google_timeout + T_tavily + 1)
```

**Sayisal ornek:** Q=5 sorgu, T_google=2s -> T_search = 5*(2+1) = 15s. Her sorgu R=8 sonuc donerse toplam 40 URL.

### Asama 4: Content Extraction (Icerik Cikarma)

**Koddaki karsiligi:** `extract_content_from_url()` (real_deep_research.py L432-476), `extract_and_analyze_content()` (smart_multilingual.py L388-429)

**Islem detayi:** Her URL icin HTTP GET + HTML parsing + text extraction. BeautifulSoup ile script/style elementleri temizlenir.

**Zaman karmasikligi:**

```
T_extract = S * (T_http + T_parse)
    S = toplam sonuc sayisi (islenecek URL)
    T_http = HTTP GET suresi (~0.5-5s, timeout=10-15s)
    T_parse = BeautifulSoup parsing + text extraction

T_parse = O(H)
    H = HTML dokuman boyutu (karakter)
```

BeautifulSoup'un DOM tree olusturma karmasikligi O(H), text extraction O(N) burada N = DOM node sayisi.

**Sayisal ornek:** S=20 URL, T_http=2s (ortalama), T_parse=0.1s -> T_extract = 20 * 2.1 = 42s. Ama seri islendiginden bu en uzun adim. Not: real_deep_research.py'de seri, together_open_deep_research.py'de `asyncio.gather()` ile paralel.

### Asama 5: Source Evaluation (Kaynak Degerlendirme)

**Koddaki karsiligi:** `evaluate_source_reliability()` (real_deep_research.py L52-150), smart_multilingual.py L431-469

**Islem detayi:** Her kaynak icin bir LLM cagri yapilarak 0-100 (veya 1-10) skor atanir.

**Zaman karmasikligi:**

```
T_eval = S * T_llm_reliability
    T_llm_reliability = L_api + t_gen * 200  (max_tokens=200)
```

**Sayisal ornek:** S=20 kaynak, T_llm_reliability ~ 5s -> T_eval = 100s. Bu cok pahali! Pipeline'in en yavas ikinci asamasi.

### Asama 6: Synthesis (Bilgi Sentezleme)

**Koddaki karsiligi:** Icin kaynak analizi (real_deep_research.py L714-757), extract_specific_data (L192-230), detect_conflicting_information (L152-190)

**Islem detayi:** Her kaynak icin icerik analizi LLM cagri + spesifik veri cikarma + celiski tespiti.

**Zaman karmasikligi:**

```
T_synthesis = S * (T_llm_analysis + T_llm_data_extract) + T_llm_conflict
    T_llm_analysis: max_tokens=500
    T_llm_data_extract: max_tokens=300
    T_llm_conflict: max_tokens=500 (bir kez)
```

### Asama 7: Report Generation (Rapor Olusturma)

**Koddaki karsiligi:** Final prompt (real_deep_research.py L842-891), generate_comprehensive_report (smart_multilingual.py L624-716)

**Islem detayi:** Tum sentezlenmis verilerin tek bir LLM cagriyla raporlanmasi.

**Zaman karmasikligi:**

```
T_report = L_api + t_gen * max_tokens_final
    max_tokens_final = 4000-5000 (en buyuk token butcesi)
```

**Sayisal ornek:** 4000 token * 50ms/token = 200s ~ 3.3 dakika. Pipeline'in en yavas asamasi.

### Asama 8: Quality Assessment (Kalite Degerlendirmesi)

**Koddaki karsiligi:** `iterative_research_analysis()` (smart_multilingual.py L471-520), `evaluate_research_completeness()` (together_open_deep_research.py L409-441)

**Islem detayi:** Mevcut verilerin yeterliligi LLM ile degerlendirilir. Eksik alanlar tespit edilir.

**Zaman karmasikligi:**

```
T_quality = T_llm_evaluation + T_llm_json_parse
           = 2 * (L_api + t_gen * max_tokens)
```

### Toplam Pipeline Suresi

**Seri calisma (worst case):**

```
T_total = T_topic + T_query + T_search + T_extract + T_eval + T_synthesis + T_report + T_quality

T_total = 10 + 20 + 15 + 42 + 100 + (20*10 + 20*5 + 10) + 200 + 20
        = 10 + 20 + 15 + 42 + 100 + 310 + 200 + 20
        = 717 saniye ~ 12 dakika
```

**Asama basina LLM cagri sayisi (S=20 kaynak, Q=5 sorgu):**

| Asama | LLM Cagri Sayisi | max_tokens | Toplam Token Uretimi |
|-------|------------------|------------|---------------------|
| Topic Analysis | 1-2 | 200 | ~300 |
| Query Generation | 1-2 | 500 | ~700 |
| Source Eval | S = 20 | 200 | ~4000 |
| Content Analysis | S = 20 | 500 | ~10000 |
| Data Extraction | S = 20 | 300 | ~6000 |
| Conflict Detection | 1 | 500 | ~500 |
| Final Report | 1 | 4000-5000 | ~4500 |
| Quality Check | 1-2 | 500 | ~700 |
| **TOPLAM** | **~67** | | **~26700** |

---

## 1.2 Iterative Deepening: Gap Analysis ile Eksik Alan Tespiti

### Teorik Temel

Iterative deepening, bilgi arama literaturunde "Information Foraging Theory" (Pirolli & Card, 1999) ile modellenebilir. Temel fikir: bir arastirmacinin bilgi toplama sureci, bir yirtici hayvanin yem arama davranisina benzer. "Information patches" (bilgi adalari) arasindan en verimli olani secilir.

LocoDex'te bu kavram, `evaluate_research_completeness()` (together_open_deep_research.py L409-441) ve `iterative_research_analysis()` (smart_multilingual.py L471-520) fonksiyonlarinda somutlasir.

### Bilgi Kapsama Orani (Coverage Ratio)

Kapsama oranini formalize edelim. Bir konu T icin gereken bilgi alanlarini K = {k_1, k_2, ..., k_m} olarak tanimlayalim. Her iterasyonda bulunan bilgi alt kumesini B_i ise:

```
Coverage(i) = |B_1 ∪ B_2 ∪ ... ∪ B_i| / |K|
```

Bu, set-theoretic bir tanim. Pratikte "bilgi alanlari" surekli bir uzaydir, ayrik degildir. Bu durumda vektorel yaklasim kullanilir:

Her bilgi alani k_j icin bir "tamamlanma derecesi" c_j in [0,1] tanimlayabiliriz:

```
Coverage(i) = (1/m) * sum_{j=1}^{m} c_j(i)
```

burada c_j(i), i. iterasyon sonunda k_j alaninin ne kadar karsilandigini gosterir.

**Koddaki karsiligi:** `iterative_research_analysis()` LLM'e mevcut ozeti gosterir ve "hangi konular eksik?" diye sorar. LLM'in cevabi implicitly bu coverage oranini tahmin eder. Eksik alanlarin sayisi 0'a dustugunde coverage ~ 1.0 kabul edilir.

### Azalan Verim Yasasi (Diminishing Returns)

Her ek iterasyon, giderek daha az yeni bilgi getirir. Bu, bilgi kuramindaki "redundancy" kavramina karsilik gelir:

```
Delta_Coverage(i) = Coverage(i) - Coverage(i-1)
```

Tipik olarak Delta_Coverage monoton azalir. Bunu modelleyelim:

```
Coverage(i) = 1 - (1 - alpha)^i
```

burada alpha, her iterasyondaki ortalama "yeni bilgi orani"dir. Turetme:

```
Baslangic: Coverage(0) = 0
Her adimda kalan boslugu alpha oraninda kapatiyoruz:
Coverage(i) = Coverage(i-1) + alpha * (1 - Coverage(i-1))
            = Coverage(i-1) + alpha - alpha * Coverage(i-1)
            = alpha + (1 - alpha) * Coverage(i-1)

Bu bir geometrik seri. Cozum:
Coverage(i) = 1 - (1-alpha)^i
```

**Sayisal ornek:** alpha = 0.4 (her iterasyon %40 yeni bilgi)

| Iterasyon | Coverage | Delta |
|-----------|----------|-------|
| 0 | 0.000 | - |
| 1 | 0.400 | 0.400 |
| 2 | 0.640 | 0.240 |
| 3 | 0.784 | 0.144 |
| 4 | 0.870 | 0.086 |
| 5 | 0.922 | 0.052 |
| 6 | 0.953 | 0.031 |

### Stopping Criterion (Durma Kriteri)

Ne zaman arastirma "yeterli"? Uc yaklasim vardir:

**1. Budget-based (Butce temelli):**
LocoDex'te kullanilan yaklasim budur. DeepResearcher sinifinda `budget=6` parametresi vardir (together_open_deep_research.py L33). Her iterasyonda `current_spending` artar. `current_spending >= budget` oldugunda durulur.

```
Dur: current_spending >= budget
```

Bu en basit ama en az "akilli" yontemdir. Bilgi yeterli olsa bile butce dolana kadar devam eder (gereksiz maliyet), veya bilgi yetersiz kalsa bile butce bitince durur (eksik arastirma).

**2. Threshold-based (Esik temelli):**
Kodda implicitly kullanilir. `evaluate_research_completeness()` bos liste dondururse iterasyon sonlanir (together_open_deep_research.py L135):

```python
additional_queries = [q for q in additional_queries if q]
if not additional_queries:
    break  # Durma kriteri: ek sorgu gerekmez
```

Bu, LLM'in "yeterli bilgi toplandi" demesine esittir. Matematiksel olarak:

```
Dur: Q_additional = {} (bos kume)
```

**3. Marginal-gain-based (Marjinal kazanc temelli):**
Kodda dogrudan uygulanmiyor ama en matematiksel yaklasim budur:

```
Dur: Delta_Coverage(i) < epsilon
```

burada epsilon bir esik degeri (ornegin 0.05). Bu, "son iterasyon %5'ten az yeni bilgi getirdiyse dur" anlamina gelir.

Yukardaki modelden: `Delta_Coverage(i) = alpha * (1-alpha)^{i-1} < epsilon`

Cozum: `i > 1 + log(epsilon/alpha) / log(1-alpha)`

**Sayisal ornek:** alpha=0.4, epsilon=0.05:
```
i > 1 + log(0.05/0.4) / log(0.6)
i > 1 + log(0.125) / log(0.6)
i > 1 + (-2.079) / (-0.511)
i > 1 + 4.07
i > 5.07
```

Yani 6 iterasyonda durulur -- bu, LocoDex'in default `budget=6` degeriyle uyumlu! Bu tesaduf degil: alpha=0.4 makul bir tahminse, 6 iterasyon %95+ kapsama saglar.

---

## 1.3 Progress Tracking: Non-Linear Ilerleme Egrisi

### Koddaki Gozlem

Progress degerleri incelendiginde lineer olmayan bir dagilim gorulur:

```
smart_multilingual_research.py:
  0.01 -> baslangic
  0.05 -> dil algilama
  0.07 -> dil sonucu
  0.10 -> strateji
  0.12 -> sorgular hazir
  0.15 + i*0.15 -> web aramasi (i=0..3, yani 0.15, 0.30, 0.45, 0.60)
  0.50 + i*0.03 -> kaynak analizi (i=0..9, yani 0.50..0.77)
  0.70 -> eksiklik analizi
  0.90 -> rapor hazirlaniyor
  0.95 -> rapor kayit
  1.00 -> tamam
```

Bu dagilim sigmoid-benzeri bir egri cikarir:

```
real_deep_research.py:
  0.05 -> baslangic
  0.08 -> dil algilama
  0.10 -> strateji
  0.30 -> icerik okuma (ortada buyuk atlama)
  0.90 -> rapor
  1.00 -> tamam
```

### Neden Sigmoid-Benzeri?

Ilerleme egrisi P(t) zamana karsi cizidiginde bir S-egrisi olusur. Bunun uc nedeni vardir:

**1. Baslangiç yavashigi (P ~ 0.0 - 0.2):** Ilk asamalar LLM inference gerektirir (konu analizi, sorgu olusturma). Tek seferde yapilir ama hizli ilerleme gostermez cunku sonuc gorulmez.

**2. Orta hiz (P ~ 0.2 - 0.8):** Web aramasi ve icerik analizi paralel olarak ilerler. Her URL islendikce progress artar. Bu en "gorunur" asama.

**3. Son yavaslama (P ~ 0.8 - 1.0):** Final rapor olusturma tek buyuk bir LLM cagridir (4000-5000 token). Bu tek basina 3+ dakika surer ama sadece 0.9->1.0 arasini temsil eder.

Bunu logistic (sigmoid) fonksiyonla modelleyebiliriz:

```
P(t) = 1 / (1 + exp(-k * (t - t_mid)))

burada:
  k = egim parametresi (ne kadar dik)
  t_mid = egri orta noktasi (t'nin yarisi)
```

Ancak LocoDex'teki ilerleme zamana degil, tamamlanan asamalara baglidir. Daha dogru model:

```
P(n) = sum_{i=1}^{n} w_i / sum_{i=1}^{N} w_i

burada:
  w_i = i. asama icin atanan progress agirligi
  n = tamamlanan asama sayisi
  N = toplam asama sayisi
```

Koddaki "atlamalar" (ornegin 0.30'dan 0.50'ye bir anda) bazi asamalarin daha fazla "agirlik" tasimasi nedeniyledir. Web aramasi ve icerik cikarma en cok kaynagi tuketir ama en cok "gorsel ilerleme" de saglar.

### Algilanan Ilerleme vs Gercek Ilerleme

Insan algisi icin Weber-Fechner yasasi gecerlidir:

```
Algilanan_ilerleme = k * ln(Gercek_ilerleme / I_0)

burada:
  k = algi sabiti
  I_0 = esik degeri
```

Bu, %10->%20 gecisinin %80->%90 gecisinden "daha buyuk" algildanmasina neden olur. LocoDex'in progress bar'i bunu telafi edemez cunku lineer 0-1 olcegi kullanir. Kullanicilar son %10'luk kismda "takilmis" hissedecektir.

**Cozum onerisi:** Logaritmik progress mapping:

```
P_displayed(t) = log(1 + alpha * P_real(t)) / log(1 + alpha)

alpha >> 1 icin baslangicta hizli ilerleme goruntusi, sonda yavaslar.
alpha = 9 icin: P_real=0.1 -> P_displayed=0.301, P_real=0.9 -> P_displayed=0.954
```

---

## 1.4 Paralel vs Seri Arastirma: Amdahl Yasasi

### Teorik Temel

Amdahl Yasasi (Gene Amdahl, 1967), bir programin paralellestirmeyle elde edebilecegi maksimum hizlanmayi verir:

```
Speedup(N) = 1 / ((1 - P) + P/N)

burada:
  P = paralelleştirilebilir oran (0 <= P <= 1)
  N = paralel isci sayisi (thread/process/coroutine)
  1-P = seri kisim (paralellestirilemeyen)
```

**Turetme:**

Toplam seri sure T_s olsun. Bu surenin P oranlik kismi paralellestirilebilir, (1-P) oranlik kismi seri kalmak zorunda.

```
T_seri = T_s
T_paralel = (1-P) * T_s + P * T_s / N
Speedup = T_seri / T_paralel
        = T_s / ((1-P)*T_s + P*T_s/N)
        = 1 / ((1-P) + P/N)
```

N -> sonsuz limitinde:
```
Speedup_max = 1 / (1-P)
```

### LocoDex'te Paralellik Analizi

Pipeline'daki asamalari paralellestirilebilir ve seri olarak siniflandiralim:

**Seri asamalar (paralellestirilemiyor):**
- Topic Analysis: sonraki asamalar buna bagimli -> SERI
- Query Generation: sorgu olusturulmadan arama yapilamaz -> SERI
- Final Report: tum veriler lazim -> SERI
- Quality Assessment: rapordan sonra -> SERI

**Paralellestirilebilir asamalar:**
- Web Search: sorgular birbirinden bagimsiz -> PARALEL (asyncio.gather)
- Content Extraction: URL'ler birbirinden bagimsiz -> PARALEL
- Source Evaluation: kaynaklar birbirinden bagimsiz -> PARALEL
- Content Analysis: kaynaklar birbirinden bagimsiz -> PARALEL

**Koddaki durum:**

together_open_deep_research.py `search_all_queries()` (L308-336) `asyncio.gather()` kullanir:
```python
res_list = await asyncio.gather(*tasks)  # L328
```

Ancak real_deep_research.py ve smart_multilingual_research.py'de arama ve analiz SERI yapilir:
```python
for i, query in enumerate(search_queries):  # L676
    results = await self.search_web(query, max_results=8)
    # ...
for i, result in enumerate(all_search_results[:20]):  # L691
    # ... seri islem
```

### P Orani Hesabi

Yukardaki sure tahminlerini kullanarak:

```
T_seri_kisimlar = T_topic + T_query + T_report + T_quality
                = 10 + 20 + 200 + 20 = 250s

T_paralel_kisimlar = T_search + T_extract + T_eval + T_synthesis
                   = 15 + 42 + 100 + 310 = 467s

T_total = 250 + 467 = 717s

P = 467 / 717 = 0.651 (% 65.1)
```

### Hizlanma Hesabi

```
N=1:  Speedup = 1 / (0.349 + 0.651/1) = 1.0x
N=2:  Speedup = 1 / (0.349 + 0.651/2) = 1 / 0.675 = 1.48x
N=4:  Speedup = 1 / (0.349 + 0.651/4) = 1 / 0.512 = 1.95x
N=8:  Speedup = 1 / (0.349 + 0.651/8) = 1 / 0.430 = 2.33x
N=16: Speedup = 1 / (0.349 + 0.651/16) = 1 / 0.390 = 2.56x
N->inf: Speedup_max = 1 / 0.349 = 2.87x
```

**Yorum:** P=0.651 ile maksimum teorik hizlanma 2.87x. Bu, pipeline'in seri kisimlari (ozellikle final rapor uretimi = 200s) nedeniyle sinirlidir. 4 paralel worker ile 1.95x hizlanma (717s -> 367s ~ 6 dk) elde edilir.

### Darbogazlar

1. **Final Report Generation (200s):** Tek LLM cagri, paralellestirilemiyor. Tum pipeline'in %28'i.
2. **Source Evaluation (100s, seri halinde):** Her kaynak icin ayri LLM cagri. Paralellestirilebilir ama rate limiting ile kisitli.
3. **LLM Rate Limiting:** Ayni anda N istek gondermek API throttling'e yol acar. Pratikte N etkin olarak 3-5 ile sinirli.

---

## 1.5 Error Propagation: Hata Yayilimi

### Teorik Cerceve

Bir pipeline'da i. asamanin hata orani e_i olsun. Eger hatalar bagimsiz ve kumulatif ise, n asama sonra hatasiz sonuc olasiligi:

```
P_correct = prod_{i=1}^{n} (1 - e_i)
```

Kucuk e_i degerleri icin (e_i << 1):

```
P_correct ≈ 1 - sum_{i=1}^{n} e_i
```

Bu, hatalarin yaklasik olarak toplandigi anlamina gelir.

### LocoDex'te Hata Kaynaklari

Her asama icin tipik hata oranlarini tahmin edelim:

| Asama | Hata Turu | Tahmini e_i | Aciklama |
|-------|-----------|-------------|----------|
| Topic Analysis | Yanlis dil algilama | 0.05 | 'c cedilla' bug'i (Fransizca icin) |
| Query Generation | Alakasiz sorgu | 0.10 | LLM hallucination |
| Web Search | Sonucsuz arama | 0.08 | Google rate limit, bos sonuc |
| Content Extraction | HTTP hatasi/timeout | 0.15 | Siteler cevap vermeyebilir |
| Source Evaluation | Yanlis skor | 0.12 | LLM subjektif degerlendirme |
| Synthesis | Yanlis ozet | 0.10 | LLM hallucination |
| Report Generation | Tutarsiz rapor | 0.08 | Celiski, tekrar, eksiklik |
| Quality Assessment | Yanlis gap analizi | 0.10 | LLM eksik tespit edemez |

```
P_correct = (0.95)(0.90)(0.92)(0.85)(0.88)(0.90)(0.92)(0.90)
          = 0.460

P_error = 1 - 0.460 = 0.540 = %54
```

Bu korkutucu bir rakam: 8 asamali pipeline'da en az bir hatanin olusma olasiligi %54! Ancak bu, "herhangi bir hata" demektir -- gercekte hatalarin cogu tolere edilebilir (ornegin bir URL'nin timeout olmasi sonucu degistirmez).

### Hata Siniflandirmasi

Hatalari "kritik" ve "tolere edilebilir" olarak ayiralim:

**Kritik hatalar (raporu tamamen bozar):**
- Yanlis dil algilama -> tamamen yanlis dilde rapor
- Query generation basarisizligi -> hic arama yapilmiyor
- Final rapor LLM hatasi -> bos rapor

**Tolere edilebilir hatalar (rapor kalitesini dusurur):**
- Bir URL timeout -> diger kaynaklar kullanilir
- Yanlis guvenilirlik skoru -> yanlis kaynak onceligi
- Eksik gap analizi -> bir ek iterasyon eksik kalir

Kritik hata olasiligi cok daha dusuktur:

```
P_critical_error = 1 - (0.95)(0.90)(0.92) ~ 1 - 0.786 = 0.214 = %21
```

### Hata Telafi Mekanizmalari (Koddaki)

1. **Fallback chains:** Google -> Tavily/DuckDuckGo (real_deep_research.py L396-420)
2. **Try-except blokları:** Her asama kendi hatasini yakalar, pipeline devam eder
3. **Default degerler:** reliability_score=50 (real_deep_research.py L123), language='en' (L540)
4. **LLM retry:** tenacity ile 3 deneme, exponential backoff (llms.py L37)
5. **Iterative deepening:** Bir iterasyonda eksik kalan bilgi sonraki iterasyonda tamamlanabilir

### Hata Propagasyon Modeli (Bayesian Yaklasim)

Daha sofistike bir model: her asama i, onceki asamanin ciktisi uzerinde calisir. Eger onceki asama hatali cikti verdiyse, sonraki asamanin da hatali olma olasiligi artar.

P(E_i | E_{i-1}) > P(E_i) -- kosullu bagimsizlik ihlali.

Markov zinciri modeli:

```
P(dogru -> dogru) = 1 - e_i        (temiz girdi, temiz cikti)
P(dogru -> hatali) = e_i            (temiz girdi, hatali cikti)
P(hatali -> dogru) = r_i            (hatali girdi ama duzeltildi)
P(hatali -> hatali) = 1 - r_i       (hatali girdi, hatali cikti)
```

burada r_i, i. asamanin "hata duzeltme" kapasitesidir. LLM-based asamalar icin r_i ~ 0.3-0.5 olabilir (LLM bazen hatali girdiyi fark eder ve duzeltir).

Transition matrisi:

```
T_i = [ 1-e_i    e_i  ]
      [  r_i   1-r_i  ]
```

n asama sonraki durum dagilimi:

```
[P_correct, P_error]_n = [1, 0] * T_1 * T_2 * ... * T_n
```

**Sayisal ornek:** 3 asama, hepsi e=0.1, r=0.3:

```
T = [0.9  0.1]
    [0.3  0.7]

Asama 1 sonrasi: [0.9, 0.1]
Asama 2 sonrasi: [0.9*0.9 + 0.1*0.3, 0.9*0.1 + 0.1*0.7] = [0.84, 0.16]
Asama 3 sonrasi: [0.84*0.9 + 0.16*0.3, 0.84*0.1 + 0.16*0.7] = [0.804, 0.196]
```

Bagimsiz modelde: P_error = 1 - 0.9^3 = 0.271
Markov modelde: P_error = 0.196

Farki: r_i > 0 oldugunda (hata duzeltme kapasitesi) gercek hata orani, bagimsiz modelden DAHA DUSUK. Bu iyi haber: LLM'ler onceki asamalardaki bazi hatalari "duzeltebilir".

---

## 1.6 Alternatif Pipeline Tasarimlari ve Trade-off'lar

### Alternatif 1: Breadth-First vs Depth-First Arastirma

**LocoDex'in mevcut yaklasimi:** Breadth-first. Once tum sorgular aranir, sonra tum URL'ler islenir, sonra rapor yazilir.

**Alternatif: Depth-first.** Her sorgu icin hemen arastirma-analiz-rapor dongusu yapilir, sonra birlestirilir.

| Kriter | Breadth-First | Depth-First |
|--------|--------------|-------------|
| Ilk sonuc gorme suresi | Yavas (tum asamalar bitmeli) | Hizli (ilk sorgu biter bitmez) |
| Bilgi kalitesi | Yuksek (tum kaynaklar karssilastirilir) | Dusuk (erken sorgularin etkisi fazla) |
| Celiski tespiti | Kolay (tum kaynaklar mevcut) | Zor (artimsal karsilastirma) |
| Bellek kullanimi | O(S * C) (tum kaynaklar) | O(C) (tek seferde bir kaynak) |

### Alternatif 2: Map-Reduce Arastirma

1. **Map:** Her sorgu bagimsiz olarak arastirma yapar, kendi mini-raporunu olusturur.
2. **Reduce:** Mini-raporlar tek bir final rapora birlestirilir.

Avantaj: Map asamasi tamamen paralel, P->1.0, Speedup->N.
Dezavantaj: Reduce asamasinda bilgi kaybi, tekrar eden bilgiler.

### Alternatif 3: Reinforcement Learning-Based Arastirma

Arastirma surecini MDP (Markov Decision Process) olarak modelleyebiliriz:
- **State:** mevcut bilgi kumesi, coverage orani
- **Action:** yeni sorgu sec, kaynak sec, rapor yaz, dur
- **Reward:** coverage artisi - maliyet (LLM cagri, zaman)
- **Policy:** hangi aksiyonun en iyi sonucu verecegini gren

Bu, LocoDex'in mevcut heuristic yaklasimina gore optimal stopping criterion ve sorgu secimi saglayabilir. Ancak training verisi ve reward fonksiyonu tasarimi gerektirir.

---

## 1.7 Sinirlamalar

1. **LLM darbogazI:** Pipeline'in %70+'i LLM inference suresidir. LLM hizi pipeline hizini dogrudan belirler.

2. **Seri final rapor:** Tek buyuk LLM cagri, paralellestirilemiyor. Amdahl'in sert siniri.

3. **Deterministik olmayan cikti:** Ayni sorgu icin ayni LLM'den farkli sonuclar gelebilir (temperature > 0). Tekrarlanabilirlik sorunu.

4. **Maliyet olceklenmesi:** S kaynak, Q sorgu icin LLM cagri sayisi O(S*Q). Buyuk arastirmalar maliyetli.

5. **Rate limiting:** Web search API'lari ve LLM API'lari istekleri throttle eder. Gercek paralellik sinirli.

6. **Bilgi guncelliği:** LLM training data cutoff'undan sonraki bilgiler icin sadece web'e bagimli. Guncel konularda LLM kendi bilgisini kullanamaz.
