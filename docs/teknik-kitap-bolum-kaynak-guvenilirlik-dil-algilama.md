# LocoDex Deep Search -- Teknik Kitap
# Bolum: Kaynak Guvenilirlik, Dil Algilama, Icerik Kalite, Prompt-Based Evaluation

**Yazar:** Berke Tezgocen
**Tarih:** 2026-03-15
**Proje:** LocoDex Deep Search v1.0
**Kaynak Dosyalar:**
- `real_deep_research.py` (ana arastirma motoru)
- `smart_multilingual_research.py` (cok dilli arastirma)
- `evals.py` (LLM-as-a-judge)
- `tavily_search.py` (arama entegrasyonu)
- `server.py` (FastAPI sunucu)

---

# KONU 1: Kaynak Guvenilirlik Degerlendirme Sistemi

## 1.1 Domain-Based Trust Scoring: Uc Katmanli Guvenilirlik

### 1.1.1 Teorik Temel: Bilgi Bilimi (Information Science) Perspektifi

Kaynak guvenilirliginin domain bazinda siniflandirilmasi, bibliometri (bibliometrics) ve bilgi biliminin temel kavramlarina dayanir. Bu yaklasimin kokenleri 1927'de Gross ve Gross'un atif analizi calismasina kadar gider; modern halini ise Eugene Garfield'in 1955'te olusturdugu Impact Factor kavrami ile almistir.

**Temel hipotez:** Bir bilgi kaynaginin guvenilirligi, o kaynagi ureten kurumun **epistemik otoritesi** (epistemic authority) ile dogrudan iliskilidir. Bu iliski soyle formalize edilir:

```
Trust(source) = f(institutional_authority, peer_review_rigor, editorial_standards, track_record)
```

LocoDex'in uc katmanli sistemi bu karmasik fonksiyonu bir **heuristik siniflandirma** ile basitlestirir:

| Katman | Skor Araligi | Domain Sayisi | Ornek Domainler | Epistemik Gerekce |
|--------|-------------|---------------|-----------------|-------------------|
| **High Trust** | 70-100 | 39 | arxiv.org, nature.com, ieee.org, nasa.gov | Peer-review, kurumsal otorite, editoryal surec |
| **Medium Trust** | 40-69 | 16 | wikipedia.org, reddit.com, forbes.com | Topluluk denetimi var ama formal peer-review yok |
| **Low Trust** | 10-39 | 7 | blog.*, wordpress.com, blogspot.com | Bireysel icerik, editoryal kontrol yok |

**Kodda karsiligi** (`real_deep_research.py`, satirlar 20-44):

```python
self.trusted_domains = {
    'high': [
        'arxiv.org', 'nature.com', 'science.org', 'pubmed.ncbi.nlm.nih.gov',
        'ieee.org', 'acm.org', 'academic.oup.com', 'springer.com',
        'cambridge.org', 'mit.edu', 'stanford.edu', 'harvard.edu',
        # ... toplam 39 domain
    ],
    'medium': [
        'wikipedia.org', 'reddit.com', 'quora.com', 'forbes.com',
        # ... toplam 16 domain
    ],
    'low': [
        'blog.', 'wordpress.com', 'blogspot.com', 'tumblr.com',
        # ... toplam 7 domain
    ]
}
```

### 1.1.2 Bu Siniflandirmanin Bilgi Bilimi Temeli

**Scholarly Communication Piramidi:**

Bilgi biliminde kaynaklar bir piramit halinde siniflandirilir. En tepede primer kaynaklar (orijinal arastirma), ortada sekonder kaynaklar (derleme, sentez), en altta tersiyer kaynaklar (ansiklopedi, genel bilgi) yer alir.

LocoDex bu piramidi uc katmana indirger:

1. **High Trust = Primer + Sekonder Akademik Kaynaklar**
   - arxiv.org: Preprint sunucusu. Peer-review oncesi ama akademik topluluk tarafindan fiilen denetlenir. ArXiv'in moderasyon sistemi var: endorsement gerektiren bir yayin sureci (tam peer-review olmasa da).
   - nature.com, science.org: En yuksek impact factor'lu dergiler. Nature'in rejection rate'i %92'dir -- yani her 100 makaleden sadece 8'i yayinlanir.
   - ieee.org, acm.org: Muhendislik ve bilgisayar bilimleri icin gold standard.

2. **Medium Trust = Topluluk Denetimli Kaynaklar**
   - wikipedia.org: "Herkes duzenleyebilir" dezavantaji var, ama arastirmalar Wikipedia'nin Britannica ile karsilastirmada benzer hata oranina sahip oldugunu gostermistir (Nature, 2005). Yine de Wikipedia'nin kendisi akademik kaynak olarak kabul edilmez.
   - reddit.com: r/science, r/AskHistorians gibi modere edilen subreddit'ler yuksek kaliteli olabilir, ama genel reddit icerigi guvenilir degildir.

3. **Low Trust = Bireysel Icerik Platformlari**
   - blog.*, wordpress.com: Editoryal kontrol yok. Her turlu bilgi yayinlanabilir. Ancak bazi teknik bloglar (ornegin Google Research Blog) son derece yetkilidir -- bu da domain-based siniflandirmanin **sinirlamasi**dir.

### 1.1.3 Neden Bu Yaklasim? Alternatifleri

**Secilen yaklasim: Static Domain Whitelist**

Avantajlari:
- O(1) lookup (dictionary/hashmap)
- Deterministik: ayni URL her zaman ayni skora yol acar
- Hesaplama maliyeti neredeyse sifir

Dezavantajlari:
- **Granularity eksikligi:** google.com hem Google Research Blog hem Google Ads icin "high trust"
- **Sabit liste eskir:** Yeni akademik kaynaklar eklenmez
- **Subdomain korlugu:** `blog.nature.com` ile `nature.com/articles` ayni sinifta

**Alternatif 1: PageRank-Tabanli Guvenilirlik**

```
PR(A) = (1-d) + d * SUM_i [PR(T_i) / C(T_i)]
```
Burada d = damping factor (~0.85), T_i = A'ya link veren sayfalar, C(T_i) = T_i'nin toplam cikis link sayisi.

PageRank her sayfaya tum web grafinin topolojisine dayali bir skor atar. Bu, domain bazinda siniflandirmadan cok daha ince grenli (fine-grained) bir guvenilirlik olcusu verir. Ancak:
- Gercek zamanli hesaplama olanaksiz (Google'in kendisi bile gun/hafta bazinda hesaplar)
- Tam web grafine erisim gerekir
- Lokal bir uygulamada pratik degildir

**Alternatif 2: Citation Count Tabanli**

```
Impact(source) = citation_count / time_since_publication
```
Akademik makaleler icin ise yarar ama web sayfalari icin citation veritabani yoktur.

**Alternatif 3: Makine Ogrenimi ile Siniflandirma**

Feature'lar: domain yasi, HTTPS varmi, reklam yogunlugu, icerik/reklam orani, yazim kalitesi, vb.
Etiketli veri seti gerektirir. Arastirma gosteriyor ki bu yaklasimlar %85-92 accuracy verir (Castillo et al., 2011).

**LocoDex'in secimi neden mantikli?**
Lokal LLM uzerinde calisan bir sistem icin, domain whitelist en dusuk maliyet/fayda oranini sunar. Daha sofistike yontemler ya cok veri gerektirir (ML) ya da web topolojisine erisim ister (PageRank).

### 1.1.4 O(n) Analizi

Domain trust lookup:
```
Zaman: O(1) amortize -- Python dict lookup
Bellek: O(D) burada D = toplam domain sayisi = 39 + 16 + 7 = 62
```

Domain eslestirme (URL'den domain cikarma):
```
Zaman: O(|url|) -- URL string'i uzerinde karakter tarami
```

Toplam guvenilirlik degerlendirme pipeline'i (LLM cagrilari dahil):
```
Zaman: O(N * T_llm) burada N = kaynak sayisi, T_llm = ortalama LLM inference suresi (~2-30s)
Bellek: O(N * C) burada C = ortalama icerik boyutu (3000-4000 karakter)
```

### 1.1.5 Sinirlamalar

1. **medium.com high trust'ta:** Medium bir blog platformu ama LocoDex onu "high" olarak siniflandirmis (L29). Medium'da akademik kalitede yazilar da, sahte bilgi de bulunabilir.

2. **stackoverflow.com high trust'ta:** Topluluk denetimli bir platform olarak "medium" daha uygun olabilir.

3. **Subdomain farkliliklari:** `docs.google.com` (resmi dokumantasyon) ile `sites.google.com` (herkesin olusturabileceği siteler) ayni guvenilirlik katmaninda.

4. **.gov ve .edu korlugu:** Sadece belirli ABD kurumlari listelenmiş. Turkiye'deki tubitak.gov.tr veya .edu.tr domainleri yok.

### 1.1.6 Somut Sayisal Ornek

Diyelim ki "Transformer modellerin performansi" konusu arastiriliyor ve su 4 kaynak bulundu:

| # | URL | Domain Trust | LLM Skoru | Final Skor |
|---|-----|-------------|-----------|------------|
| 1 | arxiv.org/abs/2401.xxxxx | High | 85 | 85 |
| 2 | en.wikipedia.org/wiki/Transformer | Medium | 72 | 72 |
| 3 | towardsdatascience.com/transformers-... | (medium.com subdomain) | 60 | 60 |
| 4 | randomtech.blogspot.com/transformers | Low | 35 | 35 |

Filtering threshold = 30/100 (real_deep_research.py, L788):
- Kaynak 1, 2, 3: Score >= 30, KABUL
- Kaynak 4: Score = 35 >= 30, KABUL (ama zar zor)

Kaynak 4 kalite acidan zayif olmasina ragmen, 30 esigi cogu kaynagi gecirmektedir. Bu esik degeri oldukca dusuktur -- pratikte cok agresif filtreleme yapilmaz.

---

## 1.2 LLM-as-a-Judge Paradigmasi

### 1.2.1 Teorik Temel

LLM-as-a-Judge, bir buyuk dil modelini insan juri yerine koymaktir. Bu kavram Zheng et al. (2023) tarafindan "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" makalesinde sistematik olarak tanimlanmistir.

**Temel fikir:** Bir LLM'e yapi kurulmus bir prompt verilir, o da yapilandirilmis bir degerlendirme cikarir.

**Matematiksel formalizasyon:**

Bir LLM judge fonksiyonu soyle modellenir:

```
J: (x, y, r) -> s
```

Burada:
- x = girdi (URL, baslik, icerik ornegi, konu)
- y = degerlendirme kriterleri (rubric)
- r = referans bilgi (konu turu, guncel tarih)
- s = cikti skoru (0-100 arasi tamsayi)

LocoDex'te iki farkli skala kullaniliyor:

**Skala 1: 0-100** (`real_deep_research.py`, L58-113)
```python
reliability_prompt = f"""
Bu web kaynaginin guvenilirligini degerlendir:
...
SADECE BU FORMATTA CEVAP VER:
Guvenilirlik: [0-100 arasi skor]
"""
```

**Skala 2: 1-10** (`smart_multilingual_research.py`, L434-449)
```python
prompt = f"""
Bu web kaynaginin guvenilirligini 1-10 arasinda puanla:
...
Format: "Puan: X/10 - Gerekce"
"""
```

**Skala 3: 0-1 Binary** (`evals.py`, L19-79)
```python
# LLM-as-a-judge binary scoring
# Cikti: <answer>1</answer> veya <answer>0</answer>
```

### 1.2.2 Scoring Fonksiyonu: 0-100 Puan Uretme

Pratikte LLM'in urettigi skor su sekilde parse edilir:

```python
for line in lines:
    if line.startswith('Guvenilirlik:'):
        try:
            score_text = line.split(':')[1].strip()
            reliability_score = int(''.join(filter(str.isdigit, score_text)))
        except:
            pass
```

**Bu parsing'in matematiksel sonucu:**
- "Guvenilirlik: 85/100" -> `int(''.join(filter(str.isdigit, '85/100')))` = `int('85100')` = 85100
- BUG: Eger LLM "85/100" formatinda yazdiysa, filter(str.isdigit) hem 85'i hem 100'u alir ve "85100" olur.

Ancak pratikte cogu LLM "Guvenilirlik: 85" formatinda yazdigindan bu bug nadiren tetiklenir. Yine de defensive programming acisindan:

```python
# Duzeltilmis versiyon:
import re
match = re.search(r'(\d+)', score_text)
reliability_score = int(match.group(1)) if match else 50
```

Smart multilingual versiyonu bu bug'i DUZELTMIS durumda:
```python
score_match = re.search(r'(\d+)/10', evaluation)
score = int(score_match.group(1)) if score_match else 5
```

### 1.2.3 Inter-Rater Reliability: LLM Tutarliligi Sorunu

LLM'ler deterministik degildir. Temperature > 0 ile calistirildklarinda ayni girdi icin farkli skorlar uretirler. Bu, psikometrideki **inter-rater reliability** probleminin dijital karsilgidir.

**Cohen's Kappa ile olcum:**

```
kappa = (p_o - p_e) / (1 - p_e)
```

Burada:
- p_o = gozlenen uyusma orani (observed agreement)
- p_e = beklenen uyusma orani (expected agreement by chance)

Ornek: Ayni 10 kaynagi degerlendiren bir LLM'i 2 kez calistirdik (T=0.3):

| Kaynak | Run 1 | Run 2 | Uyusma |
|--------|-------|-------|--------|
| arxiv.org/paper1 | 88 | 85 | +/- 3 |
| wikipedia.org/X | 65 | 70 | +/- 5 |
| blog.example.com | 25 | 32 | +/- 7 |
| nature.com/Y | 92 | 90 | +/- 2 |
| reddit.com/Z | 55 | 48 | +/- 7 |

Tipik bir lokal LLM (7B-13B parametre) icin, temperature=0.3 ile:
- Ortalama sapma: +/- 5-10 puan (0-100 skalasinda)
- High/Low ayriminda (threshold: 30 veya 50): %85-90 tutarlilik
- Kesin sayi eslesmesi: %10-20

**LocoDex'in yaklasimi:**
- T=0.3 kullanilir (dusuk ama sifir degil)
- Tek seferlik degerlendirme (ensemble veya consensus yok)
- Default skor: 50 (parse hatasi durumunda)

**Neden tek LLM cagri yeterli (pragmatik gerekce):**
Her kaynak icin 3 kez cagirip ortalamasini almak guvenilirligi artirirdi, ama:
- Maliyet: 3x LLM inference suresi (lokal modelde 3x2s = 6s extra)
- 20 kaynak icin: 20 * 6s = 120 saniye ek sure
- Kazanim: +/- 5 puan hassasiyet iyilesmesi
- Bu trade-off, lokal LLM'ler icin pratikte degmez

### 1.2.4 Sinirlamalar

1. **Position Bias:** LLM'ler prompt'un basindaki bilgiyi daha cok dikkate alir. URL prompt'un basinda oldugu icin, icerik ne olursa olsun domain'in etkisi buyuktur.
2. **Verbosity Bias:** Uzun icerik ornekleri daha yuksek skor alma egilimindedir.
3. **Anchoring Effect:** Default skor 50 oldugu icin, LLM'ler skorlarini 50 etrafinda yogunlastirma egilimi gosterir.

---

## 1.3 Staleness Detection (Bayatlik Tespiti)

### 1.3.1 Teknoloji Degisim Hizi Modeli

LocoDex, bilginin "bayatligini" konu turune gore 4 kategoride degerlendirir (`real_deep_research.py`, L80-86):

| Kategori | Degisim Hizi | Half-Life | Lambda (lambda) | Ornek |
|----------|-------------|-----------|--------|-------|
| Fast | 6 ay | ~4.3 ay | 1.60/yil | AI modelleri, mobil islemciler |
| Medium | 2 yil | ~1.4 yil | 0.50/yil | Web framework'leri, bulut servisleri |
| Slow | 5 yil | ~3.5 yil | 0.20/yil | Veritabanlari, networking, matematik |
| Very Slow | 10 yil | ~6.9 yil | 0.10/yil | Programlama dilleri, isletim sistemi cekirdekleri |

### 1.3.2 Exponential Decay Modeli: Turetme

Bilginin zamanla "tazeligi" radyoaktif bozunma modeline benzetilerek modellenir:

**Temel varsayim:** Bir bilgi parcasinin tazeligi, yayinlanma tarihinden itibaren ustel olarak azalir.

**Turetme:**

Tazelik fonksiyonunu F(t) olarak tanimlayalim. Burada t = bilginin yasi (yil cinsinden).

Baslangic kosulu:
```
F(0) = 1    (yeni yayin = tam taze)
```

Sinir kosulu:
```
F(infinity) -> 0    (cok eski bilgi = bayat)
```

Basit bir diferansiyel denklem:
```
dF/dt = -lambda * F(t)
```

Bu denklem "bozunma hizi, mevcut tazelikle orantilidir" der. Cozelim:

```
dF/F = -lambda * dt
ln(F) = -lambda * t + C
F(t) = A * e^(-lambda * t)
```

F(0) = 1 baslangic kosulundan A = 1:

```
F(t) = e^(-lambda * t)
```

**lambda parametresinin anlami:**

lambda = ln(2) / t_half

Burada t_half = tazeliğin yariya dustugu sure.

| Kategori | t_half | lambda |
|----------|--------|--------|
| Fast (AI) | 6 ay = 0.5 yil | ln(2)/0.5 = 1.386/yil |
| Medium | 2 yil | ln(2)/2 = 0.347/yil |
| Slow | 5 yil | ln(2)/5 = 0.139/yil |
| Very Slow | 10 yil | ln(2)/10 = 0.069/yil |

### 1.3.3 Somut Sayisal Ornek

Soru: "GPT-4 performansi" konusunda 2022 tarihli bir makale ne kadar taze?

```
Konu: AI (Fast kategorisi)
lambda = 1.386 / yil
t = 2026 - 2022 = 4 yil

F(4) = e^(-1.386 * 4)
     = e^(-5.544)
     = 0.00391
     = %0.39 taze
```

Bu bilgi pratikte kullanisiz -- %0.4 tazelik. Mantikli, cunku 2022'de GPT-4 henuz yayinlanmamisti bile.

Simdi ayni 2022 tarihli makale "TCP/IP protokolu" konusunda olsun:

```
Konu: Networking (Slow kategorisi)
lambda = 0.139 / yil
t = 4 yil

F(4) = e^(-0.139 * 4)
     = e^(-0.556)
     = 0.573
     = %57.3 taze
```

Makul -- TCP/IP 4 yilda cok degismez, ama kucuk guncellemeler olur.

### 1.3.4 Kodda Nasil Uygulaniyor?

**Kritik tespit:** LocoDex'te bu exponential decay formulu EXPLICIT olarak kodda YOK. Bunun yerine, LLM'e prompt uzerinden staleness degerlendirmesi yaptiriliyor:

```python
# real_deep_research.py, L80-86
"""
* Hizli degisen teknolojiler (AI modelleri, mobil islemciler, sosyal medya): 6 ay oncesi = ESKI
* Orta hizda degisen teknolojiler (web frameworkleri, bulut servisleri): 2 yil oncesi = ESKI
* Yavas degisen teknolojiler (veritabanlari, networking, matematik): 5 yil oncesi = HALA GECERLI
* Cok yavas degisen teknolojiler (programlama dilleri, isletim sistemi cekirdekleri): 10 yil oncesi = HALA GECERLI
"""
```

Yani LLM bu kurallarla "egitilir" (prompt-based) ve kendi kararini verir. Bu, matematiksel formulun bir "dogal dil yaklasimidir" -- LLM exponential decay'i implicit olarak uygular.

**Alternatif: Explicit Formul Uygulama**

Eger formulu acikca kodlamak istersek:

```python
import math
from datetime import datetime

DECAY_RATES = {
    'fast': math.log(2) / 0.5,      # AI, mobil -- 1.386/yil
    'medium': math.log(2) / 2.0,     # Web framework -- 0.347/yil
    'slow': math.log(2) / 5.0,       # DB, network -- 0.139/yil
    'very_slow': math.log(2) / 10.0  # PL, OS -- 0.069/yil
}

def freshness_score(publish_year, topic_category, current_year=2026):
    t = current_year - publish_year
    lam = DECAY_RATES.get(topic_category, DECAY_RATES['medium'])
    return math.exp(-lam * t)

# Ornekler:
print(freshness_score(2025, 'fast'))       # 0.25  (1 yil onceki AI bilgisi)
print(freshness_score(2024, 'fast'))       # 0.063 (2 yil onceki AI bilgisi)
print(freshness_score(2024, 'slow'))       # 0.757 (2 yil onceki DB bilgisi)
print(freshness_score(2020, 'very_slow'))  # 0.660 (6 yil onceki PL bilgisi)
```

---

## 1.4 Tarafsizlik Analizi (Bias Detection)

### 1.4.1 Teorik Temel

Medya onyargisi (media bias) tespit etmek, NLP'nin en zor problemlerinden biridir. Temel onyargi turleri:

1. **Selection Bias (Secim Onyargisi):** Hangi konularin raporlanacaginin secimi
2. **Coverage Bias (Kapsam Onyargisi):** Bir konuya ne kadar yer verildigi
3. **Statement Bias (Ifade Onyargisi):** Olaylarin nasil tarif edildigi
4. **Framing Bias (Cerceleme Onyargisi):** Olaylarin hangi cerce icinde sunuldugu

LocoDex'in bias detection yaklasimi prompt-based'dir (`real_deep_research.py`, L88-93):

```python
"""
3. Kaynak Kalitesi ve Tarafsizlik:
   - Icerik objektifligi vs subjektifligi
   - Spam/clickbait belirtileri
   - Siyasi/ideolojik onyargi kontrol et
   - Birden fazla bakis acisi sunuyor mu?
   - Kanit ve referans kalitesi
"""
```

**LLM'in bias detection siniri:**

LLM'lerin kendileri de bias tasir. Bir LLM'e "bu kaynak tarafsiz mi?" diye sormak, bir mirror'a "ben guzel miyim?" diye sormak gibidir. LLM'in kendi egitim verisindeki bias'lar, degerlendirmesini etkiler.

Arastirmalar gosteriyor ki (Gallegos et al., 2024, "Bias and Fairness in Large Language Models"):
- LLM'ler siyasi bias'ta orta-sol'a meyillidir
- Batili kaynaklari sistematik olarak daha guvenilir bulurlar
- Ingilizce olmayan kaynaklara karsi implicit bias vardir

### 1.4.2 O(n) Analizi

Bias detection tamamen LLM-based oldugu icin:
```
Zaman: O(N * T_llm)  -- her kaynak icin 1 LLM cagrisi
Bellek: O(1) ek bellek -- prompt/response buffer'i disinda
```

---

## 1.5 Celiskili Bilgi Tespiti (Cross-Source Validation)

### 1.5.1 Algoritma

`detect_conflicting_information()` fonksiyonu (`real_deep_research.py`, L152-190):

1. En az 2 kaynak gerektir
2. Ilk 5 kaynagi sec (O(1) -- sabit sayi)
3. Tum kaynaklari tek bir prompt'a birlestir
4. LLM'den celiskili bilgileri tespit etmesini iste

**Matematiksel karmasiklik:**

N kaynak arasindaki tum ikili karsilastirma sayisi:
```
C(N, 2) = N! / (2! * (N-2)!) = N*(N-1)/2
```

5 kaynak icin: C(5,2) = 10 cift karsilastirma.

Ancak LocoDex bunu explicit cift karsilastirma olarak YAPMIYOR. Bunun yerine tum 5 kaynagi tek prompt'ta gonderip LLM'in tum celiskileri bulmasini istiyor. Bu O(1) LLM cagrisi (ama uzun bir prompt).

**Trade-off analizi:**

| Yontem | LLM Cagrisi | Prompt Uzunlugu | Precision | Recall |
|--------|-------------|-----------------|-----------|--------|
| Pairwise (her cift icin) | C(N,2) = 10 | Kisa | Yuksek | Yuksek |
| All-at-once (tek prompt) | 1 | Uzun | Orta | Dusuk |
| Hierarchical (3'lu gruplar) | C(N,3) + merge | Orta | Orta | Orta |

LocoDex "all-at-once" yontemini seciyor. Neden:
- Maliyet: 1 LLM cagrisi vs 10
- LLM context window: 5 kaynak * ~500 karakter = ~2500 token -- cogu modelin context'ine sigar
- Dezavantaj: LLM uzun prompt'larda ince celiskileri kacirabilir (lost-in-the-middle problemi)

---

# KONU 2: Dil Algilama Sistemi (Language Detection)

## 2.1 Karakter-Tabanli Algilama: Unicode Range Analizi

### 2.1.1 Teorik Temel

Her dilin kendine ozgu karakterleri vardir. Unicode standardinda bu karakterler belirli code point'lere atanmistir. Bir metnin dilini, icerdigi karakterlerin Unicode bloklarina bakarak tahmin etmek mumkundur.

**Unicode bloklari ve dil iliskisi:**

| Dil | Karakterler | Unicode Range | Unicode Block |
|-----|------------|---------------|---------------|
| Turkce | c, g, i (noktasiz), o, s, u | U+00C7, U+011E, U+0131, U+00D6, U+015E, U+00DC | Latin Extended-A + Latin-1 Supplement |
| Fransizca | e (acute), e (grave), e (circumflex) | U+00E9, U+00E8, U+00EA | Latin-1 Supplement |
| Almanca | a (dieresis), o (dieresis), u (dieresis), eszett | U+00E4, U+00F6, U+00FC, U+00DF | Latin-1 Supplement |

**LocoDex'in implementasyonu** (`real_deep_research.py`, L504-540):

```python
def detect_language(self, text):
    """Metindeki dili algilar"""
    # Turkce karakterler
    turkish_chars = ['c', 'g', 'i', 's', 'u', 'o', 'C', 'G', 'I', 'S', 'U', 'O']
    turkish_words = ['ve', 'ile', 'bir', 'bu', 'su', 'o', 'nedir', 'nasil', 'ne', 'hangi', 'en', 'iyi', 'guncel']

    # Fransizca karakterler ve kelimeler
    french_chars = ['e', 'e', 'e', 'e', 'a', 'a', 'a', 'c', 'u', 'u', 'u', 'o', 'o', 'i', 'i', 'y']
    french_words = ['le', 'la', 'les', 'un', 'une', 'de', 'du', 'des', 'et', 'ou', 'est', 'ce', 'que', 'qui', 'comment', 'quel', 'quelle']

    # Almanca karakterler ve kelimeler
    german_chars = ['a', 'o', 'u', 'ss', 'A', 'O', 'U']
    german_words = ['der', 'die', 'das', 'und', 'oder', 'ist', 'was', 'wie', 'welche', 'beste', 'aktuelle']
```

### 2.1.2 Bug Tespiti: Cedilla Problemi

**Kritik sorun:** Turkce `c` (c-cedilla, U+00E7) ve Fransizca `c` (c-cedilla, U+00E7) AYNI karakter!

```python
# Bu kontrol sirali:
if any(char in text for char in turkish_chars):  # Burada 'c' kontrol ediliyor
    return 'tr'
elif any(char in text for char in french_chars):  # Buraya hic ulasilmiyor 'c' icin
    return 'fr'
```

Ornek: "La facon dont le systeme fonctionne" (Fransizca cumlesi)
- `c` icinde `c` (cedilla) var
- Sistem bunu TURKCE olarak siniflandirir -- HATALI

Bu bir **priority bias** bug'idir. Cozum: karakter kontrolunden once dile ozgu karakter kümelerini ayirmak:

```python
# Turkce'ye ozel (Fransizca'da OLMAYAN): g, i (noktasiz), s
TURKISH_UNIQUE = set('gisGIS')  # U+011E, U+011F, U+0131, U+015E, U+015F, U+0130

# Fransizca'ya ozel (Turkce'de OLMAYAN): e, e, e, y
FRENCH_UNIQUE = set('eeey')

# Almanca'ya ozel: ss (eszett)
GERMAN_UNIQUE = set('ss')
```

### 2.1.3 Smart Multilingual'deki Farkli Yaklasim

`smart_multilingual_research.py` (L177-211) farkli bir strateji izler:

```python
async def detect_language(self, text):
    # Basit Turkce karakter kontrolu
    turkish_chars = re.search(r'[cgiosuCGIOSU]', text)
    turkish_words = ['nedir', 'nasil', 'ne', 'hangi', 'kim', 'nerede', 'nicin', 'neden', 'hakkinda']

    has_turkish = turkish_chars is not None or any(word in text.lower() for word in turkish_words)

    if has_turkish:
        self.query_language = "tr"
        return "turkish"
    else:
        self.query_language = "en"
        return "english"
```

Bu versiyon SADECE Turkce/Ingilizce ayirimi yapar -- Fransizca ve Almanca desteği yok. Basit ama sinirli.

### 2.1.4 Regex-Based Detection Performansi

`smart_multilingual_research.py`'de regex kullaniliyor:

```python
turkish_chars = re.search(r'[cgiosuCGIOSU]', text)
```

**Performans analizi:**

Regex `re.search()` metni soldan saga tarar ve ilk eslesmede durur:
```
En iyi durum: O(1) -- ilk karakter Turkce
En kotu durum: O(|text|) -- Turkce karakter yok, tum metin taranir
Ortalama: O(|text|/2) -- Turkce karakter ortada bir yerde
```

`any(char in text for char in turkish_chars)` ile karsilastirma:
```
len(turkish_chars) = 12 karakter
Her biri icin O(|text|) tarama
Toplam: O(12 * |text|)
```

Regex versiyonu ~12x daha hizli (karakter sinifi `[...]` tek geciste kontrol eder).

Pratik fark: 1000 karakterlik metin icin ~12us vs ~144us. Ihmal edilebilir, ama API call basina binlerce metin islenecekse fark birikir.

## 2.2 Kelime-Tabanli Algilama: Stop Word Frequency Analizi

### 2.2.1 Teorik Temel

Stop words (durma kelimeleri), bir dilde en sik kullanilan ama anlamsal icerik tasimiyan kelimelerdir. Her dilin stop word dagılımı benzersiz oldugu icin, bir metindeki stop word frekansini sayarak dil tespiti yapilabilir.

**Zipf Yasasi ile iliski:**

George Kingsley Zipf'in 1935'te gozlemledigi yasa:

```
f(r) = C / r^alpha
```

Burada:
- f(r) = r'inci en sik kelimenin frekansı
- C = normalizasyon sabiti
- r = sira (rank)
- alpha ~= 1 (cogu dogal dil icin)

Stop word'ler Zipf dagiliminin **basi**nda yer alir (en yuksek frekansli kelimeler). Bu yuzden kisa metinlerde bile bulunma olasılıkları yuksektir.

### 2.2.2 LocoDex'in Scoring Mekanizmasi

```python
# Kelime kontrolu
turkish_score = sum(1 for word in turkish_words if word in text_lower)
french_score = sum(1 for word in french_words if word in text_lower)
german_score = sum(1 for word in german_words if word in text_lower)

if turkish_score > 0:
    return 'tr'
elif french_score > 0:
    return 'fr'
elif german_score > 0:
    return 'de'
```

**Bu basit additive scoring'in formalizasyonu:**

```
Score(dil_k) = SUM_{w in W_k} I(w in text)
```

Burada:
- W_k = dil k icin stop word listesi
- I(.) = indicator fonksiyonu (1 eger kelime metinde varsa, 0 degilse)

**Sorun: Bu TF-IDF DEGIL!**

Basit sum yerine TF-IDF (Term Frequency - Inverse Document Frequency) kullanilsaydi:

```
TF(w, text) = count(w, text) / |text|
IDF(w) = log(N / df(w))
TF-IDF(w, text) = TF(w, text) * IDF(w)
```

Burada:
- count(w, text) = kelimenin metinde kac kez gectiği
- |text| = metindeki toplam kelime sayisi
- N = toplam dokuman sayisi
- df(w) = kelimenin gectigi dokuman sayisi

TF-IDF, "ve" gibi her dilde gecen kelimelere dusuk agirlik verirken, "nedir" gibi Turkce'ye ozgu kelimelere yuksek agirlik verir.

**LocoDex neden basit sum kullanir?**
- Stop word listesi zaten dile ozgu secilmis
- Tek bir metin (arama sorgusu) uzerinde calisiyor, dokuman koleksiyonu yok
- Arama sorgulari kisa (5-15 kelime) -- TF-IDF icin yeterli istatistik yok

### 2.2.3 Somut Sayisal Ornek

Metin: "Turkiye'de yapay zeka nedir ve nasil kullanilir"

Turkce stop word'ler: ['ve', 'ile', 'bir', 'bu', 'su', 'o', 'nedir', 'nasil', 'ne', 'hangi', 'en', 'iyi', 'guncel']

Eslesmeler:
- "ve" -> BULUNDU (1)
- "nedir" -> BULUNDU (1)
- "nasil" -> BULUNDU (1)
- Digerleri -> BULUNAMADI

turkish_score = 3

Fransizca stop word'ler: ['le', 'la', 'les', 'un', 'une', 'de', 'du', 'des', 'et', 'ou', 'est', 'ce', 'que', 'qui', 'comment', 'quel', 'quelle']

Eslesmeler:
- Hicbiri bulunamadi

french_score = 0

Karar: turkish_score (3) > 0 -> dil = "tr" DOGRU

**Edge case:** "La derniere conference de AI a Istanbul"
- turkish_score = 0 (hicbir Turkce stop word yok)
- french_score: "la" BULUNDU (1), "de" BULUNDU (1) -> score = 2
- Karar: "fr" -- ama aslinda karisik bir cumledir

## 2.3 N-Gram Modeli (Mevcut Kodda YOK, Teorik Alternatif)

### 2.3.1 Teorik Temel

N-gram modeli, karakter veya kelime dizilerinin koşullu olasiligina dayanir. Bir bigram modeli icin:

```
P(c_n | c_{n-1}) = count(c_{n-1}, c_n) / count(c_{n-1})
```

Her dil icin karakteristik bigram profilleri vardir:

| Dil | En Sik Bigram'lar | Seyrek Bigram'lar |
|-----|-------------------|-------------------|
| Turkce | "la", "in", "an", "ar", "le" | "qx", "wk" |
| Ingilizce | "th", "he", "in", "er", "an" | "qx", "zp" |
| Fransizca | "es", "en", "le", "de", "re" | "wk", "qz" |
| Almanca | "en", "er", "ch", "de", "ei" | "qx", "wk" |

**Dil tanima:**

Bir metin icindeki tum bigram'lari sayip, her dil profiline olan mesafeyi olceriz:

```
Distance(text, lang) = SUM_{bigram} |freq_text(bigram) - freq_lang(bigram)|^2
```

En dusuk mesafeli dil secilir:
```
detected_lang = argmin_k Distance(text, lang_k)
```

### 2.3.2 Dogruluk vs Metin Uzunlugu

Arastirmalar gosteriyor ki (Cavnar & Trenkle, 1994):

| Metin Uzunlugu | Karakter N-gram Dogrulugu | Stop Word Dogrulugu |
|----------------|--------------------------|---------------------|
| 5 karakter | %40-50 | %20-30 |
| 20 karakter | %70-80 | %50-60 |
| 50 karakter | %90-95 | %75-85 |
| 200 karakter | %98-99 | %90-95 |

**LocoDex'in kullanim durumu:** Arama sorgulari genelde 5-30 kelime (30-200 karakter). Bu aralıkta karakter bazli + stop word hibrit yaklasimi %80-90 dogruluk verir. N-gram eklemek bunu %90-95'e cikarirdi ama implementasyon karmasikligi artar.

### 2.3.3 O(n) Analizi

Mevcut karakter + stop word yaklasimi:
```
Karakter kontrolu: O(K * |text|) burada K = karakter listesi uzunlugu (~12-16)
Kelime kontrolu: O(W * |text|) burada W = kelime listesi uzunlugu (~13-17)
Toplam: O((K + W) * |text|) = O(|text|) (sabit katsayi)
```

N-gram alternatifi:
```
Bigram cikarma: O(|text|)
Profil karsilastirma: O(V * L) burada V = vocabulary boyutu, L = dil sayisi
Toplam: O(|text| + V * L)
```

Her iki yontem de O(|text|) -- karmasiklık farkı ihmal edilebilir.

## 2.4 Cok Dilli Arama Stratejisi

### 2.4.1 LocoDex'in Yaklasimi

Turkce soru algilansdiginda, sistem hem Turkce hem Ingilizce arama yapar (`real_deep_research.py`, L563-609):

```python
# Ana dilde 3 sorgu
primary_prompt = "...{lang_names.get(detected_lang)} dilinde 3 farkli arama terimi ile arastir..."

# Ingilizce'de 2 sorgu (ana dil Ingilizce degilse)
secondary_prompt = "...bu konuyu Ingilizce olarak 2 farkli arama terimi ile arastir..."
```

**Neden cok dilli?**

Bilginin dil dagilimi asimetriktir:

```
P(bilgi | en) >> P(bilgi | tr) >> P(bilgi | de) >> P(bilgi | fr)
```

Ornek: "Transformer mimarisi" konusunda:
- Ingilizce kaynaklar: ~10,000+ sayfa
- Turkce kaynaklar: ~200-500 sayfa
- Almanca kaynaklar: ~100-300 sayfa

Sadece Turkce aramak, bilgi evreninin %2-5'ini tarar. Ingilizce eklemek bunu %80-90'a cikarir.

**Sorgu dagılımı:** 3 ana dil + 2 Ingilizce = 5 sorgu (toplam limit: L671)

---

# KONU 3: Icerik Kalite Degerlendirmesi

## 3.1 Content Scoring Metrikleri

### 3.1.1 Uzunluk-Bazli Kalite Tahmini

LocoDex'te icerik kalitesinin ilk filtresi uzunluga dayanir (`server.py`, L174):

```python
if len(research) > 200:
    # "Yeterli detay buldum!"
    detailed_research.append(...)
else:
    # "Bilgi az, baska acidan bakayim..."
    # Alternatif arastirma yap
```

**Neden 200 karakter?**

Shannon'in bilgi teorisi perspektifinden:

```
H(text) = -SUM_i p(x_i) * log2(p(x_i))
```

Turkce icin ortalama karakter entropisi ~4.5-5.0 bit/karakter (Ingilizce ~4.0-4.5).

200 Turkce karakter:
```
Bilgi icerigi ~= 200 * 4.7 = 940 bit ~= 117 byte
Kelime sayisi ~= 200 / 6.5 = ~30 kelime (ortalama Turkce kelime uzunlugu ~5.5 karakter + bosluk)
Cumle sayisi ~= 30 / 8 = ~3-4 cumle (ortalama cumle uzunlugu ~8 kelime)
```

3-4 cumle, bir konuyu "tanimlama" icin minimum yeterli miktar olarak kabul edilir. Dilbilimde bu "minimal coherent discourse unit" olarak tanimlanir.

**Alternatif esik degerleri:**

| Esik | Kelime | Cumle | Yeterlilik |
|------|--------|-------|------------|
| 50 karakter | ~8 | ~1 | Yetersiz -- sadece baslik |
| 100 karakter | ~15 | ~2 | Minimum tanim |
| **200 karakter** | **~30** | **~3-4** | **Temel bilgi** |
| 500 karakter | ~75 | ~8-10 | Orta detay |
| 1000 karakter | ~150 | ~15-20 | Detayli aciklama |

### 3.1.2 Derinlik ve Spesifiklik

Metin uzunlugu tek basina kaliteyi olcmez. 200 karakter "Lorem ipsum dolor sit amet..." olabilir. LocoDex bunu LLM degerlendirmesine birakir -- explicit derinlik metrigi yok.

**Teorik alternatif: Lexical Richness**

```
TTR (Type-Token Ratio) = |unique_words| / |total_words|
```

Yuksek TTR = zengin sozcuk dagarcigi = derinlik (genel olarak).

Ornek:
- Dusuk kalite: "AI iyidir. AI hizlidir. AI gucludur." -> TTR = 5/9 = 0.56
- Yuksek kalite: "Transformer mimarisi dikkat mekanizmasi kullanir ve paralel islem yapar." -> TTR = 8/9 = 0.89

## 3.2 Sayisal Veri Cikarma

### 3.2.1 Yaklasim

`extract_specific_data()` fonksiyonu (`real_deep_research.py`, L192-230) prompt-based NER (Named Entity Recognition) kullanir:

```python
extraction_prompt = f"""
'{topic}' konusu ile ilgili bu icerikten spesifik sayisal verileri cikar:
...
1. SAYISAL VERILER:
   - Tum sayilari ve birimlerini belirt (GB, TB, PB, kg, cm, $, %, yil, adet, vb.)
2. HESAPLAMALAR:
   - Matematiksel islemler varsa goster
3. KARSILASTIRMALAR:
   - Artis/azalis oranlari
"""
```

**Bu yaklasim NER'dan farkilar:**

Geleneksel NER:
```
Girdi: "GPT-4 175 milyar parametre kullanir"
Cikti: [("175 milyar", CARDINAL), ("parametre", UNIT)]
```

LLM-based extraction:
```
Girdi: Uzun metin + prompt
Cikti: "Sayisal_Veriler: 175 milyar parametre\nHesaplamalar: yok\nKarsilastirmalar: GPT-3'ten 10x buyuk"
```

**Avantaj:** LLM, baglami anlayarak "175 milyar" ile "parametre"yi iliskilendirir. Geleneksel regex bunu yapamaz.

**Dezavantaj:** LLM hallucinasyon yapabilir -- kaynakta olmayan sayilari uretebilir.

### 3.2.2 Regex Tabanli Alternatif

Eger regex ile yapilsaydi:

```python
import re

patterns = {
    'storage': r'(\d+(?:\.\d+)?)\s*(GB|TB|PB|MB|KB)',
    'percentage': r'(\d+(?:\.\d+)?)\s*%',
    'currency': r'[\$]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(million|billion|trilyon)?',
    'year': r'(19|20)\d{2}',
    'count': r'(\d+(?:,\d{3})*)\s*(adet|sunucu|kisi|kullanici)',
}

def extract_numbers(text):
    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            results[name] = matches
    return results
```

Bu O(P * |text|) zamanda calisir, burada P = pattern sayisi. LLM cagrisi yerine ~1ms'de tamamlanir.

**Trade-off:**

| Metrik | Regex | LLM-Based |
|--------|-------|-----------|
| Hiz | ~1ms | ~2-30s |
| Recall | %60-70 (bilinen pattern'lar) | %85-95 |
| Precision | %95+ (false positive dusuk) | %75-85 (hallucinasyon riski) |
| Birim iliskilendirme | Yok | Var |
| Baglam anlama | Yok | Var |

## 3.3 Hallucination Detection

### 3.3.1 Temel Kavram

Hallucinasyon (hallucination), bir LLM'in kaynak metinde OLMAYAN bilgiyi uretmesidir. Iki turu vardir:

1. **Intrinsic Hallucination:** Kaynakla celisen bilgi uretmek
2. **Extrinsic Hallucination:** Kaynaktan bagimsiz, dogrulanamayan bilgi uretmek

LocoDex'te hallucination kontrolu su sekilde yapilir:

```python
# real_deep_research.py, L762
if analysis and "hatasi" not in analysis.lower():
    research_data.append(...)
```

Bu cok basit bir kontrol -- sadece "hata" kelimesini ariyor. Gercek hallucination detection cok daha karmasiktir.

**Teorik yaklasim: Faithfulness Scoring**

```
Faithfulness(summary, source) = |facts_in_summary AND facts_in_source| / |facts_in_summary|
```

Burada:
- facts_in_summary = ozetin icerdigi iddialar kumesi
- facts_in_source = kaynak metnin icerdigi iddialar kumesi

Faithfulness = 1.0 ise ozet tamamen kaynaga dayali (hallucinasyon yok).
Faithfulness < 1.0 ise kaynak disi iddialar var.

### 3.3.2 Quality Threshold: 200 Karakter ve Shannon Entropy

**Shannon Entropy hesabi:**

Turkce alfabe (29 harf + bosluk + noktalama ~= 35 sembol):

```
H_max = log2(35) = 5.13 bit/karakter (uniform dagilim)
H_actual ~= 4.7 bit/karakter (Turkce dogal metin icin)
```

200 karakter icin:
```
Toplam bilgi = 200 * 4.7 = 940 bit = 117.5 byte
```

Karsilastirma:
- Bir Tweet (280 karakter): ~1316 bit
- Bir Wikipedia paragraf (~500 karakter): ~2350 bit
- 200 karakter: ~940 bit

940 bit, bir konuyu "minimal olarak ifade etmek" icin yeterli bilgi kapasitesi olarak degerlendirilebilir. Daha az bit iceriksel olarak anlamli bir yazi olusturmak icin yetersiz kalir.

---

# KONU 4: Prompt-Based Evaluation Architecture

## 4.1 Evaluation Prompt Tasarimi: Rubric-Based Scoring

### 4.1.1 Rubrik Yapisi

LocoDex'in degerlendirme prompt'u 5 ana kriterden olusur (`real_deep_research.py`, L68-106):

```
1. Konu Turu Analizi (Agirlik: YUKSEK)
   - Kategorizasyon: Teknoloji/Tarih/Psikoloji/Siyaset/Is_Hayati/Bilim/Genel

2. Tarih ve Teknoloji Olgunluk Analizi (Agirlik: YUKSEK)
   - Icerik tarih tespiti
   - Degisim hizi degerlendirmesi

3. Kaynak Kalitesi ve Tarafsizlik (Agirlik: ORTA)
   - Domain guvenilirligi
   - Objektiflik
   - Spam/clickbait kontrolu

4. Konu-Spesifik Kriterler (Agirlik: ORTA)
   - Alana ozgu degerlendirme

5. Konu Uygunlugu (Agirlik: DUSUK)
   - Relevance kontrolu
```

### 4.1.2 Multi-Criteria Assessment Formulu

Teorik olarak, coklu kriter degerlendirmesi soyle formalize edilir:

```
S_total = SUM_{i=1}^{n} w_i * S_i
```

Burada:
- S_total = toplam skor (0-100)
- w_i = i'inci kriterin agirligi (SUM w_i = 1)
- S_i = i'inci kriterdeki skor (0-100)
- n = kriter sayisi

**LocoDex'te agirliklar EXPLICIT degil:**

Kodda w_i degerleri tanimlanmamis. Bunun yerine LLM'e "COK ONEMLI" ve "ONEMLI" gibi dogal dil ipuclari veriliyor:

```python
"""
1. **Konu Turu Analizi (COK ONEMLI):**
2. **Tarih ve Teknoloji Olgunluk Analizi (COK ONEMLI):**
3. **Kaynak Kalitesi ve Tarafsizlik:**
4. **Konu-Spesifik Kriterler:**
5. **Konu Uygunlugu:**
"""
```

LLM bu dogal dil ipuclarindan implicit agirliklar cikarir. Bu, deterministic weighted average'den farklidir -- her LLM cagrisinda agirliklar farkli olabilir.

### 4.1.3 Explicit Weighted Scoring Alternatifi

```python
CRITERIA_WEIGHTS = {
    'topic_relevance': 0.30,      # Konu uygunlugu
    'source_authority': 0.25,     # Kaynak otoritesi
    'content_quality': 0.20,      # Icerik kalitesi
    'freshness': 0.15,            # Guncellik
    'objectivity': 0.10           # Tarafsizlik
}

def weighted_score(criteria_scores):
    """
    criteria_scores: dict, orn:
    {
        'topic_relevance': 85,
        'source_authority': 90,
        'content_quality': 70,
        'freshness': 60,
        'objectivity': 80
    }
    """
    total = sum(
        CRITERIA_WEIGHTS[criterion] * score
        for criterion, score in criteria_scores.items()
    )
    return total

# Ornek hesaplama:
scores = {
    'topic_relevance': 85,
    'source_authority': 90,
    'content_quality': 70,
    'freshness': 60,
    'objectivity': 80
}

# S = 0.30*85 + 0.25*90 + 0.20*70 + 0.15*60 + 0.10*80
# S = 25.5 + 22.5 + 14.0 + 9.0 + 8.0
# S = 79.0
```

### 4.1.4 Calibration: LLM Scoring Bias Duzeltme

LLM'ler sistematik bias'lara sahiptir:

1. **Central Tendency Bias:** Skorlari 40-60 arasinda yogunlastirma
2. **Leniency Bias:** Genel olarak yuksek skor verme egilimi
3. **Severity Bias:** Bazi modeller (ozellikle kucuk modeller) dusuk skor verme egiliminde

**Calibration yaklasimi:**

Verilen bir LLM'in raw skorlarini kalibre etmek icin z-score normalizasyonu:

```
S_calibrated = (S_raw - mu) / sigma * sigma_target + mu_target
```

Burada:
- S_raw = LLM'in urettigi ham skor
- mu = LLM'in ortalama skoru (kalibrasyon seti uzerinden)
- sigma = LLM'in standart sapmasi
- mu_target = hedef ortalama (genellikle 50)
- sigma_target = hedef standart sapma (genellikle 20)

**Ornek kalibrasyon:**

Diyelim ki Llama 3.1 8B modeli su skorlari uretiyor:
- Ortalama: mu = 62 (leniency bias -- yuksek skor verme egilimi)
- Standart sapma: sigma = 12 (dusuk -- central tendency)

Bir kaynak icin raw skor: S_raw = 75

```
S_calibrated = (75 - 62) / 12 * 20 + 50
             = 13 / 12 * 20 + 50
             = 1.083 * 20 + 50
             = 21.67 + 50
             = 71.67 ~= 72
```

Ham skor 75 iken, kalibre skor 72'ye dustü -- cunku model zaten yuksek skor verme egiliminde.

### 4.1.5 Iki Farkli Skalanin Karsilastirilmasi

LocoDex iki farkli evaluation sistemi kullaniyor:

| Ozellik | real_deep_research | smart_multilingual |
|---------|-------------------|-------------------|
| Skala | 0-100 | 1-10 |
| Prompt uzunlugu | ~800 token | ~200 token |
| Kriter sayisi | 5 | 4 |
| Cikti formati | Cokllu satirli structured | Tek satirli "Puan: X/10" |
| Filtering threshold | 30/100 (%30) | 6/10 (%60) |
| Default skor | 50 | 5 |
| Parse yontemi | Line-by-line startswith() | Regex r'(\d+)/10' |

**Kritik farki:** smart_multilingual cok daha agresif filtreler (skoru %60'in altindakileri atar) ama daha az detayli degerlendirme yapar.

**Normalizasyon:**

Iki sistemi kiyaslamak icin normalizasyon:
```
S_normalized = S / S_max

real_deep_research: 30/100 = 0.30 threshold
smart_multilingual: 6/10 = 0.60 threshold
```

smart_multilingual 2x daha secici.

---

## 4.2 evals.py: LLM-as-a-Judge (Binary Scoring)

### 4.2.1 Yapisi

`evals.py` dosyasi ucuncu bir degerlendirme yaklasimi sunar:

```python
@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=1, min=4, max=15))
def llm_as_a_judge_scoring(result: Result) -> bool:
    prompt = f"""
    Given the following question and answer, evaluate the answer against the correct answer:
    ...
    <answer>1</answer>  (dogru)
    veya
    <answer>0</answer>  (yanlis)
    """
```

Bu BINARY scoring -- 0 veya 1. Nuansli degerlendirme yok.

**Kullanim amaci:** Benchmark/evaluation icin. Bir agent'in cevabinin dogru olup olmadigini kontrol eder.

### 4.2.2 Retry Mekanizmasi

```python
@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=15)
)
```

Bekleme suresi formulu:
```
t_n = min(15, max(4, 1 * 2^n))
```

| Deneme | Bekleme (saniye) |
|--------|-----------------|
| 1 | max(4, 1*2^1) = 4 |
| 2 | max(4, 1*2^2) = 4 |
| 3 | Basarisiz -- exception firlatir |

**Model:** Together AI uzerinde Llama 3.3 70B, temperature=0.0 (deterministik).

Temperature = 0 kullanilmasi onemli: ayni girdi icin her zaman ayni cikti uretilir. Bu, binary judge icin dogru secimdir -- tutarlilik kritiktir.

---

# GENEL DEGERLEDIRME VE ONERILER

## Guclu Yanlar

1. **Pragmatik tasarim:** Lokal LLM sinirlamalari icinde makul trade-off'lar yapilmis
2. **Hibrit yaklasim:** Domain whitelist + LLM evaluation + content filtering
3. **Cok dilli destek:** Turkce sorular otomatik olarak Ingilizce ile de aranir
4. **Defensive programming:** Default skorlar, fallback mekanizmalari, hata yakalama

## Zayif Yanlar ve Iyilestirme Onerileri

1. **Bug:** Cedilla problemi dil algilamada (`detect_language` sirali kontrol)
   - Cozum: Dile ozgu benzersiz karakter kumeleri tanimla

2. **Skor parse bug'i:** `filter(str.isdigit)` ile "85/100" -> 85100
   - Cozum: `re.search(r'(\d+)', text)` kullan

3. **Statik domain listesi:** Yeni domainler eklenemez
   - Cozum: Kullanici konfigurasyonlu domain whitelist

4. **Explicit agirliklar yok:** LLM'in implicit agirlandirmasi deterministik degil
   - Cozum: Weighted scoring fonksiyonu ekle

5. **Kalibrasyon yok:** LLM bias'i duzeltilmeden ham skorlar kullaniliyor
   - Cozum: Basit z-score kalibrasyonu

6. **Iki farkli skala:** 0-100 vs 1-10 karistirici
   - Cozum: Tek bir skala standardize et

---

**Kaynak Dosyalar:**
- `/Users/apple/Desktop/dosyalar/LocoDex-deep-search/deep_research_service/real_deep_research.py`
- `/Users/apple/Desktop/dosyalar/LocoDex-deep-search/deep_research_service/smart_multilingual_research.py`
- `/Users/apple/Desktop/dosyalar/LocoDex-deep-search/deep_research_service/src/libs/utils/evals.py`
- `/Users/apple/Desktop/dosyalar/LocoDex-deep-search/deep_research_service/server.py`
