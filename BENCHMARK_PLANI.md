# LocoDex DeepSearch — Benchmark Planı

**Oluşturulma:** 2026-04-25
**Durum:** Plan aşaması — bu sprint'te uygulanmayacak, ileride yapılacak
**Soru:** Lokal model + DeepSearch pipeline, GPT-4/Grok/Perplexity gibi cloud rakiplerden ne kadar uzakta?

---

## 1. Mevcut Durum

- **Aktif model:** Gemma 3 12B (8.1 GB, 9 ay önce indirilmiş — Ollama)
- **README iddiası:** "Grok'a 9/10 kalite, %95+ accuracy" → **kanıtsız**
- **Düzeltme:** İddialar yumuşatıldı (`subjective evaluation`) ama benchmark hâlâ yapılmadı

## 2. Modeller — Güncel Durum

LocoDex'i Gemma 3 12B yerine güncel/güçlü modellerle test etmek lazım. Yerel envanter:

### 2.1 LM Studio (`~/.lmstudio/models/lmstudio-community/`)

| Model | Boyut | Tip | Önemi |
|---|---|---|---|
| **gemma-4-26B-A4B-it** | ~26B aktif ~4B | MoE GGUF | 2026 yeni, Gemma 3'ün halefi |
| **Qwen3.5-35B-A3B** | ~35B aktif ~3B | MoE GGUF | Hızlı, güçlü |
| **GLM-4.7-Flash-MLX-6bit** | ~? | MLX (Apple) | M4 Max'te yerli hız |
| **NVIDIA-Nemotron-3-Nano-30B-A3B-MLX-4bit** | 30B MoE | MLX | Düşük VRAM ile yüksek kalite |
| **Qwen3-32B** | 32B dense | GGUF | Kanonik baseline |
| **QwQ-32B** | 32B | GGUF | Reasoning odaklı |
| **DeepSeek-R1-Distill-Qwen-32B** | 32B | GGUF | Reasoning, distill |
| **gemma-3-27b-it** | 27B | GGUF | Mevcut Gemma 3'ten daha büyük |
| **gpt-oss-20b** | 20B | GGUF | OpenAI açık model |

### 2.2 Ollama (`ollama list`)

| Model | Boyut | Modified | Not |
|---|---|---|---|
| **gemma4:31b** | 19 GB | 3 hafta | LocoDex aday — Gemma 3 12B'nin doğal halefi |
| qwen3-coder:30b | 18 GB | 8 ay | Coding odaklı, RAG için aşırı |
| qwen3:30b-a3b | 18 GB | 9 ay | MoE genel amaçlı |
| gpt-oss:latest | 13 GB | 8 ay | |
| gemma3:12b | 8.1 GB | 9 ay | **Mevcut LocoDex modeli** |
| deepseek-r1:14b | 9.0 GB | 9 ay | Reasoning |

### 2.3 Önerilen Test Şampiyonları

LocoDex pipeline'ında 3 farklı modeli test et:

1. **Hızlı/küçük baseline:** `gemma3:12b` (mevcut, kontrol noktası)
2. **Güncel daha güçlü:** `gemma4:31b` (Ollama, hazır) **veya** `gemma-4-26B-A4B-it` (LM Studio MoE, daha hızlı)
3. **Reasoning odaklı:** `DeepSeek-R1-Distill-Qwen-32B` veya `QwQ-32B` — DeepSearch tipik olarak multi-hop muhakeme gerektiriyor, reasoning model'in faydası ölçülmeli

---

## 3. Benchmark Framework Seçimi

### 3.1 RAGAS (Önerilen — pratik)

- **GitHub:** `github.com/explodinggradients/ragas`
- **Pip:** `pip install ragas`
- **2026 durumu:** Hâlâ aktif, RAG eval'da SOTA
- **Metrikler:**
  - `context_precision` — getirilen pasajlar sorulan soruya ne kadar uygun
  - `context_recall` — gerekli bilgilerin yüzde kaçı getirilmiş
  - `faithfulness` — cevap pasajlardan türeyen mi yoksa halüsinasyon mu
  - `answer_relevancy` — cevap soruyu ne kadar karşılıyor
- **Önemi:** Reference-free — ground-truth cevaba ihtiyaç yok, LLM-as-judge ile çalışıyor (GPT-4 veya Claude judge önerilir)

### 3.2 CRAG (Meta, 2024)

- **GitHub:** `github.com/facebookresearch/CRAG`
- **Veri:** 4,409 soru-cevap, 5 domain (finance, sports, music, movies, open), 8 kategori
- **Mock API'lar:** web search ve KG simülasyonu var
- **Niye önemli:** En çetin RAG benchmark — SOTA modellerin %63 başarısı
- **Boyut:** ~2GB

### 3.3 NQ Open / TriviaQA (klasik)

- **HuggingFace:** `nq_open`, `trivia_qa`
- **Boyut:** subset 100-500 soru yeterli
- **Avantaj:** Kanonik, kıyaslanabilir sonuç tabanı geniş

### 3.4 2026 Yeni Eklenenler

- **LegalBench-RAG** — hukuki QA (LocoDex hedefi değil)
- **WixQA** — web-scale, daha gerçekçi
- **T²-RAGBench** — multi-turn, görev odaklı

**Önerim:** RAGAS + CRAG (50-100 soruluk subset) + NQ Open (100 soru) başlangıç paketi.

---

## 4. Karşılaştırılacak Rakipler

| Sistem | Model | Tür | Erişim |
|---|---|---|---|
| **LocoDex (eski)** | Gemma 3 12B | Lokal RAG | Mevcut |
| **LocoDex (yeni)** | Gemma 4 31B / DeepSeek-R1 | Lokal RAG | Test edilecek |
| **GPT-4o** | OpenAI cloud | Cloud RAG/Search | API ücreti |
| **Claude Opus 4.7** | Anthropic | Cloud, web search | API ücreti |
| **Perplexity** | Cloud RAG | Web app | Pro abonelik |
| **Grok** | xAI | Cloud | API |
| **Gemini 2.5 Pro** | Google | Cloud Search-RAG | API |

API ücretleri çıkarsa: Claude/GPT-4o aynı 100 soru ile $5-20 civarı, 4 sistem × 100 soru ≈ $20-80 toplam.

---

## 5. Önerilen Çalışma Planı

### Faz 1 — Sandbox (1 gün)
- `pip install ragas datasets evaluate openai anthropic`
- 10 örnek soruyla LocoDex (Gemma 3) RAGAS pipeline'ını çalıştır
- Çıktı formatı + metrik akışı doğrulanır

### Faz 2 — Çoklu Model Lokal Test (2-3 gün)
- Aynı 100 soruluk NQ subset üzerinde:
  - Gemma 3 12B (baseline)
  - Gemma 4 31B (güncel)
  - DeepSeek-R1-Distill-32B (reasoning)
- RAGAS metriklerini kaydet, latency + cost (token) ölç

### Faz 3 — CRAG (3-5 gün)
- CRAG'in 5 domain'inden 50'şer soru = 250 soru
- En iyi 2 lokal model + 1 cloud (GPT-4o veya Claude) ile çalıştır
- Domain bazlı kıyaslama tablosu

### Faz 4 — Rapor (2 gün)
- Sonuçları `teknik_dokuman/` altına ek bölüm:
  - "DeepSearch Benchmark Sonuçları (2026-XX)"
  - Tablo: model × metric × dataset
  - README'deki "9/10 vs Grok" iddiasını gerçek sayılarla değiştir

---

## 6. Dosya Konumu Önerisi

```
LocoDex-deep-search/
├── benchmarks/
│   ├── datasets/            # NQ, CRAG subset, custom queries
│   ├── results/
│   │   ├── gemma3_12b/
│   │   ├── gemma4_31b/
│   │   ├── deepseek_r1_32b/
│   │   ├── gpt4o/
│   │   └── claude_opus_47/
│   ├── scripts/
│   │   ├── run_ragas.py
│   │   ├── run_crag.py
│   │   ├── compare.py
│   │   └── plot.py
│   └── reports/
│       └── 2026-XX-XX-baseline-vs-gemma4.md
```

---

## 7. Risk ve Dikkat

- **LLM-as-judge bias:** RAGAS GPT-4 judge kullanırsa, GPT-4 tabanlı sistem haksız avantaj alabilir → Claude judge ile cross-validate
- **Latency:** Lokal Gemma 4 31B vs cloud GPT-4o eşit cevap kalitesi verse bile 5-10× yavaş — bu da "lokal değer" tartışmasında kritik
- **Domain seçimi:** NQ Wikipedia ağırlıklı, TR sorularında zayıf — gerçek kullanım Türkçe ise ek TR query set ekle
- **Eski Gemma 3 sonuçları:** "9/10 vs Grok" iddiası burayla doğrulanmalı/çürütülmeli — sonuç ne çıkarsa README'ye dürüstçe yansıt

---

## 8. Sonraki Adım (gerçekten başladığımızda)

1. Bu dosyayı yeniden oku
2. Yerel ortama RAGAS kur, smoke test (10 soru, Gemma 3) çalıştır
3. Sonuca göre güncel modellerle Faz 2'ye geç
4. Sonuçlar `benchmarks/reports/` altında haftalık güncelleme

---

## 9. Bu Plan Yapılırken Karadul Benchmark'ı Da Bekliyor

`/Users/apple/Desktop/black-widow/BENCHMARK_YAPILACAKLAR.md` — Karadul tarafında DIRTY + Coreutils planı var. İki proje birlikte değerlendirilebilir, ama önce LocoDex (RAGAS daha kolay setup).
