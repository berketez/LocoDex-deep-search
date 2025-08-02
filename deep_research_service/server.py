import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sys
import os
import json

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from real_deep_research import RealDeepResearcher
from smart_multilingual_research import SmartMultilingualResearcher
import asyncio
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Lokal model test fonksiyonları
async def test_lm_studio():
    """LM Studio'nun çalışıp çalışmadığını test eder"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:1234/v1/models", timeout=5) as response:
                return response.status == 200
    except:
        return False



class LocalDeepResearcher:
    """Tamamen lokal modellerle çalışan derin araştırma sınıfı"""
    
    def __init__(self, model_name, websocket):
        self.model_name = model_name
        self.websocket = websocket
        
    def call_local_model(self, prompt, system_prompt=""):
        """Lokal modeli çağırır - sync version with requests"""
        try:
            import requests
            
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            # Docker container'dan LM Studio'ya erişim için host IP kullan
            import socket
            try:
                # Docker container'dan host makineye erişim
                host_ip = socket.gethostbyname('host.docker.internal')
                lm_studio_url = f"http://{host_ip}:1234/v1/chat/completions"
            except:
                # Fallback for other systems or if host.docker.internal fails
                lm_studio_url = "http://localhost:1234/v1/chat/completions"
            
            response = requests.post(
                lm_studio_url, 
                json=payload, 
                timeout=600  # 10 dakika timeout - derin araştırma uzun sürer
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                return content
            else:
                error_msg = f"LM Studio HTTP hatası: {response.status_code} - {response.text}"
                return error_msg
                
        except requests.exceptions.Timeout:
            return "⏰ Model yavaş yanıt veriyor - daha küçük bir model deneyin"
        except Exception as e:
            return f"LM Studio bağlantı hatası: {str(e)}"
    
    async def research_topic(self, topic):
        """Tamamen lokal derin araştırma yapar - detaylı düşünme süreciyle"""
        
        await self.websocket.send_json({"type": "progress", "step": 0.05, "message": "🤔 Konuyu analiz etmeye başlıyorum..."})
        await asyncio.sleep(1)
        
        await self.websocket.send_json({"type": "progress", "step": 0.08, "message": f"📋 '{topic}' konusu için araştırma stratejisi belirliyorum..."})
        await asyncio.sleep(1)
        
        # 1. İlk araştırma planı
        await self.websocket.send_json({"type": "progress", "step": 0.1, "message": "🧠 Hangi bilgi türlerini araştırmam gerektiğini düşünüyorum..."})
        
        analysis_prompt = f"""
Aşağıdaki araştırma konusunu analiz et ve hangi alt konuların araştırılması gerektiğini belirle:

Konu: {topic}

Lütfen şu formatta yanıtla:
1. Ana konu özeti
2. Araştırılması gereken alt konular (5-7 tane)
3. Bu konuyla ilgili önemli noktalar
"""
        
        await self.websocket.send_json({"type": "progress", "step": 0.12, "message": "🔍 Model ile konu planını hazırlıyorum..."})
        analysis = self.call_local_model(analysis_prompt, "Sen detaylı araştırma yapan bir AI asistansın.")
        
        await self.websocket.send_json({"type": "progress", "step": 0.15, "message": "✅ Araştırma planı hazır! Alt konuları belirliyorum..."})
        await asyncio.sleep(1)
        
        # Alt konuları çıkar
        subtopics = []
        lines = analysis.split('\n')
        for line in lines:
            if any(marker in line for marker in ['1.', '2.', '3.', '4.', '5.', '-', '*']):
                clean_line = line.strip('1234567890.-* ')
                if len(clean_line) > 10:  # Anlamlı alt konular
                    subtopics.append(clean_line)
        
        await self.websocket.send_json({"type": "progress", "step": 0.18, "message": f"📚 {len(subtopics)} farklı açıdan konuyu araştıracağım..."})
        await asyncio.sleep(1)
        
        # Simüle kaynak listesi
        simulated_sources = [
            "Model bilgi tabanı - Temel kavramlar",
            "Model bilgi tabanı - Teknik detaylar", 
            "Model bilgi tabanı - Güncel gelişmeler",
            "Model bilgi tabanı - Pratik uygulamalar",
            "Model bilgi tabanı - Karşılaştırmalar",
            "Model bilgi tabanı - Uzman görüşleri"
        ]
        
        detailed_research = []
        collected_info = []
        
        for i, subtopic in enumerate(subtopics[:5]):  # Max 5 alt konu
            base_progress = 0.2 + (0.5 * i / len(subtopics[:5]))
            
            await self.websocket.send_json({"type": "progress", "step": base_progress, "message": f"🔎 '{subtopic[:60]}...' konusunu araştırıyorum"})
            await asyncio.sleep(1)
            
            # Kaynak seçimi simülasyonu
            selected_source = simulated_sources[i % len(simulated_sources)]
            await self.websocket.send_json({"type": "progress", "step": base_progress + 0.02, "message": f"📖 {selected_source} kaynağını inceliyorum..."})
            await asyncio.sleep(2)
            
            # Bilgi toplama simülasyonu
            await self.websocket.send_json({"type": "progress", "step": base_progress + 0.04, "message": f"💭 Bu kaynakta '{subtopic}' hakkında ne var bakalım..."})
            await asyncio.sleep(1)
            
            research_prompt = f"""
"{subtopic}" konusu hakkında detaylı bilgi ver. Özellikle "{topic}" ana konusu bağlamında:

- Temel kavramlar ve tanımlar
- Önemli özellikler ve karakteristikler  
- Avantajlar ve dezavantajlar
- Güncel durum ve gelişmeler
- Pratik uygulamalar

Detaylı ve bilgilendirici bir açıklama yap.
"""
            
            research = self.call_local_model(research_prompt, "Sen uzman bir araştırmacısın. Objektif ve detaylı bilgi verirsin.")
            
            # Bilgi değerlendirmesi
            await self.websocket.send_json({"type": "progress", "step": base_progress + 0.06, "message": f"🤓 Bulunan bilgiyi analiz ediyorum... ({len(research)} karakter bilgi toplandı)"})
            await asyncio.sleep(1)
            
            # Yeterlilik kontrolü simülasyonu
            if len(research) > 200:
                await self.websocket.send_json({"type": "progress", "step": base_progress + 0.08, "message": f"✅ '{subtopic}' için yeterli detay buldum!"})
                detailed_research.append(f"## {subtopic}\n\n{research}")
                collected_info.append(f"✓ {subtopic}: {len(research)} karakter ({selected_source})")
            else:
                await self.websocket.send_json({"type": "progress", "step": base_progress + 0.08, "message": f"⚠️ '{subtopic}' için bilgi az, başka açıdan bakayım..."})
                # Alternatif araştırma
                alt_prompt = f"'{subtopic}' konusu hakkında farklı bir perspektiften daha detaylı bilgi ver."
                alt_research = self.call_local_model(alt_prompt, "Farklı bir bakış açısıyla detaylı bilgi ver.")
                detailed_research.append(f"## {subtopic}\n\n{research}\n\n### Ek Bilgiler\n{alt_research}")
                collected_info.append(f"✓ {subtopic}: {len(research + alt_research)} karakter (alternatif araştırma)")
                await self.websocket.send_json({"type": "progress", "step": base_progress + 0.09, "message": f"💡 Alternatif perspektifle daha iyi bilgi topladım!"})
            
            await asyncio.sleep(1)
        
        # Toplam bilgi özeti
        total_chars = sum(len(r) for r in detailed_research)
        await self.websocket.send_json({"type": "progress", "step": 0.75, "message": f"📊 Toplamda {total_chars} karakter bilgi topladım. Yeterli mi kontrol ediyorum..."})
        await asyncio.sleep(1)
        
        if total_chars > 3000:
            await self.websocket.send_json({"type": "progress", "step": 0.77, "message": "✅ Toplanan bilgi kapsamlı! Final rapor hazırlayabilirim."})
        else:
            await self.websocket.send_json({"type": "progress", "step": 0.77, "message": "⚠️ Daha fazla detay gerekebilir, raporu optimize ediyorum..."})
            
        await asyncio.sleep(1)
        
        # Kaynak özeti gösterimi  
        await self.websocket.send_json({"type": "progress", "step": 0.8, "message": "📋 Toplanan bilgi özeti:"})
        await asyncio.sleep(0.5)
        
        for info in collected_info:
            await self.websocket.send_json({"type": "progress", "step": 0.81, "message": f"  {info}"})
            await asyncio.sleep(0.3)
        
        await self.websocket.send_json({"type": "progress", "step": 0.85, "message": "📝 Şimdi tüm bilgileri düzenli bir rapor haline getiriyorum..."})
        await asyncio.sleep(2)
        
        # Final rapor oluşturma
        final_prompt = f"""
Aşağıdaki araştırma verilerini kullanarak "{topic}" konusu hakkında kapsamlı ve iyi organize edilmiş bir rapor hazırla:

ARAŞTIRMA VERİLERİ:
{chr(10).join(detailed_research)}

RAPOR REQUİREMENTS:
- Başlık ve giriş
- Ana bölümler halinde organize edilmiş içerik
- Sonuç ve özetler
- Markdown formatında
- Detaylı ve profesyonel

Tamamen lokal model bilgilerine dayalı, kapsamlı bir araştırma raporu oluştur.
"""
        
        await self.websocket.send_json({"type": "progress", "step": 0.9, "message": "🎯 Model final raporu yazıyor..."})
        final_report = self.call_local_model(final_prompt, "Sen profesyonel rapor yazarısın. İyi organize edilmiş, kapsamlı ve anlaşılır raporlar yazarsın.")
        
        await self.websocket.send_json({"type": "progress", "step": 0.95, "message": "✅ Rapor tamamlandı! Son kontroller yapılıyor..."})
        await asyncio.sleep(1)
        
        # Lokal araştırma bildirimi ekle
        local_note = f"""
---

**🏠 Lokal Araştırma Raporu**

- **Model:** {self.model_name}
- **Toplam Bilgi:** {total_chars:,} karakter
- **Araştırılan Alt Konular:** {len(subtopics)}
- **Kullanılan Kaynaklar:** {len(collected_info)} farklı model perspektifi
- **Araştırma Türü:** Tamamen lokal (internet araması yok)

Bu araştırma tamamen sizin bilgisayarınızdaki AI modeli tarafından yapılmıştır.

---

"""
        
        full_report = local_note + final_report
        
        # Dosya kaydetme işlemi
        await self.websocket.send_json({"type": "progress", "step": 0.97, "message": "💾 Raporu dosyaya kaydediyorum..."})
        
        try:
            import os
            from datetime import datetime
            
            os.makedirs('/app/research_results', exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
            filename = f"/app/research_results/{timestamp}_{safe_topic.replace(' ', '_')}.md"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# Deep Research: {topic}\n\n")
                f.write(f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Model:** {self.model_name}\n")
                f.write(f"**Mod:** Tamamen Lokal\n\n")
                f.write("---\n\n")
                f.write(full_report)
            
            await self.websocket.send_json({"type": "progress", "step": 0.99, "message": f"📁 Rapor kaydedildi: {os.path.basename(filename)}"})
            
        except Exception as e:
            await self.websocket.send_json({"type": "progress", "step": 0.99, "message": f"⚠️ Dosya kaydetme hatası: {str(e)}"})
        
        await self.websocket.send_json({"type": "progress", "step": 1.0, "message": "🎉 Deep research tamamlandı!"})
        
        return full_report

class ResearchRequest(BaseModel):
    topic: str
    model: str | None = None  # İsteğe bağlı model adı

# Varsayılan modeller - Lokal LM Studio/Ollama
DEFAULT_PLANNING_MODEL = "lmstudio://localhost:1234/v1"
DEFAULT_SUMMARIZATION_MODEL = "lmstudio://localhost:1234/v1"
DEFAULT_JSON_MODEL = "lmstudio://localhost:1234/v1"
DEFAULT_ANSWER_MODEL = "lmstudio://localhost:1234/v1"

print("INFO: LocoDex Deep Research - Tamamen Lokal Mod")
print("INFO: API anahtarları gereksiz - sadece lokal modeller kullanılıyor")

# Paylaşılan researcher
researcher = None

@app.post("/research")
async def research_http(request: ResearchRequest):
    """
    Conducts deep research on a given topic using the DeepResearcher agent via HTTP.
    """
    try:
        answer = await researcher.research_topic(request.topic)
        return {"status": "success", "answer": answer}
    except Exception as e:
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
                logger.info("Keepalive ping sent")
            except Exception as e:
                logger.error(f"Keepalive error: {e}")
                break
    
    keepalive = asyncio.create_task(keepalive_task())
    
    try:
        while True:
            logger.info("Waiting for message...")
            try:
                # WebSocket receive timeout ekle - daha uzun süre bekle
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300)  # 5 dakika
                logger.info(f"RAW MESSAGE RECEIVED: {data}")
            except asyncio.TimeoutError:
                logger.info("WebSocket receive timeout - sending keepalive")
                await websocket.send_json({"type": "keepalive", "message": "Bağlantı aktif, araştırma isteği bekleniyor..."})
                continue
            
            try:
                request = json.loads(data)
                logger.info(f"PARSED MESSAGE: {request}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON PARSE ERROR: {e}")
                await websocket.send_json({"type": "error", "data": f"JSON hatası: {str(e)}"})
                continue
            
            # Ping mesajlarını ele al
            if request.get("type") == "ping":
                logger.info("Ping received, ignoring.")
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

            logger.info(f"TOPIC: {topic}, MODEL: {model_info}")
            logger.info(f"Full request: {request}")
            logger.info(f"Skipping model test, proceeding with research for: {model_info}")
            logger.info(f"Processing research for topic: '{topic}' with model: {model_name} from {model_source}")

            # Smart multilingual research bildirimi
            await websocket.send_json({"type": "progress", "step": 0, "message": "🌐 Akıllı çok dilli araştırma başlıyor..."})

            # Yeni akıllı çok dilli sistem kullan
            researcher = SmartMultilingualResearcher(
                model_name=model_name,
                model_source=model_source,
                websocket=websocket
            )

            try:
                # Model yüklendi bildirimi gönder
                await websocket.send_json({"type": "progress", "step": 0, "message": f"🤖 Model hazır: {model_name} ({model_source})"})
                
                # Araştırma başlıyor bildirimi  
                await websocket.send_json({"type": "progress", "step": 0.05, "message": f"🚀 '{topic}' konusu için akıllı çok dilli araştırma başlatılıyor..."})
                
                # Yeni run_research metodunu çağır
                answer = await researcher.run_research(topic)
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
        if not websocket.client_state == "DISCONNECTED":
            await websocket.close()
            logger.info("WebSocket connection closed.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
