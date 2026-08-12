# KONU 2: Rapor Sentezi (Report Generation)

## 2.1 Multi-Source Synthesis: Birden Fazla Kaynaktan Bilgi Birlestirme

### Problem Tanimi

LocoDex, S adet web kaynagindan toplanan bilgileri tek bir tutarli rapora donusturur. Bu, bilgi fuzyonu (information fusion) problemidir. Kaynaklarin birbirleriyle tutarli olmasi garanti degildir: farkli kaynaklar ayni konu hakkinda celisebilir.

Koddaki somut karsilik: `research_topic()` fonksiyonundaki `combined_research` olusturma (real_deep_research.py L804-813) ve `generate_comprehensive_report()` (smart_multilingual.py L624-716).

### 2.1.1 Dempster-Shafer Evidence Theory

Dempster-Shafer (DS) teorisi, farkli kaynaklardan gelen "kanit"lari birlestirmek icin kullanilir. Bayesian olasiligin bir genellemesidir: "bilmiyorum" durumunu modelleyebilir.

**Temel Kavramlar:**

Theta = {h_1, h_2, ..., h_n} bir "frame of discernment" (karar cercevesi) olsun. Ornegin:
- h_1 = "AI 2025'te 1T$ pazar buyuklugune ulasacak"
- h_2 = "AI 2025'te 1T$ pazar buyuklugune ULASMAYACAK"

Bir mass function m: 2^Theta -> [0,1] su kosullari saglar:
```
m(empty_set) = 0
sum_{A subset of Theta} m(A) = 1
```

m(A), A hipotez kumesine dogrudan atanan "inanc miktari"dir.

**Belief ve Plausibility:**

```
Bel(A) = sum_{B subset of A} m(B)     -- A'nin kesin dogrulugu icin alt sinir
Pl(A) = sum_{B ∩ A != empty} m(B)     -- A'nin mumkun dogrulugu icin ust sinir

Her zaman: Bel(A) <= P(A) <= Pl(A)
```

**Dempster's Rule of Combination:**

Iki bagimsiz kaynak m_1 ve m_2'yi birlestirmek icin:

```
(m_1 ⊕ m_2)(A) = (1/K) * sum_{B ∩ C = A} m_1(B) * m_2(C)

burada K = 1 - sum_{B ∩ C = empty} m_1(B) * m_2(C)

K normallestime sabitidir. sum_{B ∩ C = empty} terimi "celiski miktari"dir.
```

**Sayisal Ornek:**

Theta = {h_1: "Python en populer dil", h_2: "JavaScript en populer dil"}

Kaynak 1 (Stack Overflow anketi, guvenilirlik 0.8):
```
m_1({h_1}) = 0.6
m_1({h_2}) = 0.2
m_1(Theta) = 0.2    (belirsiz)
```

Kaynak 2 (GitHub istatistikleri, guvenilirlik 0.7):
```
m_2({h_1}) = 0.3
m_2({h_2}) = 0.5
m_2(Theta) = 0.2
```

Birlestirme:

Once celiski hesabi:
```
K_conflict = m_1({h_1})*m_2({h_2}) + m_1({h_2})*m_2({h_1})
           = 0.6*0.5 + 0.2*0.3
           = 0.30 + 0.06 = 0.36

K = 1 - 0.36 = 0.64
```

Birlesik mass:
```
m_combined({h_1}) = [m_1({h_1})*m_2({h_1}) + m_1({h_1})*m_2(Theta) + m_1(Theta)*m_2({h_1})] / K
                  = [0.6*0.3 + 0.6*0.2 + 0.2*0.3] / 0.64
                  = [0.18 + 0.12 + 0.06] / 0.64
                  = 0.36 / 0.64
                  = 0.5625

m_combined({h_2}) = [m_1({h_2})*m_2({h_2}) + m_1({h_2})*m_2(Theta) + m_1(Theta)*m_2({h_2})] / K
                  = [0.2*0.5 + 0.2*0.2 + 0.2*0.5] / 0.64
                  = [0.10 + 0.04 + 0.10] / 0.64
                  = 0.24 / 0.64
                  = 0.375

m_combined(Theta) = [m_1(Theta)*m_2(Theta)] / K
                  = 0.2*0.2 / 0.64
                  = 0.04 / 0.64
                  = 0.0625
```

Dogrulama: 0.5625 + 0.375 + 0.0625 = 1.0 (OK).

Sonuc: h_1 (Python) %56 oraninda desteklenir, h_2 (JavaScript) %38, belirsizlik %6.

**LocoDex'te uygulanma bicimi:**

Kodda DS teorisi explicit olarak uygulanmiyor. Bunun yerine LLM-as-a-judge yaklasimi kullanilir:
1. Her kaynaga guvenilirlik skoru verilir (0-100 veya 1-10)
2. Kaynaklar guvenilirlik sirasina gore siralanir (L785)
3. Dusuk guvenilirlik filtrelenir (L788: score >= 30)
4. LLM'e "bu kaynaklari birlestir" denir

Bu, DS'nin YAKLASIK bir uygulamasidir: guvenilirlik skorlari mass function gibi davranir, LLM ise Dempster'in birlestirme kuralinin yerine gecer.

### 2.1.2 Conflicting Source Resolution

Celiskili kaynaklarin cozumu icin iki temel strateji vardir:

**1. Agirlikli Ortalama (Weighted Average):**

Sayisal degerler icin:

```
value_final = sum_{i=1}^{S} w_i * value_i / sum_{i=1}^{S} w_i

burada w_i = reliability_score_i
```

**Sayisal ornek:** "AI pazar buyuklugu" icin 3 kaynak:
- Kaynak 1 (Reuters, guvenilirlik 85): 900 milyar $
- Kaynak 2 (blog, guvenilirlik 40): 1.5 trilyon $
- Kaynak 3 (McKinsey, guvenilirlik 75): 1.1 trilyon $

```
value = (85*900 + 40*1500 + 75*1100) / (85 + 40 + 75)
      = (76500 + 60000 + 82500) / 200
      = 219000 / 200
      = 1095 milyar $
```

Eger agirliksiz olsaydi: (900+1500+1100)/3 = 1167. Agirlikli sonuc daha dusuktir cunku dusuk guvenilirlikli kaynagin etkisi azaltilmistir.

**2. Majority Voting:**

Kalitatif ifadeler icin:

```
decision = argmax_h count(kaynaklar h lehine oy verenler)
```

Agirlikli majority voting:
```
decision = argmax_h sum_{i: kaynak_i h der} w_i
```

**LocoDex'teki uygulama:**

`detect_conflicting_information()` (real_deep_research.py L152-190) en fazla 5 kaynagi birbiriyle karsilastirir ve LLM'e "celiski var mi?" diye sorar. Bu, ne weighted average ne de majority voting'dir -- LLM'e birakilan bir serbest-form degerlendirmedir.

```python
# L158-159: Ilk 5 kaynak
sources_to_compare = research_data[:5]
```

**Sinirlamalar:**
- Sadece ilk 5 kaynak karsilastirilir (sonuc uzay kisitlamasi)
- Celiskiyi tespit etmek LLM'e birakilir (tutarsiz olabilir)
- Sayisal degerlerdeki celiski otomatik cozulmuyor (ornegin "900 milyar vs 1.5 trilyon")
- Kaynaklarin guvenilirlik skorlari celiski cozumunde KULLANILMIYOR (sadece siralamada)

---

## 2.2 Markdown Rapor Yapisi

### Koddaki Yapi

LocoDex raporlari su sirayla olusturulur:

**real_deep_research.py rapor yapisi (L947-964):**

```
# Derin Arastirma Raporu: {topic}

**Arastirma Tarihi:** ...
**Arastirma Turu:** ...
**Kullanilan Model:** ...
**Toplam Kaynak:** ...
**Arama Sorgulari:** ...

---

[LLM tarafindan uretilen icerik]

## Kaynaklar
- [kaynak1](url1)
- [kaynak2](url2)
```

**smart_multilingual_research.py rapor yapisi (L688-707):**

```
# Akilli Cok Dilli Arastirma: {topic}

**Arastirma Tarihi:** ...
**Arastirma Turu:** ...
**Kullanilan Model:** ... (kaynak)
**Toplam Kaynak:** ...
**Arastirma Dili:** ...
**Arama Motorlari:** ...

---

[LLM tarafindan uretilen icerik]

## Kaynaklar
- [kaynak](url) - Guvenilirlik: X/10 (motor)
```

### Akademik Rapor Yapisi ile Karsilastirma

Ideal bir arastirma raporu:

```
Abstract (Ozet)
  -> Rapor ne hakkinda, ana bulgular

Introduction (Giris)
  -> Konunun tanitimi, arastirma sorusu, motivasyon

Literature Review (Literatur Taramasi)
  -> Mevcut bilgi birikimi, onceki calismallar

Methodology (Yontem)
  -> Nasil arastirildi, hangi kaynaklar, neden bu kaynaklar

Findings / Analysis (Bulgular / Analiz)
  -> Ana sonuclar, veri analizi, karsilastirmalar

Discussion (Tartisma)
  -> Bulguların yorumu, sinirlama, oneriler

Conclusion (Sonuc)
  -> Ozet, gelecek ongoru

References (Kaynaklar)
  -> Tum kaynak listesi
```

LocoDex prompt'larinda (real_deep_research.py L864-875) bu yapiyi talep eden ifadeler var:
```
"Net giris bolumu"
"Ana bulgular ve onemli gelismeler"
"Detayli analiz ve degerlendirmeler"
"Sonuc ve gelecek ongoruleri"
```

Ancak bu yapi LLM'in takdirine birakilmistir -- garanti degildir.

---

## 2.3 Citation Management

### Referans Takip Sistemi

LocoDex'te iki farkli referans formati kullanilir:

**Format 1: URL listesi (real_deep_research.py)**

```python
source_list = "\n".join([
    f"- [{item['source']}]({item['url']})"
    for item in research_data
])
```

Bu, Markdown linkleri kullanir: `[baslik](url)` formati.

**Format 2: Guvenilirlik skorlu liste (smart_multilingual.py)**

```python
source_list = "\n".join([
    f"- [{item['source']}]({item['url']}) - Guvenilirlik: {item['reliability_score']}/10 ({item['search_source']})"
    for item in research_data
])
```

### Inline Citation: [n] Formati

Akademik makalelerde kullanilan [n] formati (ornegin "[1] Gore 2024'te...") LocoDex'te native olarak desteklenmemektedir. LLM prompt'unda su yonerge var:

```
"MUTLAKA rapor sonunda 'Kaynaklar' bolumu ekle ve tum kaynak URL'lerini listele"
```

Ancak metin icinde [1], [2] gibi inline referanslar LLM'in inisiyatifine birakilmistir. Bu, referans butunlugunu garanti etmez.

**Ideal citation sistemi icin gerekli:**

1. Her kaynaga benzersiz bir ID ver: kaynak_1, kaynak_2, ...
2. LLM'e "metin icinde [kaynak_ID] kullan" yonergesini ver
3. Post-processing ile [kaynak_ID] -> [n] donusumu yap
4. Rapor sonundaki listeyle cross-reference kontrol et

### Citation Integrity Kontrolu

Bir raporun citation integrity'si su metrikle olculebilir:

```
Citation_Coverage = |referans_verilen_kaynaklar| / |kullanilan_kaynaklar|
```

Ideal: Citation_Coverage = 1.0 (her kullanilan kaynak referans verilmis).

```
Phantom_Citation_Rate = |referans_verilen_ama_kullanilmayan| / |tum_referanslar|
```

Ideal: Phantom_Citation_Rate = 0.0 (hayalet referans yok).

LocoDex'te her iki metrik de KONTROL EDILMIYOR. LLM, kaynaklar bolumunde listelenmeyen bilgilere referans verebilir (hallucination) veya kaynaklar bolumundeki bir URL'ye hic atif yapmayabilir.

---

## 2.4 Prompt Chaining: Arastirma -> Analiz -> Sentez -> Final Rapor

### Prompt Zinciri Tasarimi

LocoDex pipeline'i birden fazla LLM cagri zinciri kullanir. Her cagri, onceki cagrinin ciktisini girdi olarak alir.

**Zincir 1: RealDeepResearcher (basit)**

```
search_strategy_prompt -----> arama_sorgulari
                                    |
                                    v
              [web search + content extraction]
                                    |
                                    v
reliability_prompt -----> guvenilirlik_skoru (her kaynak icin)
                                    |
                                    v
analysis_prompt -----> kaynak_ozeti (her kaynak icin)
                                    |
                                    v
extraction_prompt -----> sayisal_veriler (her kaynak icin)
                                    |
                                    v
conflict_prompt -----> celiski_analizi
                                    |
                                    v
final_prompt -----> RAPOR
```

**Zincir 2: DeepResearcher (sofistike)**

```
planning_prompt -----> arastirma_plani (free text)
                            |
                            v
plan_parsing_prompt -----> queries (JSON: ResearchPlan)
                            |
                            v
            [web search + content fetch]
                            |
                            v
evaluation_prompt -----> "daha arastirma lazim mi?" (free text)
                            |
                            v
evaluation_parsing_prompt -----> ek_queries (JSON: ResearchPlan)
                            |
                            v
            [ek web search -- iterative loop]
                            |
                            v
filter_prompt -----> "hangi kaynaklar onemli?" (free text)
                            |
                            v
filter_parsing_prompt -----> kaynak_numaralari (JSON: SourceList)
                            |
                            v
answer_prompt -----> FINAL RAPOR
```

### Prompt Zinciri Karmasikligi

Zincir uzunlugu L ve her adimda hata olasiligi e ise, zincirin dogru cikti verme olasiligi:

```
P_chain_correct = (1-e)^L
```

**RealDeepResearcher:** L=6 (kaynak sayisi S ile carpildiginda etkili L ~ 6+3S)
**DeepResearcher:** L=7+2K (K=iterasyon sayisi)

e=0.05 (her prompt icin %5 hata):
```
RealDeep (S=20): P = 0.95^(6+60) = 0.95^66 = 0.033 -- %3.3 HATASIZ cikti!
DeepResearch (K=4): P = 0.95^15 = 0.463 -- %46 hatasiz cikti
```

Bu, prompt chaining'in en buyuk sinirlamasidir: zincir uzadikca hatasiz cikti olasiligi ustel olarak duser. RealDeepResearcher'in her kaynak icin ayri LLM cagri yapmasi (3 cagri * 20 kaynak = 60 ek halka) zincirii cok uzatir.

### Zincir Optimizasyon Stratejileri

1. **Batch processing:** 20 kaynagi tek seferde degerlendirmek (1 cagri vs 20 cagri). Hata zinciri 66'dan 7'ye duser.

2. **Structured output:** Pydantic JSON schema zorlamasi (together_open_deep_research.py L252):
```python
response_format={"type": "json_object", "schema": ResearchPlan.model_json_schema()}
```
Bu, LLM ciktisini format olarak kisitlar ve parsing hatasini azaltir.

3. **Chain-of-thought:** `thinking_process_prompt` (real_deep_research.py L884) ile LLM'e dusunme sureci eklenir, ancak bu rapordan cikartilir.

---

## 2.5 Token Budget Yonetimi

### Koddaki max_tokens Degerleri

Projedeki tum max_tokens kullanimlarini kaynaktan cikaralim:

| Kullanim Yeri | max_tokens | Amac | Dosya:Satir |
|--------------|------------|------|-------------|
| Guvenilirlik degerlendirmesi | 200 | Kisa skor + sebep | real_deep_research.py:119 |
| Celiski tespiti | 500 | Kaynak karsilastirmasi | real_deep_research.py:184 |
| Veri cikarma | 300 | Sayisal veri listesi | real_deep_research.py:224 |
| Kaynak analizi | 500 | Ozet | real_deep_research.py:757 |
| Fallback rapor | 2000 | Model bilgisiyle rapor | real_deep_research.py:832 |
| Final rapor | 4000 | Tam rapor | real_deep_research.py:889 |
| Kaynak guvenilirlik | 200 | Skor | smart_multilingual.py:455 |
| Kaynak analizi | 800 | Detayli ozet | smart_multilingual.py:585 |
| Gap analizi | 500 | Eksik alan tespiti | smart_multilingual.py:506 |
| Final rapor | 5000 | Tam rapor | smart_multilingual.py:685 |
| LLM default | 3000 | Genel cagri | real_deep_research.py:232 |
| LocalDeepResearcher | 2000 | Genel cagri | server.py:55 |
| Together AI answer | 4096 | Final rapor | together_open_deep_research.py:37 |
| Together AI general | 4096 | Filter/eval | together_open_deep_research.py:460 |

### Token Budget Stratejisi

Token budget'i 3 faktore baglidir:

**1. Maliyet:**

```
Maliyet = (input_tokens + output_tokens) * fiyat_per_token

Ornegin (Llama 3.1 70B on Together AI):
  Input: $0.88 / 1M token
  Output: $0.88 / 1M token

20 kaynak icin tipik maliyet:
  Input: ~50000 token * $0.88/1M = $0.044
  Output: ~27000 token * $0.88/1M = $0.024
  TOPLAM: ~$0.07 / arastirma
```

Lokal model kullanildiginda (Ollama/LM Studio) maliyet sifirdir ama sure cok daha uzundur.

**2. Kalite vs Uzunluk Trade-off:**

max_tokens arttikca:
- Daha detayli ve kapsamli ciktilar
- Ancak LLM "bos doldurma" egilimi artar
- Hallucination riski artar (daha cok uretim = daha cok hata sansi)

Optimal nokta: kullanim amacina bagli. Guvenilirlik skoru icin 200 token yeterli (kisa ve net). Final rapor icin 4000-5000 minimum (kapsamli olm zorunda).

**3. Context Window Siniri:**

```
Total_context = input_tokens + output_tokens <= context_window

Llama 3.1 70B: context_window = 128K
DeepSeek R1: context_window = 64K
```

Real_deep_research.py'deki final prompt'un input boyutu:

```
Input = combined_research + conflict_info + source_list + prompt_template

combined_research = S * ortalama_analiz_uzunlugu
                  = 20 * ~500 token = ~10000 token
conflict_info ~ 500 token
source_list = 20 * ~50 token = ~1000 token
prompt_template ~ 500 token
TOPLAM INPUT ~ 12000 token + max_tokens_output = 4000
TOTAL ~ 16000 token (128K limitinin %12.5'i)
```

Bol headroom var. Ancak lokal modeller icin (ornegin 8K context Mistral 7B), bu input boyutu context'i asabilir.

### Token Budget Optimizasyonu

**Artimsal truncation:**

Eger toplam input context_window'u asarsa, en dusuk guvenilirlik skorlu kaynaklari cikar:

```python
while total_tokens(combined_research) > MAX_INPUT_TOKENS:
    combined_research.pop()  # en dusuk skorlu kaynagi cikar
```

Bu strateji kodda UYGULANMIYOR. Input boyutu kontrolsuz. Cok fazla kaynak toplandiysa context overflow olabilir.

**Sliding window summarization:**

Buyuk arasstirmalarda icerik summarize edilebilir:
```
Asama 1: 20 kaynak -> 5 ozet (her biri 4 kaynagi ozetler)
Asama 2: 5 ozet -> 1 final rapor
```

Bu, token kullanmini O(S) yerine O(log S) yapar.

---

## 2.6 Sinirlamalar

1. **Celiski cozumu LLM'e bagli:** Deterministik degil, tekrarlanabilir degil. Ayni kaynaklar farkli zamanlarda farkli cozumler uretebilir.

2. **Citation integrity garanti edilmiyor:** LLM, phantom referans uretebilir veya kaynak atlamayabilir.

3. **Token limit rapor kalitesini kisitlar:** 4000-5000 token ile ~3000-4000 kelimelik rapor (~8-10 sayfa). Cok detayli konular icin yetersiz olabilir.

4. **Kaynak agirlandirmasi basit:** Guvenilirlik skoru tek boyutlu (0-100 veya 1-10). Gercekte kaynak kalitesi cok boyutlu: otorite, guncellik, derinlik, objektiflik ayri agirlilandirilmali.

5. **Rapor yapisi garanti degilmis:** LLM'in istenen formata uymasi "istek" degil "zorlama" ile saglanmali. Pydantic schema veya output parser kullanilabilir.

6. **Recursive summarization yok:** 20 kaynagi tek seferde ozet istenir -- context window sinirini zorlayabilir.
