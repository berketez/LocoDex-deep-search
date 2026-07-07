# 🔍 LocoDex Deep Search v1.1

> **Local AI Research Service**
> A privacy-first, locally-runnable alternative to commercial deep-research tools.

[![GitHub](https://img.shields.io/badge/GitHub-berketez/LocoDex--deep--search-blue?style=flat-square&logo=github)](https://github.com/berketez/LocoDex-deep-search)
[![Python](https://img.shields.io/badge/Python-3.11+-green?style=flat-square&logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?style=flat-square&logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

## 🚀 Qualitative Comparison (Subjective)

**Test environment: Apple M4 Max (32 GPU cores, 16GB VRAM)**

The numbers below are an *internal subjective evaluation* on a small set of personal test queries — they are **not the result of a rigorous, reproducible benchmark** (no public test set, no annotator panel, no statistical sample size). They are shared only to give a rough sense of the system's qualitative behaviour next to a commercial baseline.

| System | Subjective Score | Wall-clock Time | Model |
|--------|------------------|-----------------|--------|
| LocoDex Deep Search | ~9 / 10 (subjective) | ~3 minutes | Gemma 3 12B (local) |
| Grok 3 Deep Search  | ~10 / 10 (subjective) | ~5 minutes | Grok 3 (cloud) |

> **Accuracy claims:** Any percentage-style accuracy figure (e.g. "≈95%") in earlier versions of this README was *anecdotal* and has been removed. A rigorous benchmark on a public dataset (HotpotQA / GAIA / 2WikiMultihopQA) has not yet been performed. See `deep_research_service/evals.py` for the LLM-as-a-Judge harness intended for such a benchmark.

> **No "outperforming" claim:** LocoDex is a free, fully-local research pipeline — it is *not* meant to outperform Grok 3 in absolute quality. Its value proposition is **privacy + local execution + zero API cost**, not raw answer quality.

## ✨ Key Features

- 🏠 **100% Local Processing** - No API keys, no data leaks
- 📅 **Date-Aware Research** - Publication dates are extracted deterministically from pages (JSON-LD → meta tags → `<time>` → URL → text); stale sources are penalized according to how time-sensitive the topic is
- ⚖️ **Claim-Level Cross-Verification** - Claims are extracted from every source and corroborated across independent domains; contradictions are detected and resolved in favor of newer + more reliable sources
- 📊 **Computed Confidence Scores** - Every key finding carries a confidence score calculated in Python (source count × reliability × freshness × contradictions), not invented by the LLM
- 🔄 **Real Iterative Research** - Unanswered sub-questions trigger additional search rounds automatically
- 🌐 **Multilingual Research** - Smart language detection (diacritic-free Turkish included)
- 🔍 **Multi-Engine Search** - DuckDuckGo text + news (time-filtered) with Google fallback, domain diversity enforcement
- ⚡ **WebSocket Real-time** - Live progress updates
- 🐳 **Docker Ready** - One-command deployment

## 🆕 What's New in v1.1

- **Per-Domain Rate Limiter** — Async rate limiting prevents hammering the same domain. Default: max 1 request per 2 seconds per host. No more getting blocked by aggressive crawling.
- **Research Cache (SQLite)** — Results are cached locally for 24 hours. Repeat queries return instantly without burning compute or network time. Zero new dependencies (uses stdlib `sqlite3`).
- **Export API (Markdown & HTML)** — New REST endpoint `GET /export/{format}?topic=...` lets you export any cached research result as clean Markdown or a self-contained HTML page.

## 🎯 Why Choose LocoDex Deep Search?

### ✅ **Privacy First**
- Zero data transmission to external servers
- Complete control over your research data
- GDPR compliant by design

### ✅ **Cost Effective**  
- No API usage fees
- One-time setup, unlimited research
- Perfect for enterprise and research institutions

### ✅ **High Performance**
- Optimized for 16GB+ VRAM systems
- Efficient memory usage with large models
- Sub-5 minute complex research completion

## 🛠️ Quick Start

### Prerequisites
- **16GB+ VRAM** (GPU recommended)
- **Python 3.11+**
- **Docker** (optional)

### Method 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search

# Build and run with Docker
docker build -t locodex-deepsearch ./deep_research_service
docker run -p 8001:8001 locodex-deepsearch
```

### Method 2: Local Installation

```bash
# Clone and setup
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search/deep_research_service

# Install dependencies
pip install -r requirements.txt

# Start the service
python server.py
```

### Method 3: With Local LM Studio

1. **Install LM Studio** and load a model (Gemma 3 12B recommended)
2. **Start LM Studio server** on port 1234
3. **Run LocoDex Deep Search**:

```bash
python server.py
```

4. **Access via WebSocket** at `ws://localhost:8001/research_ws`

## 🔧 Configuration

### Supported AI Providers

| Provider | Setup | Performance |
|----------|--------|-------------|
| **LM Studio** | Local server on :1234 | ⭐⭐⭐⭐⭐ |
| **Ollama** | Local installation | ⭐⭐⭐⭐ |
| **Together AI** | API key required | ⭐⭐⭐ |

### Recommended Models

- **Gemma 3 12B** - Fast and lightweight (16GB VRAM)
- **Gemma 3 27B** - Best balance of speed and quality (24GB VRAM)
- **Gemma 4 31B** - Latest generation, frontier-level reasoning (24GB+ VRAM)
- **GLM-4 32B** - GPT-4o competitive, strong multilingual and code (24GB+ VRAM)

## 📡 API Usage

### WebSocket Research

```javascript
const ws = new WebSocket('ws://localhost:8001/research_ws');

ws.send(JSON.stringify({
    topic: "Artificial Intelligence in Healthcare 2024",
    model: {
        id: "gemma-3-12b",
        source: "lmstudio"
    }
}));

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'result') {
        console.log('Research completed:', data.data);
    }
};
```

### REST API

```bash
curl -X POST http://localhost:8001/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "Climate Change Solutions", "model": "gemma-3-12b"}'
```

### Export Research Results (v1.1)

```bash
# Export as Markdown
curl "http://localhost:8001/export/markdown?topic=Climate%20Change%20Solutions"

# Export as HTML
curl "http://localhost:8001/export/html?topic=Climate%20Change%20Solutions" -o report.html

# View cache statistics
curl http://localhost:8001/cache/stats

# Clear all cached results
curl -X DELETE http://localhost:8001/cache
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Client    │    │  FastAPI Server  │    │  Local AI Model │
│                 │◄──►│                  │◄──►│                 │
│  (WebSocket)    │    │   (Port 8001)    │    │ (Ollama/LMS)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                  ┌───────────────────────────┐
                  │  Verified Research Engine  │
                  └───────────────────────────┘
```

### Verified Research Pipeline (`verified_research.py`)

1. **Question analysis** — topic type, time sensitivity (`critical` / `moderate` / `low`), sub-questions
2. **Multi-engine search** — DuckDuckGo text + news (time-filtered for hot topics), Google fallback, per-domain caps
3. **Content + date extraction** — pages fetched in parallel; publication date extracted deterministically from the page itself
4. **Claim extraction** — structured claims per source (single JSON-mode LLM call per source)
5. **Cross-verification** — claims merged across sources; confidence computed in Python from independent-source count, source reliability (domain prior + LLM assessment), freshness, and contradictions
6. **Gap-driven iteration** — sub-questions without confident answers trigger up to 2 extra search rounds
7. **Structured report** — direct answer, per-finding confidence labels, contradiction & recency analysis, dated source table, methodology

The legacy engine is still available: set `RESEARCH_ENGINE=smart` to use it.

## 🔬 Technical Specifications

- **Framework:** FastAPI + WebSocket
- **Search Engines:** DuckDuckGo (`ddgs`, text + news) with Google fallback; Tavily optional
- **Languages:** Python 3.11+
- **Deployment:** Docker, Kubernetes ready
- **Memory:** Optimized for 16GB+ systems

## 📈 Confidence Scoring (How Reliability Is Estimated)

LocoDex does **not** claim a fixed accuracy percentage. Instead, every finding in a report carries a confidence score computed transparently:

```
source_reliability = 0.6 × domain_prior + 0.4 × LLM_content_assessment
base_confidence    = 1 - Π(1 - reliability_i × 0.8)   over independent domains
freshness_factor   = applied when the claim is time-sensitive
contradiction      = capped at 40% when contradicted by a newer/stronger source
```

Labels: **≥85% high confidence**, **≥60% medium**, below that **low** — printed next to every finding together with the number of independent sources and the newest publication date. A report-level freshness warning is emitted when the newest verified source is older than the topic's staleness threshold.

### Performance on Different Hardware

| Hardware | Model | VRAM Usage | Time |
|----------|-------|------------|------|
| M4 Max 32 GPU | Gemma 3 12B | 14GB | 3 min |
| RTX 4090 | Gemma 3 12B | 16GB | 2.5 min |
| RTX 3080 | Llama 3.1 8B | 12GB | 4 min |

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dev dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest tests/
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 👤 Author

**Berke Tezgöçen**
- 📧 Email: [berketezgocen@hotmail.com](mailto:berketezgocen@hotmail.com)
- 🐙 GitHub: [@berketez](https://github.com/berketez)

## 🙏 Acknowledgments

- Thanks to the open-source AI community
- Inspired by academic research in information retrieval
- Built with ❤️ for researchers and developers

---

⭐ **Star this repo** if you find it useful!

[![Star History Chart](https://api.star-history.com/svg?repos=berketez/LocoDex-deep-search&type=Date)](https://star-history.com/#berketez/LocoDex-deep-search&Date)