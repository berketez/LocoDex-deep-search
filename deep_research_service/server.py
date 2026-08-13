import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel
import sys
import os
import json

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from smart_multilingual_research import SmartMultilingualResearcher
from verified_research import VerifiedDeepResearcher
from utils.research_cache import research_cache
from utils.exporter import to_markdown, to_html
import asyncio
import logging

# Araştırma motoru seçimi: "verified" (varsayılan) veya "smart" (eski motor)
RESEARCH_ENGINE = os.environ.get("RESEARCH_ENGINE", "verified").lower()


def create_researcher(model_name, model_source, websocket):
    """Aktif araştırma motorunu döndürür."""
    if RESEARCH_ENGINE == "smart":
        return SmartMultilingualResearcher(
            model_name=model_name, model_source=model_source, websocket=websocket
        )
    return VerifiedDeepResearcher(
        model_name=model_name, model_source=model_source, websocket=websocket
    )


def cache_variant(model_name):
    """Önbellek anahtarının motor + model bileşeni.

    Aynı konu farklı model ya da motorla sorulduğunda öncekinin cevabı
    dönmesin diye anahtara eklenir.
    """
    return f"{RESEARCH_ENGINE}|{model_name or 'default'}"


def cacheable(researcher):
    """Sonucun önbelleğe yazılmaya değer olup olmadığı.

    Kaynaksız biten koşu (ağ kesintisi, arama motoru boş döndü) önbelleğe
    yazılmaz: boş raporu 24 saat sunmak yeniden denemeyi engelliyordu.
    """
    return getattr(researcher, "sources", None) != []


# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()


class ResearchRequest(BaseModel):
    topic: str
    model: str | None = None  # İsteğe bağlı model adı


class _NullWebSocket:
    """HTTP isteklerinde progress mesajlarını yutan sahte websocket."""

    async def send_json(self, _data):
        pass


@app.post("/research")
async def research_http(request: ResearchRequest):
    """
    Conducts deep research on a given topic via HTTP (no streaming progress).
    """
    try:
        variant = cache_variant(request.model)
        cached = research_cache.get(request.topic, variant)
        if cached:
            logger.info(f"HTTP cache hit for topic: {request.topic}")
            return cached

        researcher = create_researcher(
            model_name=request.model or "default",
            model_source="Unknown",
            websocket=_NullWebSocket(),
        )
        answer = await researcher.run_research(request.topic)
        result = {"status": "success", "answer": answer}
        if cacheable(researcher):
            research_cache.set(request.topic, result, variant)
        return result
    except Exception as e:
        logger.error(f"HTTP research error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.websocket("/research_ws")
async def research_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")

    # İlk bağlantı mesajı gönder
    await websocket.send_json({"type": "progress", "step": 0, "message": "Bağlantı kuruldu, araştırma isteği bekleniyor..."})

    # Keepalive task başlat
    async def keepalive_task():
        while True:
            try:
                await asyncio.sleep(30)  # Her 30 saniyede bir ping
                await websocket.send_json({"type": "keepalive"})
                logger.debug("Keepalive ping sent")
            except Exception as e:
                logger.error(f"Keepalive error: {e}")
                break

    keepalive = asyncio.create_task(keepalive_task())

    try:
        while True:
            try:
                # WebSocket receive timeout ekle - daha uzun süre bekle
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300)  # 5 dakika
            except asyncio.TimeoutError:
                logger.info("WebSocket receive timeout - sending keepalive")
                await websocket.send_json({"type": "keepalive", "message": "Bağlantı aktif, araştırma isteği bekleniyor..."})
                continue

            try:
                request = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(f"JSON PARSE ERROR: {e}")
                await websocket.send_json({"type": "error", "data": f"JSON hatası: {str(e)}"})
                continue

            # Ping mesajlarını ele al
            if request.get("type") == "ping":
                continue

            topic = request.get("topic")
            model_info = request.get("model")  # Client'ten gelen { id: "model_name", source: "provider" } formatı

            if not topic:
                logger.error("Topic is missing from request")
                await websocket.send_json({"type": "error", "data": "Topic is required"})
                continue

            # Model adı ve kaynağını parse et
            if isinstance(model_info, dict):
                model_name = model_info.get('id', 'default')
                model_source = model_info.get('source', 'Unknown')
            else:
                # Fallback - eski string format
                model_name = str(model_info) if model_info else 'default'
                model_source = 'Unknown'

            logger.info(f"Processing research for topic: '{topic}' with model: {model_name} from {model_source}")

            # Araştırma motoru bildirimi
            engine_label = "Doğrulamalı derin araştırma" if RESEARCH_ENGINE != "smart" else "Akıllı çok dilli araştırma"
            await websocket.send_json({"type": "progress", "step": 0, "message": f"{engine_label} başlıyor..."})

            researcher = create_researcher(
                model_name=model_name,
                model_source=model_source,
                websocket=websocket
            )

            try:
                # Check cache first
                variant = cache_variant(model_name)
                cached = research_cache.get(topic, variant)
                if cached:
                    logger.info(f"Cache hit for topic: {topic}")
                    await websocket.send_json({"type": "progress", "step": 1.0, "message": "Önbellekten sonuç bulundu"})
                    await websocket.send_json({"type": "result", "data": cached.get("answer", "")})
                    continue

                # Model yüklendi bildirimi gönder
                await websocket.send_json({"type": "progress", "step": 0, "message": f"Model hazır: {model_name} ({model_source})"})

                answer = await researcher.run_research(topic)

                # Cache the result
                if cacheable(researcher):
                    research_cache.set(topic, {"answer": answer, "status": "success"}, variant)

                await websocket.send_json({"type": "result", "data": answer})

            except Exception as e:
                logger.error(f"Research error: {str(e)}")
                await websocket.send_json({"type": "error", "data": f"Araştırma hatası: {str(e)}"})
                # WebSocket bağlantısını devam ettir, hata yüzünden kapatma
                continue

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        keepalive.cancel()
        try:
            await keepalive
        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled.")
        try:
            await websocket.close()
            logger.info("WebSocket connection closed.")
        except RuntimeError:
            # Bağlantı zaten kopmuşsa close() istisna üretebilir
            pass


@app.get("/export/{fmt}")
async def export_research(
    fmt: str,
    topic: str = Query(..., description="Research topic to export"),
    model: str = Query("default", description="Model the research was run with"),
):
    """Export a cached research result as Markdown or HTML.

    ``fmt`` must be ``"markdown"`` or ``"html"``.  Cache entries are keyed
    by engine + model + topic, so ``model`` must match the research run.
    """
    cached = research_cache.get(topic, cache_variant(model))
    if cached is None:
        return PlainTextResponse(
            f"No cached result found for topic: {topic}", status_code=404
        )

    if fmt == "markdown":
        md = to_markdown(topic, cached)
        return PlainTextResponse(md, media_type="text/markdown")
    elif fmt == "html":
        html = to_html(topic, cached)
        return HTMLResponse(html)
    else:
        return PlainTextResponse(
            f"Unsupported format: {fmt}. Use 'markdown' or 'html'.", status_code=400
        )


@app.get("/cache/stats")
async def cache_stats():
    """Return basic cache statistics."""
    return research_cache.stats()


@app.delete("/cache")
async def clear_cache():
    """Purge all cached research results."""
    research_cache.clear()
    return {"status": "success", "message": "Cache cleared"}


if __name__ == "__main__":
    # Docker'da 0.0.0.0 gerekir; doğrudan host üzerinde çalıştırırken
    # BIND_HOST=127.0.0.1 ile yalnızca yerel erişime kapatılabilir.
    uvicorn.run(app, host=os.environ.get("BIND_HOST", "0.0.0.0"), port=8001)
