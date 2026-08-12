# LocoDex Deep Search v1.2

> **Local AI Research Service**
> A privacy-first, locally-runnable alternative to commercial deep-research tools.

[![GitHub](https://img.shields.io/badge/GitHub-berketez/LocoDex--deep--search-blue?style=flat-square&logo=github)](https://github.com/berketez/LocoDex-deep-search)
[![Python](https://img.shields.io/badge/Python-3.11+-green?style=flat-square&logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?style=flat-square&logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

## Qualitative Comparison (Subjective)

**Test environment: Apple M4 Max (32 GPU cores, 16GB VRAM)**

The numbers below are an *internal subjective evaluation* on a small set of personal test queries — they are **not the result of a rigorous, reproducible benchmark** (no public test set, no annotator panel, no statistical sample size). They are shared only to give a rough sense of the system's qualitative behaviour next to a commercial baseline.

| System | Subjective Score | Wall-clock Time | Model |
|--------|------------------|-----------------|--------|
| LocoDex Deep Search | ~9 / 10 (subjective) | ~3 minutes | Gemma 3 12B (local) |
| Grok 3 Deep Search  | ~10 / 10 (subjective) | ~5 minutes | Grok 3 (cloud) |

> **Accuracy claims:** Any percentage-style accuracy figure (e.g. "≈95%") in earlier versions of this README was *anecdotal* and has been removed. A rigorous benchmark on a public dataset (HotpotQA / GAIA / 2WikiMultihopQA) has not yet been performed. See `deep_research_service/evals.py` for the LLM-as-a-Judge harness intended for such a benchmark.

> **No "outperforming" claim:** LocoDex is a free, fully-local research pipeline — it is *not* meant to outperform Grok 3 in absolute quality. Its value proposition is **privacy + local execution + zero API cost**, not raw answer quality.

## Key Features

- **100% Local Processing** - No API keys, no data leaks
- **Date-Aware Research** - Publication dates are extracted deterministically from pages (JSON-LD → meta tags → `<time>` → URL → text); stale sources are penalized according to how time-sensitive the topic is
- **Claim-Level Cross-Verification** - Claims are extracted from every source and corroborated across independent domains; contradictions are detected and resolved in favor of newer + more reliable sources
- **Computed Confidence Scores** - Every key finding carries a confidence score calculated in Python (source count × reliability × freshness × contradictions), not invented by the LLM
- **Real Iterative Research** - Unanswered sub-questions trigger additional search rounds automatically
- **Multilingual Research** - Smart language detection (diacritic-free Turkish included)
- **Multi-Engine Search** - DuckDuckGo text + news (time-filtered); queries that come back empty are retried on backup engines (Bing, Yandex, Brave, Mojeek), domain diversity enforcement
- **WebSocket Real-time** - Live progress updates
- **Docker Ready** - One-command deployment

## What's New in v1.2

- **Terminal CLI (`locodex`)** — Research runs from a terminal with no server and
  no browser. Progress goes to stderr, the report to stdout, so `> report.md`
  gives a clean file while you still watch the run.
- **Guided TUI wizard** — Arrow-key selection for provider, model and depth. If
  the model server is not running it is started for you and the CLI waits until
  its API answers. Only models actually installed on that provider are listed.
- **Persistent research session** — The prompt stays open after a run. Follow-up
  questions are answered from findings already in memory (**no new web search**),
  a "go deeper" request triggers a focused extra round, and an unrelated topic
  starts a fresh run. In-session commands: `/rapor`, `/kaynaklar`, `/gecmis`,
  `/yeni`, `/yardim`, `/cikis`.
- **Memory sizing guidance** — Measured residency figures for large models, plus
  the Apple Silicon caveat that reported "free VRAM" is not free RAM. See
  [Memory sizing](#memory-sizing).

## What's New in v1.1

- **Per-Domain Rate Limiter** — Async rate limiting prevents hammering the same domain. Default: max 1 request per 2 seconds per host. No more getting blocked by aggressive crawling.
- **Research Cache (SQLite)** — Results are cached locally for 24 hours. Repeat queries return instantly without burning compute or network time. Zero new dependencies (uses stdlib `sqlite3`).
- **Export API (Markdown & HTML)** — New REST endpoint `GET /export/{format}?topic=...` lets you export any cached research result as clean Markdown or a self-contained HTML page.

## Why Choose LocoDex Deep Search?

### **Privacy First**
- Zero data transmission to external servers
- Complete control over your research data
- GDPR compliant by design

### **Cost Effective**  
- No API usage fees
- One-time setup, unlimited research
- Perfect for enterprise and research institutions

### **High Performance**
- Optimized for 16GB+ VRAM systems
- Efficient memory usage with large models
- Sub-5 minute complex research completion

## Quick Start

### Prerequisites
- **Python 3.11+**
- **Enough free memory for the model you choose** — a 12B model needs ~16 GB, a
  31B model at long context needs ~30 GB. See [Memory sizing](#memory-sizing)
  before running a large model; oversubscribing memory can hang the machine.
- **Docker** (optional)

### Method 1: Terminal CLI (Recommended)

No server, no browser — run research straight from a terminal.

```bash
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search
pip install -r deep_research_service/requirements.txt

# Put `locodex` on your PATH (any directory in PATH works)
ln -s "$PWD/bin/locodex" /opt/homebrew/bin/locodex
```

**Interactive session** — just run:

```bash
locodex deepsearch
```

You get a guided flow:

1. **Provider** — pick Ollama or LM Studio. If the server is not running, it is
   started for you and the CLI waits until its API responds.
2. **Model** — pick from the models actually installed on that provider.
3. **Depth** — fast (1 round / 6 sources), balanced (2 / 10) or deep (3 / 14).
4. **Prompt box** — type what to research.

When the run finishes, the terminal shows a **summary** (sources, findings,
confidence, report path) while the full report is written to disk as Markdown.
The session then **stays open and asks for the next request**.

Follow-up requests are classified automatically:

| Intent | Behaviour |
|--------|-----------|
| Follow-up question | Answered from the findings already in memory — **no new web search** |
| Deeper dive | A focused new round on the aspect that was missing |
| Unrelated topic | A full new research run |

In-session commands: `/rapor` (report path), `/kaynaklar` (source list),
`/gecmis` (session history), `/yeni <topic>` (force a fresh run), `/yardim`,
`/cikis`.

**One-shot mode** — scriptable, report goes to stdout:

```bash
locodex deepsearch "AI in food manufacturing 2026" -m gemma4:31b > report.md

locodex models                    # list installed models
locodex config --model gemma4:31b # set a default model
locodex serve                     # start the WebSocket/REST server instead
```

| Flag | Purpose |
|------|---------|
| `-m, --model` | model to use; omit it to get the picker |
| `-s, --source` | `Ollama` or `LM Studio` (inferred when omitted) |
| `-e, --engine` | `verified` (default) or `smart` |
| `-o, --out` | directory to save the report in |
| `--rounds` / `--sources` / `--queries` | tune depth per run |
| `--fast` | preset: 1 round, 6 sources, 4 queries |
| `--no-cache` | ignore the 24-hour result cache |
| `-q, --quiet` | hide progress lines |

Progress is written to stderr and the report to stdout, so redirecting to a file
keeps the report clean while progress stays visible on screen.

### Method 2: Docker

```bash
# Clone the repository
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search

# Build and run with Docker
docker build -t locodex-deepsearch ./deep_research_service
docker run -p 8001:8001 locodex-deepsearch
```

### Method 3: Local Installation

```bash
# Clone and setup
git clone https://github.com/berketez/LocoDex-deep-search.git
cd LocoDex-deep-search/deep_research_service

# Install dependencies
pip install -r requirements.txt

# Start the service
python server.py
```

### Method 4: With Local LM Studio

1. **Install LM Studio** and load a model (Gemma 3 12B recommended)
2. **Start LM Studio server** on port 1234
3. **Run LocoDex Deep Search**:

```bash
python server.py
```

4. **Access via WebSocket** at `ws://localhost:8001/research_ws`

## Configuration

### Supported AI Providers

| Provider | Setup | Performance |
|----------|--------|-------------|
| **LM Studio** | Local server on :1234 | 5/5 |
| **Ollama** | Local installation | 4/5 |
| **Together AI** | API key required | 3/5 |

### Recommended Models

- **Gemma 3 12B** - Fast and lightweight (16GB VRAM)
- **Gemma 3 27B** - Best balance of speed and quality (24GB VRAM)
- **Gemma 4 31B** - Latest generation, frontier-level reasoning (32GB+, see below)
- **GLM-4 32B** - GPT-4o competitive, strong multilingual and code (32GB+)

### Memory sizing

Weights are only part of the cost. The KV cache grows with context length, and a
multimodal model also loads a vision projector. Measured on an M4 Max (36 GB
unified memory) running `gemma4:31b` through Ollama at a 65 536-token context:

| Component | Size |
|-----------|------|
| Model weights (Q4_K_M) | 17.4 GB |
| KV cache @ 64K context | 6.2 GB |
| Vision projector (mmproj) | 1.3 GB |
| Compute buffers + context checkpoints | ~3 GB |
| **Resident total** | **~30 GB** |

Two things to know before running a large model:

- **On Apple Silicon, "free VRAM" is not free RAM.** Metal reports a GPU budget
  (~78% of total memory) that ignores what other apps already hold. A loader can
  decide the model "fits" while the system is nearly out of memory.
- **Context length is the cheapest lever.** Halving `OLLAMA_CONTEXT_LENGTH` from
  65 536 to 32 768 gives back roughly 3 GB with no change to model quality.

Rule of thumb: keep total model residency under **70% of physical memory**, and
close browsers and other model servers before loading a 30B-class model.

### Reasoning models

Reasoning models (Qwen3, DeepSeek-R1, gpt-oss) spend their output budget on a
chain of thought *before* writing the answer. The research pipeline asks for
structured JSON against a schema it already specifies, so that thinking buys
nothing — and on a short limit the model is cut off before it emits a single
character of JSON.

Measured on qwen3.6-27b via LM Studio, one research run: **6 of 6 calls hit the
token limit, and all 4194 generated tokens were reasoning.** Every planning step
silently fell back to defaults. Topic analysis took 145 s and returned nothing.

The client therefore disables thinking on every call. The effective switch
differs per server, and several plausible ones are silently ignored:

| Field | LM Studio (MLX) |
|-------|-----------------|
| `reasoning_effort: "none"` | **works** |
| `chat_template_kwargs.enable_thinking` | ignored |
| `/no_think` in the prompt | ignored |
| `reasoning.enabled` | ignored |

Ollama uses `think: false`. Unsupported fields are dropped on the first client
error and remembered, so no request pays for the same rejection twice. After the
fix the same two planning steps take **21.8 s instead of 323 s**, and they return
real results rather than falling back.

To keep the chain of thought — for synthesis quality over speed — construct the
client with `LocalLLMClient(..., enable_thinking=True)`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RESEARCH_ENGINE` | `verified` | Research engine: `verified` (date-aware, claim-verified) or `smart` (legacy) |
| `OLLAMA_HOST_IP` | auto | Model server host; auto-resolves `host.docker.internal` → `127.0.0.1` |
| `RESEARCH_OUTPUT_DIR` | Desktop / `research_results` | Where report `.md` files are saved |
| `BIND_HOST` | `0.0.0.0` | Server bind address; use `127.0.0.1` to restrict to local access |

### Reading the Report

Every research run produces a Markdown report with:

- **Overall confidence score** in the header, plus a staleness warning when the newest verified source is older than the topic requires
- **Key Findings** — one line per verified finding: statement, confidence label (`high ≥85%`, `medium ≥60%`, `low` below), number of independent sources, newest publication date, and a `ÇELİŞKİ` note naming the conflicting source numbers when sources disagree
- **Contradictions & Recency** — which source says what, which is newer/more reliable, and which information is likely outdated
- **Source table** — every source with its publication date, how the date was extracted (JSON-LD, meta tag, URL...), and its reliability score
- **Methodology** — how the numbers were computed, so results are auditable

## API Usage

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

## Architecture

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
2. **Multi-engine search** — DuckDuckGo text + news (time-filtered for hot topics), empty queries retried on backup engines, per-domain caps
3. **Content + date extraction** — pages fetched in parallel; publication date extracted deterministically from the page itself
4. **Claim extraction** — structured claims per source (single JSON-mode LLM call per source)
5. **Cross-verification** — claims merged across sources; confidence computed in Python from independent-source count, source reliability (domain prior + LLM assessment), freshness, and contradictions
6. **Gap-driven iteration** — sub-questions without confident answers trigger up to 2 extra search rounds
7. **Structured report** — direct answer, per-finding confidence labels, contradiction & recency analysis, dated source table, methodology

The legacy engine is still available: set `RESEARCH_ENGINE=smart` to use it.

## Technical Specifications

- **Framework:** FastAPI + WebSocket
- **Search Engines:** DuckDuckGo (`ddgs`, text + news), with Bing/Yandex/Brave/Mojeek as fallbacks for empty results; Tavily optional
- **Languages:** Python 3.11+
- **Deployment:** Docker, Kubernetes ready
- **Memory:** 16GB+ for 12B-class models; see [Memory sizing](#memory-sizing) for larger ones

## Confidence Scoring (How Reliability Is Estimated)

LocoDex does **not** claim a fixed accuracy percentage. Instead, every finding in a report carries a confidence score computed transparently:

```
source_reliability = 0.6 × domain_prior + 0.4 × LLM_content_assessment
base_confidence    = 1 - Π(1 - reliability_i × 0.8)   over independent domains
freshness_factor   = applied when the claim is time-sensitive
contradiction      = capped at 40% when contradicted by a newer/stronger source
```

Labels: **≥85% high confidence**, **≥60% medium**, below that **low** — printed next to every finding together with the number of independent sources and the newest publication date. A report-level freshness warning is emitted when the newest verified source is older than the topic's staleness threshold.

### Performance on Different Hardware

| Hardware | Model | Memory Usage | Time |
|----------|-------|--------------|------|
| M4 Max 32 GPU | Gemma 3 12B | 14GB | 3 min |
| RTX 4090 | Gemma 3 12B | 16GB | 2.5 min |
| RTX 3080 | Llama 3.1 8B | 12GB | 4 min |
| M4 Max (36 GB unified) | Gemma 4 31B | ~30GB | 12 min 14 s |
| M4 Max (36 GB unified) | Gemma 3 4B | not measured | 2 min 05 s |

The last two rows are from a same-machine, same-prompt comparison on 2026-08-12
(balanced depth: 2 rounds × 10 sources, cache disabled, verified engine). Model
size buys source analysis quality, not speed — budget roughly 6× the wall-clock
time when moving from a 4B to a 31B model.

## Contributing

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

## License

Released under the **MIT License** — free to use, modify, distribute and sell,
including commercially, as long as the copyright notice is kept. Provided as is,
without warranty. Full text: [LICENSE](LICENSE).

Copyright © 2025-2026 Berke Tezgöçen.

## Author

**Berke Tezgöçen**
- Email: [berketezgocen@hotmail.com](mailto:berketezgocen@hotmail.com)
- GitHub: [@berketez](https://github.com/berketez)

## Acknowledgments

- Thanks to the open-source AI community
- Inspired by academic research in information retrieval
- Built for researchers and developers

---

**Star this repo** if you find it useful!

[![Star History Chart](https://api.star-history.com/svg?repos=berketez/LocoDex-deep-search&type=Date)](https://star-history.com/#berketez/LocoDex-deep-search&Date)