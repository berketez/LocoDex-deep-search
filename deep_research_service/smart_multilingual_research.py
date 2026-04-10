import asyncio
import aiohttp
import json
from datetime import datetime
import os
import logging
import re
from typing import List, Dict, Any
import time

from utils.rate_limiter import rate_limiter, extract_domain

logger = logging.getLogger(__name__)

class SmartMultilingualResearcher:
    """
    Akıllı çok dilli araştırma sistemi
    - Dil algılama
    - İteratif web araması
    - İçerik kalite değerlendirmesi
    - Mantıksal çıkarım
    - Kapsamlı rapor oluşturma
    """
    
    def __init__(self, model_name, model_source, websocket):
        self.model_name = model_name
        self.model_source = model_source
        self.websocket = websocket
        self.search_results = []
        self.research_data = []
        self.query_language = "auto"
        
    async def call_local_model(self, prompt, system_prompt="", max_tokens=3000):
        """Lokal modeli asenkron olarak çağırır - Ollama ve LM Studio desteği"""
        try:
            logger.info(f"call_local_model called with model_source: '{self.model_source}', model_name: '{self.model_name}'")
            import socket
            
            # Host IP'yi bul - Docker container'dan host'a erişim için
            try:
                # Docker compose network'te host.docker.internal kullan
                host_ip = socket.gethostbyname('host.docker.internal')
            except:
                # Fallback IP'ler - macOS Docker Desktop için
                try:
                    host_ip = "192.168.65.1"  # Docker Desktop default gateway
                except:
                    try:
                        host_ip = "172.17.0.1"  # Docker bridge network
                    except:
                        host_ip = "localhost"

            async with aiohttp.ClientSession() as session:
                logger.info(f"Model source comparison: '{self.model_source}' == 'Ollama' ? {self.model_source == 'Ollama'}")
                if self.model_source == "Ollama":
                    try:
                        # Model yükleniyor bildirimi
                        await self.websocket.send_json({
                            "type": "progress", 
                            "step": 0, 
                            "message": f"🔄 {self.model_name} modeli yükleniyor (ilk kullanımda zaman alabilir)..."
                        })
                        
                        ollama_url = f"http://{host_ip}:11434/api/generate"
                        ollama_payload = {
                            "model": self.model_name,
                            "prompt": f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:",
                            "stream": False,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": max_tokens
                            }
                        }
                        
                        async with session.post(ollama_url, json=ollama_payload, timeout=300) as response:
                            logger.info(f"Ollama request to {ollama_url} with payload: {ollama_payload}")
                            logger.info(f"Ollama response status: {response.status}")
                            if response.status == 200:
                                data = await response.json()
                                return data.get('response', '').strip()
                            else:
                                error_text = await response.text()
                                logger.error(f"Ollama HTTP {response.status} error: {error_text}")
                                return f"Ollama hatası: {response.status} - {error_text}"
                    except Exception as ollama_error:
                        return f"Ollama hatası: {ollama_error}"
                
                elif self.model_source == "LM Studio":
                    try:
                        lm_studio_url = f"http://{host_ip}:1234/v1/chat/completions"
                        lm_payload = {
                            "model": self.model_name,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.3,
                            "max_tokens": max_tokens,
                            "stream": False
                        }
                        
                        async with session.post(lm_studio_url, json=lm_payload, timeout=120) as response:
                            if response.status == 200:
                                data = await response.json()
                                content = data['choices'][0]['message']['content']
                                return content.strip()
                            else:
                                return f"LM Studio hatası: {response.status}"
                    except Exception as lm_error:
                        # LM Studio çalışmıyorsa Ollama'ya fallback yap
                        logger.warning(f"LM Studio erişilemez, Ollama'ya geçiliyor: {lm_error}")
                        try:
                            ollama_url = f"http://{host_ip}:11434/api/generate"
                            ollama_payload = {
                                "model": self.model_name,
                                "prompt": f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:",
                                "stream": False,
                                "options": {
                                    "temperature": 0.3,
                                    "num_predict": max_tokens
                                }
                            }
                            
                            async with session.post(ollama_url, json=ollama_payload, timeout=300) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    return data.get('response', '').strip()
                                else:
                                    return f"Hem LM Studio hem Ollama erişilemez"
                        except:
                            return f"Model bağlantı hatası: LM Studio çalışmıyor, Ollama'ya da erişilemedi"
                
                else: # Kaynak bilinmiyorsa önce LM Studio dene, sonra Ollama
                    try:
                        lm_studio_url = f"http://{host_ip}:1234/v1/chat/completions"
                        lm_payload = {
                            "model": self.model_name,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.3,
                            "max_tokens": max_tokens,
                            "stream": False
                        }
                        
                        async with session.post(lm_studio_url, json=lm_payload, timeout=120) as response:
                            if response.status == 200:
                                data = await response.json()
                                content = data['choices'][0]['message']['content']
                                return content.strip()
                    except:
                        pass
                    
                    try:
                        ollama_url = f"http://{host_ip}:11434/api/generate"
                        ollama_payload = {
                            "model": self.model_name,
                            "prompt": f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:",
                            "stream": False,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": max_tokens
                            }
                        }
                        
                        async with session.post(ollama_url, json=ollama_payload, timeout=300) as response:
                            if response.status == 200:
                                data = await response.json()
                                return data.get('response', '').strip()
                    except:
                        pass
                
                return "Model bağlantı hatası: Hem LM Studio hem Ollama erişilemez"

        except Exception as e:
            return f"Model bağlantı hatası: {str(e)}"

    async def detect_language(self, text):
        """Metin dilini algılar ve araştırma stratejisi belirler"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.05, 
                "message": "🔍 Soru dilini analiz ediyorum..."
            })
            
            # Basit Türkçe karakter kontrolü
            turkish_chars = re.search(r'[çğıöşüÇĞIİÖŞÜ]', text)
            turkish_words = ['nedir', 'nasıl', 'ne', 'hangi', 'kim', 'nerede', 'niçin', 'neden', 'hakkında']
            
            has_turkish = turkish_chars is not None or any(word in text.lower() for word in turkish_words)
            
            if has_turkish:
                self.query_language = "tr"
                await self.websocket.send_json({
                    "type": "progress", 
                    "step": 0.07, 
                    "message": "🇹🇷 Türkçe soru tespit edildi - çok dilli araştırma stratejisi hazırlanıyor"
                })
                return "turkish"
            else:
                self.query_language = "en"
                await self.websocket.send_json({
                    "type": "progress", 
                    "step": 0.07, 
                    "message": "🇺🇸 İngilizce soru tespit edildi - global araştırma stratejisi hazırlanıyor"
                })
                return "english"
                
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return "english"

    async def generate_smart_queries(self, topic, language):
        """Akıllı arama sorguları oluşturur"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.1, 
                "message": "🧠 Akıllı arama stratejisi geliştiriliyor..."
            })
            
            current_date = datetime.now().strftime("%d %B %Y")
            
            if language == "turkish":
                prompt = f"""
Bu konuyla ilgili 4 farklı arama sorgusu oluştur:

Konu: {topic}
Tarih: {current_date}

Sorgular şu açılardan olmalı:
1. Temel tanım ve kavram (Türkçe)
2. Güncel gelişmeler ve haberler (Türkçe)
3. Global perspektif (İngilizce)
4. Teknik/bilimsel yaklaşım (İngilizce)

Her sorguyu ayrı satırda sadece sorgu olarak yaz, açıklama ekleme.
"""
            else:
                prompt = f"""
Generate 4 different search queries for this topic:

Topic: {topic}
Date: {current_date}

Queries should cover:
1. Basic definition and concept
2. Recent developments and news
3. Technical/scientific approach
4. Practical applications

Write only the queries, one per line, no explanations.
"""
            
            queries_text = await self.call_local_model(
                prompt, 
                "Sen araştırma uzmanısın. Etkili web arama sorguları oluşturursun."
            )
            
            # Sorguları parse et
            search_queries = []
            lines = queries_text.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 5:
                    # Numaraları ve fazla işaretleri temizle
                    query = re.sub(r'^\d+[\.\-\)\s]*', '', line).strip()
                    if query and query not in search_queries:
                        search_queries.append(query)
            
            # Fallback sorguları
            if not search_queries:
                if language == "turkish":
                    search_queries = [
                        topic,
                        f"{topic} nedir",
                        f"{topic} güncel gelişmeler",
                        f"{topic} english"
                    ]
                else:
                    search_queries = [
                        topic,
                        f"what is {topic}",
                        f"{topic} latest developments",
                        f"{topic} applications"
                    ]
            
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.12, 
                "message": f"📝 {len(search_queries)} farklı arama sorgusu hazırlandı"
            })
            
            return search_queries[:4]  # En fazla 4 sorgu
            
        except Exception as e:
            logger.error(f"Query generation error: {e}")
            return [topic]

    async def search_web_advanced(self, query, max_results=5):
        """Gelişmiş web araması - Google ve DuckDuckGo hibrit"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.2, 
                "message": f"🌐 Web'de araştırma: '{query[:50]}...'"
            })
            
            import asyncio
            import concurrent.futures
            
            def sync_search():
                results = []
                
                # Önce Google'ı dene
                try:
                    from googlesearch import search as google_search
                    import requests
                    from bs4 import BeautifulSoup
                    
                    google_urls = list(google_search(query, num_results=max_results, lang='en'))
                    
                    for url in google_urls[:max_results]:
                        try:
                            response = requests.get(url, timeout=5, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            soup = BeautifulSoup(response.text, 'html.parser')
                            title = soup.find('title')
                            title_text = title.text if title else url
                            
                            meta_desc = soup.find('meta', attrs={'name': 'description'})
                            description = meta_desc.get('content', '') if meta_desc else ''
                            
                            results.append({
                                'title': title_text,
                                'body': description,
                                'href': url,
                                'source': 'Google'
                            })
                        except:
                            continue
                            
                except ImportError:
                    pass
                
                # Google yetersizse DuckDuckGo ekle
                if len(results) < max_results:
                    try:
                        from duckduckgo_search import DDGS
                        ddgs = DDGS()
                        ddg_results = list(ddgs.text(query, max_results=max_results, region='us-en'))
                        
                        for result in ddg_results:
                            if len(results) >= max_results:
                                break
                                
                            title = result.get('title', '').lower()
                            body = result.get('body', '').lower()
                            url = result.get('href', '').lower()
                            
                            # Çince karakterleri filtrele
                            chinese_pattern = r'[\u4e00-\u9fff]'
                            if (re.search(chinese_pattern, title) or 
                                re.search(chinese_pattern, body) or
                                any(site in url for site in ['zhihu.com', 'baidu.com', 'weibo.com'])):
                                continue
                            
                            result['source'] = 'DuckDuckGo'
                            results.append(result)
                    except:
                        pass
                
                return results
            
            # Sync search'ü thread pool'da çalıştır
            with concurrent.futures.ThreadPoolExecutor() as executor:
                search_results = await asyncio.get_event_loop().run_in_executor(
                    executor, sync_search
                )
            
            return search_results
            
        except Exception as e:
            logger.error(f"Advanced web search error: {e}")
            return []

    async def extract_and_analyze_content(self, url, title):
        """URL'den içerik çeker ve AI ile analiz eder"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.3, 
                "message": f"📖 İçerik analiz ediliyor: {title[:40]}..."
            })
            
            async with aiohttp.ClientSession() as session:
                await rate_limiter.wait(extract_domain(url))
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # HTML temizleme
                        try:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Script ve style etiketlerini kaldır
                            for script in soup(["script", "style", "nav", "footer", "header"]):
                                script.decompose()
                            
                            # Text'i al
                            text = soup.get_text()
                            
                            # Satırları temizle
                            lines = (line.strip() for line in text.splitlines())
                            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                            clean_text = ' '.join(chunk for chunk in chunks if chunk)
                            
                            return clean_text[:4000]  # İlk 4000 karakter
                            
                        except ImportError:
                            # BeautifulSoup yoksa basit text extract
                            import re
                            text = re.sub('<[^<]+?>', '', html)
                            return text[:4000]
            
        except Exception as e:
            logger.error(f"Content extraction error for {url}: {e}")
            return ""

    async def evaluate_source_reliability(self, source_data):
        """Kaynak güvenilirliğini AI ile değerlendirir"""
        try:
            prompt = f"""
Bu web kaynağının güvenilirliğini 1-10 arasında puanla:

Başlık: {source_data.get('title', '')}
URL: {source_data.get('href', '')}
İçerik: {source_data.get('content', '')[:500]}...

Değerlendirme kriterleri:
- Kaynak otoritesi (domain güvenilirliği)
- İçerik kalitesi ve derinliği
- Güncellik
- Objektiflik

Sadece puanı ver (1-10) ve kısa gerekçe.
Format: "Puan: X/10 - Gerekçe"
"""
            
            evaluation = await self.call_local_model(
                prompt,
                "Sen kaynak güvenilirlik uzmanısın. Web kaynaklarını objektif değerlendirirsin.",
                max_tokens=200
            )
            
            # Puanı çıkar
            score_match = re.search(r'(\d+)/10', evaluation)
            score = int(score_match.group(1)) if score_match else 5
            
            return {
                'score': score,
                'evaluation': evaluation,
                'reliable': score >= 6
            }
            
        except Exception as e:
            logger.error(f"Source evaluation error: {e}")
            return {'score': 5, 'evaluation': 'Değerlendirilemedi', 'reliable': True}

    async def iterative_research_analysis(self, topic, research_data):
        """İteratif araştırma analizi - eksik alanları tespit eder"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.7, 
                "message": "🔄 Araştırma eksikliklerini tespit ediyorum..."
            })
            
            # Mevcut araştırma verilerini özetle
            current_summary = "\n".join([
                f"- {item['source']}: {item['analysis'][:100]}..."
                for item in research_data[:5]
            ])
            
            prompt = f"""
Bu konudaki mevcut araştırma verilerini analiz et ve eksik alanları tespit et:

Konu: {topic}

Mevcut veriler:
{current_summary}

Eksik kalan önemli alanları listele:
1. Hangi konular eksik?
2. Hangi bakış açıları kayıp?
3. Güncel gelişmeler var mı?

Sadece en önemli 2-3 eksik alanı belirt.
"""
            
            gap_analysis = await self.call_local_model(
                prompt,
                "Sen araştırma kalite kontrol uzmanısın. Araştırmalardaki eksikleri tespit edersin.",
                max_tokens=500
            )
            
            # Eksik alanları parse et
            gaps = []
            lines = gap_analysis.split('\n')
            for line in lines:
                line = line.strip()
                if line and ('eksik' in line.lower() or 'kayıp' in line.lower() or 'yok' in line.lower()):
                    gaps.append(line)
            
            return gaps[:3]  # En fazla 3 eksik alan
            
        except Exception as e:
            logger.error(f"Gap analysis error: {e}")
            return []

    async def run_research(self, topic):
        """Ana araştırma fonksiyonu - tüm süreci yönetir"""
        try:
            start_time = time.time()
            
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.01, 
                "message": f"🚀 '{topic}' için akıllı çok dilli araştırma başlıyor..."
            })
            
            # 1. Dil algılama
            language = await self.detect_language(topic)
            
            # 2. Akıllı sorgu oluşturma
            queries = await self.generate_smart_queries(topic, language)
            
            # 3. Web araştırması
            all_results = []
            for i, query in enumerate(queries):
                await self.websocket.send_json({
                    "type": "progress", 
                    "step": 0.15 + (i * 0.15), 
                    "message": f"🔍 Arama {i+1}/{len(queries)}: {query[:50]}..."
                })
                
                results = await self.search_web_advanced(query, max_results=4)
                all_results.extend(results)
                
                await asyncio.sleep(1)  # Rate limiting
            
            # 4. İçerik analizi
            research_data = []
            for i, result in enumerate(all_results[:10]):  # İlk 10 sonuç
                await self.websocket.send_json({
                    "type": "progress", 
                    "step": 0.5 + (i * 0.03), 
                    "message": f"📊 Kaynak analizi: {result['title'][:30]}..."
                })
                
                # İçerik çek
                content = await self.extract_and_analyze_content(result['href'], result['title'])
                result['content'] = content
                
                # Güvenilirlik değerlendir
                reliability = await self.evaluate_source_reliability(result)
                result['reliability'] = reliability
                
                # Sadece güvenilir kaynakları al
                if reliability['reliable'] and content:
                    analysis_prompt = f"""
Bu web kaynağındaki bilgileri '{topic}' konusu için özetle:

Kaynak: {result['title']}
İçerik: {content[:2000]}

Sadece konuyla ilgili önemli bilgileri özetle.
"""
                    
                    analysis = await self.call_local_model(
                        analysis_prompt,
                        "Sen araştırma analistisin. Web kaynaklarını özetlersin.",
                        max_tokens=800
                    )
                    
                    if analysis and "hatası" not in analysis.lower():
                        research_data.append({
                            'source': result['title'],
                            'url': result['href'],
                            'analysis': analysis,
                            'reliability_score': reliability['score'],
                            'search_source': result.get('source', 'Unknown')
                        })
            
            # 5. Eksiklik analizi (opsiyonel)
            gaps = await self.iterative_research_analysis(topic, research_data)
            
            # 6. Final rapor
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.9, 
                "message": "📝 Kapsamlı araştırma raporu hazırlanıyor..."
            })
            
            report = await self.generate_comprehensive_report(topic, research_data, language, gaps)
            
            # 7. Performans metrikleri
            end_time = time.time()
            duration = end_time - start_time
            
            await self.websocket.send_json({
                "type": "progress", 
                "step": 1.0, 
                "message": f"✅ Araştırma tamamlandı! ({duration:.1f}s, {len(research_data)} kaynak)"
            })
            
            return report
            
        except Exception as e:
            logger.error(f"Research process error: {e}")
            return f"Araştırma hatası: {str(e)}"

    async def generate_comprehensive_report(self, topic, research_data, language, gaps):
        """Kapsamlı araştırma raporu oluşturur"""
        try:
            # Araştırma verilerini birleştir
            combined_research = "\n\n".join([
                f"**Kaynak: {item['source']}** (Güvenilirlik: {item['reliability_score']}/10)\nURL: {item['url']}\nAraştırma Motoru: {item['search_source']}\n{item['analysis']}"
                for item in research_data
            ])
            
            # Eksiklik bilgisi
            gaps_text = "\n".join([f"- {gap}" for gap in gaps]) if gaps else "Kapsamlı araştırma tamamlandı."
            
            current_date = datetime.now().strftime("%d %B %Y")
            
            if language == "turkish":
                final_prompt = f"""
Aşağıdaki araştırma sonuçlarını kullanarak '{topic}' konusu hakkında Türkçe kapsamlı bir rapor hazırla:

ARAŞTIRMA VERİLERİ:
{combined_research}

EKSİK ALANLAR:
{gaps_text}

RAPOR İHTİYAÇLARI:
- Tamamen Türkçe yazılmış olması
- Net giriş ve özet
- Ana bulgular ve önemli gelişmeler
- Kaynaklara dayalı detaylı analiz
- Güncel durum değerlendirmesi
- Sonuç ve gelecek öngörüleri
- Markdown formatında düzenli yapı

Özellikle {current_date} tarihi itibariyle güncel ve bilimsel bir rapor oluştur.
"""
            else:
                final_prompt = f"""
Create a comprehensive English report about '{topic}' using the following research data:

RESEARCH DATA:
{combined_research}

IDENTIFIED GAPS:
{gaps_text}

REPORT REQUIREMENTS:
- Professional English writing
- Clear introduction and summary
- Key findings and developments
- Source-based detailed analysis
- Current status assessment
- Conclusions and future outlook
- Well-structured Markdown format

Focus on current information as of {current_date}.
"""
            
            final_report = await self.call_local_model(
                final_prompt,
                "Sen uzman araştırmacısısın. Web araştırması sonuçlarından kapsamlı, profesyonel raporlar yazarsın.",
                max_tokens=5000
            )
            
            # Rapor başlığı ve meta bilgileri
            header = f"""# Akıllı Çok Dilli Araştırma: {topic}

**Araştırma Tarihi:** {datetime.now().strftime('%d %B %Y, %H:%M')}
**Araştırma Türü:** Akıllı Çok Dilli Web Araştırması
**Kullanılan Model:** {self.model_name} ({self.model_source})
**Toplam Kaynak:** {len(research_data)} güvenilir web kaynağı
**Araştırma Dili:** {language.title()}
**Arama Motorları:** Google, DuckDuckGo

---

"""
            
            # Kaynak listesi
            source_list = "\n".join([
                f"- [{item['source']}]({item['url']}) - Güvenilirlik: {item['reliability_score']}/10 ({item['search_source']})"
                for item in research_data
            ])
            
            full_report = header + final_report + f"\n\n## 📚 Kaynaklar\n\n{source_list}"
            
            # Dosya kaydetme
            await self.save_research_report(topic, full_report)
            
            return full_report
            
        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return f"Rapor oluşturma hatası: {str(e)}"

    async def save_research_report(self, topic, report):
        """Araştırma raporunu dosyaya kaydeder"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.95, 
                "message": "💾 Rapor kaydediliyor..."
            })
            
            import os
            from pathlib import Path
            
            # Masaüstü yolunu bul
            home = Path.home()
            desktop = home / "Desktop"
            
            # Dosya adı oluştur
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
            filename = f"{timestamp}_{safe_topic.replace(' ', '_')}_smart_research.md"
            
            # Masaüstüne kaydet
            filepath = desktop / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.98, 
                "message": f"✅ Rapor masaüstüne kaydedildi: {filename}"
            })
            
        except Exception as e:
            logger.error(f"Report save error: {e}")
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.98, 
                "message": f"⚠️ Dosya kaydetme hatası: {str(e)}"
            })