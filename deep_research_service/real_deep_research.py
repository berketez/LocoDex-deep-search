import asyncio
import aiohttp
import json
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class RealDeepResearcher:
    """Gerçek web araması yapan deep research sistemi"""
    
    def __init__(self, model_name, model_source, websocket):
        self.model_name = model_name
        self.model_source = model_source
        self.websocket = websocket
        self.search_results = []
        
        # Güvenilir kaynak listeleri
        self.trusted_domains = {
            'high': [
                'arxiv.org', 'nature.com', 'science.org', 'pubmed.ncbi.nlm.nih.gov',
                'ieee.org', 'acm.org', 'academic.oup.com', 'springer.com',
                'cambridge.org', 'mit.edu', 'stanford.edu', 'harvard.edu',
                'openai.com', 'deepmind.com', 'anthropic.com', 'microsoft.com',
                'google.com', 'apple.com', 'nvidia.com', 'meta.com',
                'techcrunch.com', 'arstechnica.com', 'wired.com', 'zdnet.com',
                'reuters.com', 'bbc.com', 'cnn.com', 'nytimes.com',
                'github.com', 'stackoverflow.com', 'medium.com', 'substack.com',
                'huggingface.co', 'kaggle.com', 'paperswithcode.com',
                'who.int', 'cdc.gov', 'nasa.gov', 'fda.gov', 'sec.gov'
            ],
            'medium': [
                'wikipedia.org', 'reddit.com', 'quora.com', 'forbes.com',
                'businessinsider.com', 'theverge.com', 'engadget.com',
                'venturebeat.com', 'techrepublic.com', 'pcmag.com',
                'blog.google.com', 'engineering.fb.com', 'blogs.microsoft.com',
                'aws.amazon.com', 'cloud.google.com', 'azure.microsoft.com'
            ],
            'low': [
                'blog.', 'wordpress.com', 'blogspot.com', 'tumblr.com',
                'yahoo.com', 'answers.com', 'ehow.com'
            ]
        }
        
        # Güvensiz/spam domain'ler
        self.untrusted_domains = [
            'clickbait.com', 'spam.com', 'fake-news.com', 'ads.com',
            'affiliate.com', 'referral.com', 'promotion.com'
        ]
    
    async def evaluate_source_reliability(self, url, title, content_sample, topic):
        """Model ile kaynak güvenilirliği değerlendirir"""
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            reliability_prompt = f"""
Bu web kaynağının güvenilirliğini değerlendir:

URL: {url}
Başlık: {title}
İçerik Örneği: {content_sample[:500]}
Araştırma Konusu: {topic}
Bugünün Tarihi: {current_date}

ÖZEL DEĞERLENDİRME KRİTERLERİ:

1. **Konu Türü Analizi (ÇOK ÖNEMLİ):**
   - Önce konuyu kategorize et:
     * Teknoloji/AI: Hızlı değişen, güncellik kritik
     * Tarih/Psikoloji: Yavaş değişen, akademik kaynaklar öncelikli
     * Siyaset: Tarafsızlık kritik, birden fazla bakış açısı gerekli
     * İş Hayatı: Güncel trendler + kanıtlanmış metodlar
     * Bilim: Peer-reviewed makaleler öncelikli
     * Genel Bilgi: Orta hızda değişen

2. **Tarih ve Teknoloji Olgunluk Analizi (ÇOK ÖNEMLİ):**
   - İçerikteki tarih bilgilerini tespit et
   - Teknoloji türünü belirle ve değişim hızını değerlendir:
     * Hızlı değişen teknolojiler (AI modelleri, mobil işlemciler, sosyal medya): 6 ay öncesi = ESKİ
     * Orta hızda değişen teknolojiler (web frameworkleri, bulut servisleri): 2 yıl öncesi = ESKİ
     * Yavaş değişen teknolojiler (veritabanları, networking, matematik): 5 yıl öncesi = HALA GEÇERLİ
     * Çok yavaş değişen teknolojiler (programlama dilleri, işletim sistemi çekirdekleri): 10 yıl öncesi = HALA GEÇERLİ
     * Bilimsel araştırma: 5 yıl öncesi = HALA GEÇERLİ  
     * Genel bilgi: 2 yıl öncesi = ESKİ

3. **Kaynak Kalitesi ve Tarafsızlık:**
   - Domain güvenilirliği
   - İçerik objektifliği vs subjektifliği
   - Spam/clickbait belirtileri
   - Siyasi/ideolojik önyargı kontrol et
   - Birden fazla bakış açısı sunuyor mu?
   - Kanıt ve referans kalitesi

4. **Konu-Spesifik Kriterler:**
   - Tarih/Psikoloji: Akademik kaynak mı? Peer-reviewed mı?
   - Siyaset: Tarafsız mı? Farklı görüşleri de sunuyor mu?
   - İş Hayatı: Pratik deneyim var mı? Gerçek vaka çalışmaları var mı?
   - Bilim: Bilimsel yöntem kullanılmış mı? Veriler doğrulanabilir mi?

5. **Konu Uygunluğu:**
   - İçerik konuyla ne kadar alakalı?
   - Güncel bilgiler içeriyor mu?
   - Derinlemesine analiz var mı?

SADECE BU FORMATTA CEVAP VER:
Güvenilirlik: [0-100 arası skor]
Tarih: [içeriğin ne zaman yazıldığını tahmin et]
Konu_Türü: [teknoloji/tarih/psikoloji/siyaset/iş_hayatı/bilim/genel]
Tarafsızlık: [tarafsız/önyargılı/belirsiz]
Sebep: [tarih + konu türü + tarafsızlık + kalite değerlendirmesi]
"""
            
            response = await self.call_local_model(
                reliability_prompt,
                "Sen kaynak güvenilirliği uzmanısın. Web sitelerinin güvenilirliğini objektif olarak değerlendirirsin.",
                max_tokens=200
            )
            
            # Response'u parse et
            lines = response.strip().split('\n')
            reliability_score = 50  # default
            source_date = "Bilinmiyor"
            topic_type = "bilinmiyor"
            neutrality = "belirsiz"
            reason = "Değerlendirme yapılamadı"
            
            for line in lines:
                if line.startswith('Güvenilirlik:'):
                    try:
                        score_text = line.split(':')[1].strip()
                        reliability_score = int(''.join(filter(str.isdigit, score_text)))
                    except:
                        pass
                elif line.startswith('Tarih:'):
                    source_date = line.split(':', 1)[1].strip()
                elif line.startswith('Konu_Türü:'):
                    topic_type = line.split(':', 1)[1].strip()
                elif line.startswith('Tarafsızlık:'):
                    neutrality = line.split(':', 1)[1].strip()
                elif line.startswith('Sebep:'):
                    reason = line.split(':', 1)[1].strip()
            
            full_reason = f"Tarih: {source_date} | Tür: {topic_type} | Tarafsızlık: {neutrality} | {reason}"
            return reliability_score, full_reason
            
        except Exception as e:
            logger.error(f"Source reliability evaluation failed: {e}")
            return 50, "Değerlendirme hatası"
    
    async def detect_conflicting_information(self, research_data, topic):
        """Çelişkili bilgileri tespit eder"""
        try:
            if len(research_data) < 2:
                return "Yeterli kaynak yok"
            
            # İlk 5 kaynağı karşılaştır
            sources_to_compare = research_data[:5]
            
            comparison_prompt = f"""
'{topic}' konusu hakkında aşağıdaki farklı kaynaklardan gelen bilgileri karşılaştır:

{chr(10).join([f"Kaynak {i+1}: {source['source']} (Güvenilirlik: {source['reliability_score']}/100){chr(10)}{source['analysis']}{chr(10)}" for i, source in enumerate(sources_to_compare)])}

Bu kaynaklar arasında çelişkili bilgiler var mı? Özellikle dikkat et:
1. Çelişkili bilgileri belirt
2. Hangi kaynak daha güvenilir görünüyor?
3. Siyasi/ideolojik önyargı var mı?
4. Farklı bakış açıları dengeli sunuluyor mu?
5. Doğru bilgi hangisi olabilir?

SADECE BU FORMATTA CEVAP VER:
Çelişki: [Var/Yok]
Detay: [çelişkili bilgiler varsa açıklama]
Tarafsızlık: [Tüm kaynaklar tarafsız mı?]
Öneri: [en güvenilir ve tarafsız bilgi hangisi]
"""
            
            response = await self.call_local_model(
                comparison_prompt,
                "Sen fact-checking uzmanısın. Farklı kaynakların bilgilerini karşılaştırıp çelişkileri tespit edersin.",
                max_tokens=500
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Conflicting information detection failed: {e}")
            return "Karşılaştırma analizi yapılamadı"
    
    async def extract_specific_data(self, content, topic):
        """İçerikten spesifik sayısal verileri çıkarır"""
        try:
            extraction_prompt = f"""
'{topic}' konusu ile ilgili bu içerikten spesifik sayısal verileri çıkar:

İçerik: {content[:1000]}

🎯 ÇIKARILACAK VERİLER:

1. **SAYISAL VERİLER:**
   • Tüm sayıları ve birimlerini belirt (GB, TB, PB, kg, cm, $, %, yıl, adet, vb.)
   • Örnek: "11 petabayt", "100 sunucu", "2019 yılı", "$10 milyon"

2. **HESAPLAMALAR:**
   • Matematiksel işlemler varsa göster
   • Örnek: "4403 PB ÷ 11 PB = 400 kez izlenme"

3. **KARŞILAŞTIRMALAR:**
   • Artış/azalış oranları
   • Örnek: "%25 artış", "3 kat daha büyük"

SADECE BU FORMATTA CEVAP VER:
Sayısal_Veriler: [tüm sayısal veriler listesi]
Hesaplamalar: [matematik işlemler varsa]
Karşılaştırmalar: [oranlar ve trendler]
"""
            
            response = await self.call_local_model(
                extraction_prompt,
                "Sen veri çıkarma uzmanısın. Metinlerden sayısal bilgileri çıkarırsın.",
                max_tokens=300
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Specific data extraction failed: {e}")
            return "Veri çıkarma işlemi başarısız"
        
    async def call_local_model(self, prompt, system_prompt="", max_tokens=3000, thinking_process_prompt=""):
        """Lokal modeli asenkron olarak çağırır - Ollama ve LM Studio desteği"""
        try:
            logger.info(f"call_local_model called with model_source: '{self.model_source}', model_name: '{self.model_name}'")
            import socket
            
            # Docker container'dan host'a erişim için en güvenilir yöntem
            host_ip = os.environ.get('OLLAMA_HOST_IP') or socket.gethostbyname('host.docker.internal')

            async with aiohttp.ClientSession() as session:
                logger.info(f"Model source comparison: '{self.model_source}' == 'Ollama' ? {self.model_source == 'Ollama'}")
                if self.model_source == "Ollama":
                    try:
                        
                        ollama_url = f"http://{host_ip}:11434/api/generate"
                        ollama_payload = {
                            "model": self.model_name,
                            "prompt": f"{thinking_process_prompt}\n\nUser: {prompt}\n\nAssistant:",
                            "system": system_prompt,
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
                            "prompt": f"{thinking_process_prompt}\n\nUser: {prompt}\n\nAssistant:",
                            "system": system_prompt,
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

    async def search_web(self, query, max_results=12):
        """Web araması yapar - Google öncelikli, Tavily fallback"""
        try:
            # Google search ile başla
            try:
                import asyncio
                import concurrent.futures
                from googlesearch import search
                
                def sync_search():
                    return list(search(query, num_results=max_results, lang=self.detect_language(query)))
                
                # Run sync search in thread pool
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    search_results = await asyncio.get_event_loop().run_in_executor(
                        executor, sync_search
                    )
                
                results = []
                for i, url in enumerate(search_results):
                    if i >= max_results:
                        break
                        
                    results.append({
                        'title': url, # Google search does not provide titles directly
                        'body': '', # Google search does not provide snippets directly
                        'url': url,
                        'source': 'Google'
                    })
                
                if results:
                    return results
                    
            except Exception as google_error:
                logger.warning(f"Google search error, falling back to Tavily: {google_error}")
            
            # Tavily search fallback
            try:
                from src.libs.utils.tavily_search import atavily_search_results
                
                search_data = await atavily_search_results(
                    query=query, 
                    max_results=max_results, 
                    include_raw=True
                )
                
                results = []
                for i, result in enumerate(search_data.results):
                    if i >= max_results:
                        break
                        
                    results.append({
                        'title': result.title,
                        'body': result.content,
                        'url': result.link,
                        'source': 'Tavily (Fallback)'
                    })
                
                return results
                    
            except Exception as tavily_error:
                logger.error(f"Both Google and Tavily search failed: {tavily_error}")
            
            return []
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []

    async def extract_content_from_url(self, url, title):
        """URL'den içerik çeker"""
        try:
            await self.websocket.send_json({
                "type": "progress", 
                "step": 0.3, 
                "message": f"📖 {title[:50]}... sayfası okunuyor"
            })
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Basit HTML temizleme
                        try:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, 'html.parser')
                        except ImportError:
                            # BeautifulSoup yoksa basit text extract
                            import re
                            # HTML taglerini kaldır
                            text = re.sub('<[^<]+?>', '', html)
                            return text[:3000]
                        
                        # Script ve style etiketlerini kaldır
                        for script in soup(["script", "style"]):
                            script.decompose()
                        
                        # Text'i al
                        text = soup.get_text()
                        
                        # Satırları temizle
                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = ' '.join(chunk for chunk in chunks if chunk)
                        
                        # İlk 3000 karakteri al
                        return text[:3000]
            
        except Exception as e:
            logger.error(f"Content extraction error for {url}: {e}")
            return ""
        
        return ""

    async def check_relevance(self, topic, search_result):
        """Arama sonucunun konuyla ilgili olup olmadığını kontrol eder"""
        try:
            title = search_result.get('title', '')
            snippet = search_result.get('snippet', '')
            
            relevance_prompt = f"""
ARAŞTIRMA KONUSU: {topic}

ARAMA SONUCU:
Başlık: {title}
İçerik: {snippet}

Bu arama sonucu, araştırma konusuyla ilgili mi?

SADECE "EVET" veya "HAYIR" cevabı ver.
Eğer içerik konuyla alakalı ise EVET, alakasız ise HAYIR.
"""
            
            relevance = await self.call_local_model(relevance_prompt, "Sen içerik analiz uzmanısın.")
            return "EVET" in relevance.upper()
            
        except Exception as e:
            logger.error(f"Relevance check error: {e}")
            return True  # Hata durumunda kabul et

    def detect_language(self, text):
        """Metindeki dili algılar"""
        # Türkçe karakterler
        turkish_chars = ['ç', 'ğ', 'ı', 'ş', 'ü', 'ö', 'Ç', 'Ğ', 'İ', 'Ş', 'Ü', 'Ö']
        turkish_words = ['ve', 'ile', 'bir', 'bu', 'şu', 'o', 'nedir', 'nasıl', 'ne', 'hangi', 'en', 'iyi', 'güncel']
        
        # Fransızca karakterler ve kelimeler
        french_chars = ['é', 'è', 'ê', 'ë', 'à', 'â', 'ä', 'ç', 'ù', 'û', 'ü', 'ô', 'ö', 'î', 'ï', 'ÿ']
        french_words = ['le', 'la', 'les', 'un', 'une', 'de', 'du', 'des', 'et', 'ou', 'est', 'ce', 'que', 'qui', 'comment', 'quel', 'quelle']
        
        # Almanca karakterler ve kelimeler
        german_chars = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
        german_words = ['der', 'die', 'das', 'und', 'oder', 'ist', 'was', 'wie', 'welche', 'beste', 'aktuelle']
        
        text_lower = text.lower()
        
        # Karakter kontrolü
        if any(char in text for char in turkish_chars):
            return 'tr'
        elif any(char in text for char in french_chars):
            return 'fr'
        elif any(char in text for char in german_chars):
            return 'de'
        
        # Kelime kontrolü
        turkish_score = sum(1 for word in turkish_words if word in text_lower)
        french_score = sum(1 for word in french_words if word in text_lower)
        german_score = sum(1 for word in german_words if word in text_lower)
        
        if turkish_score > 0:
            return 'tr'
        elif french_score > 0:
            return 'fr'
        elif german_score > 0:
            return 'de'
        
        return 'en'  # Varsayılan İngilizce

    async def research_topic(self, topic):
        """Gerçek deep research yapar"""
        
        await self.websocket.send_json({
            "type": "progress", 
            "step": 0.05, 
            "message": f"🚀 '{topic}' konusu için deep research başlıyor..."
        })
        
        # 1. Dil algılama
        detected_lang = self.detect_language(topic)
        lang_names = {'tr': 'Türkçe', 'en': 'İngilizce', 'fr': 'Fransızca', 'de': 'Almanca'}
        
        await self.websocket.send_json({
            "type": "progress", 
            "step": 0.08, 
            "message": f"🌐 {lang_names.get(detected_lang, 'İngilizce')} dili algılandı"
        })
        
        # 2. Konu analizi ve arama sorguları oluştur
        current_date = datetime.now().strftime("%d %B %Y")
        
        # Önce algılanan dilde arama sorguları
        primary_prompt = f"""
ARAŞTIRMA KONUSU: {topic}

BUGÜNÜN TARİHİ: {current_date}

Bu tarihe göre kendi karar ver: hangi zaman dilimindeki bilgileri aramalısın?
- Eğer 2025 yılındaysak, 2024-2025 arası bilgiler güncel
- Eğer güncel teknoloji/AI/fiyat/trend araştırması ise, son 6-12 ay önemli
- Eğer tarihi konu ise, yıl önemli değil

Bu analizi yaptıktan sonra {lang_names.get(detected_lang, 'İngilizce')} dilinde 3 farklı arama terimi ile araştır.

KONU ANALİZİ VE ARAMA STRATEJİSİ:
1. Ana konuyu doğru anla ve spesifik terimleri kullan
2. Tarihe göre uygun zaman aralığını belirle
3. Teknik detaylar için spesifik terimler kullan (örn: "petabytes", "servers", "infrastructure")
4. İstatistik ve rakam odaklı arama yap ("statistics", "data", "numbers")
5. Güvenilir kaynakları hedefle ("reddit", "technical interview", "official report")
6. Karşılaştırma ve değerlendirme terimleri kullan ("vs", "comparison", "analysis")
7. Her sorgu farklı açıdan yaklaşsın
8. ÖZEL: AI/teknoloji konularında "January 2025", "2025 release", "latest models" gibi çok güncel terimler kullan

SADECE ARAMA TERİMLERİNİ VER:
1.
2.
3.
"""
        
        # Sonra İngilizce arama sorguları (ana dil İngilizce değilse)
        secondary_prompt = f"""
ARAŞTIRMA KONUSU: {topic}

BUGÜNÜN TARİHİ: {current_date}

Bu tarihe göre kendi karar ver ve bu konuyu İngilizce olarak 2 farklı arama terimi ile araştır.

KONU ANALİZİ VE ARAMA STRATEJİSİ:
1. Ana konuyu İngilizce karşılığı ile anla
2. Tarihe göre uygun terimleri kullan ("latest", "current", "2024", "2025" vb.)
3. Konunun özelliğine göre zaman aralığını belirle

SADECE ARAMA TERİMLERİNİ VER:
1.
2.
"""
        
        await self.websocket.send_json({
            "type": "progress", 
            "step": 0.1, 
            "message": "🧠 Araştırma stratejisi belirleniyor..."
        })
        
        # Önce ana dilde arama sorguları al
        try:
            logger.info(f"Generating primary language queries...")
            primary_queries_text = await self.call_local_model(
                primary_prompt, 
                "Sen araştırma uzmanısın. Verilen konular için etkili arama sorguları oluşturursun."
            )
            logger.info(f"Primary queries generated successfully")
        except Exception as e:
            logger.error(f"Primary query generation failed: {e}")
            primary_queries_text = "1. ana konu\n2. genel araştırma"
        
        # Ana dil İngilizce değilse, İngilizce sorgular da al
        secondary_queries_text = ""
        if detected_lang != 'en':
            try:
                logger.info(f"Generating secondary English queries...")
                secondary_queries_text = await self.call_local_model(
                    secondary_prompt, 
                    "Sen araştırma uzmanısın. Verilen konular için etkili arama sorguları oluşturursun."
                )
                logger.info(f"Secondary queries generated successfully")
            except Exception as e:
                logger.error(f"Secondary query generation failed: {e}")
                secondary_queries_text = ""
        
        # Sorguları parse et - duplikasyonları önle
        search_queries = []
        seen_queries = set()
        
        # Önce ana dil sorguları
        for line in primary_queries_text.split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-')):
                query = line.split('.', 1)[-1].strip()
                if query and query.lower() not in seen_queries and len(query) > 5:
                    search_queries.append(query)
                    seen_queries.add(query.lower())
        
        # Sonra İngilizce sorguları (varsa)
        if secondary_queries_text:
            for line in secondary_queries_text.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    query = line.split('.', 1)[-1].strip()
                    if query and query.lower() not in seen_queries and len(query) > 5:
                        search_queries.append(query)
                        seen_queries.add(query.lower())
        
        # Fallback sorguları ekle
        if not search_queries:
            search_queries = [topic, f"{topic} 2025", f"latest {topic}"]
        
        # İlk 5 sorguyu kullan
        search_queries = search_queries[:5]
        
        # 2. Web araması yap
        all_search_results = []
        
        for i, query in enumerate(search_queries):
            results = await self.search_web(query, max_results=8)
            
            # Sonuçları filtrele - sadece ilgili olanları al
            filtered_results = []
            for result in results:
                if await self.check_relevance(topic, result):
                    filtered_results.append(result)
            
            all_search_results.extend(filtered_results)
            await asyncio.sleep(1)  # Rate limiting
        
        # 3. İçerikleri analiz et
        research_data = []
        
        for i, result in enumerate(all_search_results[:20]):  # İlk 20 sonuç
            # Kullanıcıya hangi siteyi incelediğini göster
            await self.websocket.send_json({
                "type": "message", 
                "message": f"{i+1}. {result['url']} - İnceleniyor..."
            })
            
            # İçerik çek
            if result['url']:
                content = await self.extract_content_from_url(result['url'], result['title'])
                result['content'] = content
                
                # Kaynak güvenilirliğini değerlendir
                reliability_score, reason = await self.evaluate_source_reliability(
                    result['url'], result['title'], content, topic
                )
                result['reliability_score'] = reliability_score
                result['reliability_reason'] = reason
            
            # Model ile analiz et
            if result.get('content') or result.get('body'):
                analysis_text = result.get('content', result.get('body', ''))
                
                analysis_prompt = f"""
Bu web kaynağındaki bilgileri analiz et ve '{topic}' konusu ile ilgili önemli bilgileri özetle:

Kaynak: {result['title']}
URL: {result['url']}

İçerik:
{analysis_text[:2000]}

🔍 SPESIFIK VERİ ÇIKARMA TALİMATLARI:

1. **SAYISAL VERİLER (MUTLAKA BELIRT):**
   • Teknik: GB, TB, PB, MB, KB, CPU, RAM, sunucu sayısı, bant genişliği
   • Fiziksel: kg, g, cm, m, km, litre, ml, derece, watt, volt
   • Finansal: dolar, euro, lira, milyar, milyon, maliyet, bütçe
   • Zaman: yıl, ay, gün, saat, dakika, saniye
   • Performans: fps, bit rate, hız, frekans, oran, yüzde

2. **HESAPLAMALAR ve KARŞILAŞTIRMALAR:**
   • Matematik işlemler yap (örn: 4403 PB ÷ 11 PB = 400 kez)
   • Oranları belirt (örn: %25 artış, 3 kat daha büyük)
   • Trend analizi (artış/azalış, zaman içindeki değişim)

3. **KAYNAK ve TARİH BİLGİSİ:**
   • Bu veri ne zaman yayınlandı?
   • Güncel mi yoksa eski mi?
   • Resmi kaynak mı yoksa tahmin mi?

4. **ELEŞTİREL ANALİZ:**
   • Hangi varsayımlarla sonuca ulaşıldı?
   • Sınırlamalar ve belirsizlikler neler?
   • Farklı kaynaklarla tutarlı mı?

ÖRNEK FORMAT:
"Kaynak X'e göre, 2019'da 11 PB depolama kapasitesi vardı. 2024 için, veri transferindeki artışa dayanarak (4403 PB'dan 5500 PB'ye), yaklaşık 13.75 PB tahmin ediliyor. Ancak bu hesaplama izlenme oranının sabit kaldığını varsayar."

Sadece konuyla ilgili bilgileri özetle, kaynak adını da belirt.
"""
                
                analysis = await self.call_local_model(
                    analysis_prompt,
                    "Sen araştırma analistisin. Web kaynaklarındaki bilgileri özetlersin.",
                    max_tokens=500
                )
                
                # Spesifik veri çıkarma
                specific_data = await self.extract_specific_data(analysis_text, topic)
                
                if analysis and "hatası" not in analysis.lower():
                    research_data.append({
                        'source': result['title'],
                        'url': result['url'],
                        'analysis': analysis,
                        'specific_data': specific_data,
                        'reliability_score': result.get('reliability_score', 50),
                        'reliability_reason': result.get('reliability_reason', 'Bilinmiyor')
                    })
                    
                    # Kullanıcıya sonuç bulduğunu göster
                    await self.websocket.send_json({
                        "type": "message", 
                        "message": f"   ✅ Faydalı bilgi bulundu"
                    })
                else:
                    # Sonuç bulunamadı mesajı
                    await self.websocket.send_json({
                        "type": "message", 
                        "message": f"   ❌ Kullanılabilir bilgi bulunamadı"
                    })
        
        # 4. Kaynakları güvenilirlik skoruna göre sırala
        research_data.sort(key=lambda x: x['reliability_score'], reverse=True)
        
        # Düşük güvenilirlik skorlu kaynakları filtrele (30'un altı)
        filtered_research_data = [item for item in research_data if item['reliability_score'] >= 30]
        
        await self.websocket.send_json({
            "type": "message", 
            "message": f"\n📋 Toplam {len(filtered_research_data)} güvenilir kaynak bulundu"
        })
        
        await self.websocket.send_json({
            "type": "message", 
            "message": "\n🤖 Rapor hazırlanıyor...\n"
        })
        
        # Çelişkili bilgileri tespit et
        conflicting_info = await self.detect_conflicting_information(filtered_research_data, topic)
        
        # Tüm analiz sonuçlarını birleştir - güvenilirlik skoru ile
        combined_research = "\n\n".join([
            f"**Kaynak: {item['source']}** (Güvenilirlik: {item['reliability_score']}/100)\nURL: {item['url']}\nGüvenilirlik Notu: {item['reliability_reason']}\n{item['analysis']}"
            for item in filtered_research_data
        ])
        
        # Kaynak listesini de ekle
        source_list = "\n".join([
            f"- {item['source']}: {item['url']} (Güvenilirlik: {item['reliability_score']}/100)"
            for item in filtered_research_data
        ])
        
        # Eğer hiç araştırma verisi yoksa, model bilgisiyle fallback yap
        if not research_data:
            fallback_prompt = f"""
'{topic}' konusu hakkında mevcut bilgilerini kullanarak kapsamlı bir analiz yap:

- Temel tanım ve kavramlar
- Önemli özellikler ve karakteristikler
- Güncel durum ve gelişmeler
- Gelecek beklentileri
- Pratik uygulamalar

Detaylı ve bilgilendirici bir rapor hazırla.
"""
            fallback_research = await self.call_local_model(
                fallback_prompt,
                "Sen uzman araştırmacısısın. Konular hakkında kapsamlı analizler yaparsın.",
                max_tokens=2000
            )
            
            research_data.append({
                'source': 'AI Model Bilgi Tabanı',
                'url': 'N/A',
                'analysis': fallback_research
            })
            
            combined_research = f"**Kaynak: AI Model Bilgi Tabanı**\nURL: N/A\n{fallback_research}"
        
        final_prompt = f"""
Aşağıdaki araştırma sonuçlarını kullanarak '{topic}' konusu hakkında Türkçe kapsamlı bir rapor hazırla:

ARAŞTIRMA VERİLERİ:
{combined_research}

ÇELIŞKI ANALİZİ:
{conflicting_info}

KULLANILAN KAYNAKLAR:
{source_list}

DÜŞÜNME ve ANALİZ YAKLAŞIMI:
- Verileri eleştirel olarak sorgula
- Matematik hesaplamalar yap (varsa)
- Varsayımları ve sınırlamaları belirt
- Farklı kaynakları karşılaştır
- Şüpheyle yaklaş, "kesin değil" diyerek belirt
- İnsan gibi düşün ve analiz et

RAPOR İHTİYAÇLARI:
- Kullanıcının sorusuna doğrudan ve net cevap ver
- Sorulan spesifik değerleri (boyut, fiyat, tarih, teknik özellikler vb.) mutlaka belirt
- Farklı kaynaklardaki çelişkili bilgileri karşılaştır ve en doğru olanını seç
- Kaynak güvenilirlik skorlarını dikkate al (yüksek skorlu kaynakları öncelendir)
- Belirsiz veya eksik bilgiler varsa açıkça belirt
- Cevabını kanıtlarla ve araştırma verileriyle destekle
- Tamamen Türkçe yazılmış olması (hiç İngilizce kelime kullanma)
- Net giriş bölümü
- Ana bulgular ve önemli gelişmeler  
- Detaylı analiz ve değerlendirmeler
- Sonuç ve gelecek öngörüleri
- Markdown formatında düzenli yapı
- MUTLAKA rapor sonunda "Kaynaklar" bölümü ekle ve tüm kaynak URL'lerini listele

DİKKAT: Bilgi doğruluğu kritik öneme sahiptir. Eğer bir bilgi kesin değilse "tahmin ediyorum" veya "olası" gibi ifadeler kullan.
GÜVEN: Yüksek güvenilirlik skorlu kaynakları öncelendir, düşük skorlu kaynaklara şüpheyle yaklaş.
ŞEFFAFLIK: Tüm bilgilerin hangi kaynaktan geldiğini belirt, URL'leri kullanıcıya göster.

Özellikle güncel gelişmelere odaklanarak kapsamlı ve bilimsel bir rapor oluştur. Tüm metni Türkçe yaz.
"""

        thinking_process_prompt = "Kullanıcıya sadece bitmiş ve temizlenmiş raporu göster. Ön hazırlık veya düşünme sürecini rapora dahil etme."
        
        final_report = await self.call_local_model(
            final_prompt,
            "Sen uzman araştırmacısısın. Web araştırması sonuçlarından kapsamlı, profesyonel raporlar yazarsın.",
            max_tokens=4000,
            system_prompt=thinking_process_prompt
        )
        
        # 5. Kullanılan kaynakları txt dosyasına kaydet
        try:
            import os
            desktop_path = "/app/desktop"  # Docker'da host masaüstü mount edildi
            research_path = "/app/research_results"  # Container içi results
            
            os.makedirs(desktop_path, exist_ok=True)
            os.makedirs(research_path, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
            sources_filename = f"{timestamp}_{safe_topic.replace(' ', '_')}_sources.txt"
            
            # Kaynakları txt dosyasına kaydet
            desktop_sources_path = os.path.join(desktop_path, sources_filename)
            research_sources_path = os.path.join(research_path, sources_filename)
            
            sources_content = f"Araştırma Konusu: {topic}\n"
            sources_content += f"Tarih: {datetime.now().strftime('%d %B %Y, %H:%M')}\n"
            sources_content += f"Toplam Kaynak: {len(research_data)}\n"
            sources_content += f"Arama Sorguları: {search_queries}\n\n"
            sources_content += "KULLANILAN KAYNAKLAR:\n"
            sources_content += "=" * 50 + "\n\n"
            
            for i, item in enumerate(research_data, 1):
                sources_content += f"{i}. {item['source']}\n"
                sources_content += f"   URL: {item['url']}\n"
                sources_content += f"   Güvenilirlik: {item.get('reliability_score', 'N/A')}/100\n"
                sources_content += f"   Kaynak Türü: {item.get('source', 'Bilinmiyor').split('(')[0].strip()}\n\n"
            
            # Hem masaüstüne hem research_results'a kaydet
            try:
                with open(desktop_sources_path, 'w', encoding='utf-8') as f:
                    f.write(sources_content)
            except Exception as e:
                logger.error(f"Desktop sources save error: {e}")
            
            try:
                with open(research_sources_path, 'w', encoding='utf-8') as f:
                    f.write(sources_content)
            except Exception as e:
                logger.error(f"Research sources save error: {e}")
            
        except Exception as e:
            logger.error(f"Sources file save error: {e}")
            
        # 6. Dosya kaydet (rapor)
        try:
            filename = f"{timestamp}_{safe_topic.replace(' ', '_')}_deep_research.md"
            
            # Hem masaüstüne hem research_results'a kaydet
            desktop_filepath = os.path.join(desktop_path, filename)
            research_filepath = os.path.join(research_path, filename)
            
            report_header = f"""# Derin Araştırma Raporu: {topic}

**Araştırma Tarihi:** {datetime.now().strftime('%d %B %Y, %H:%M')}
**Araştırma Türü:** Web Tabanlı Derin Araştırma
**Kullanılan Model:** {self.model_name}
**Toplam Kaynak:** {len(research_data)} web kaynağı
**Arama Sorguları:** {len(search_queries)} farklı sorgu

---

"""
            
            source_list = "\n".join([
                f"- [{item['source']}]({item['url']})"
                for item in research_data
            ])
            
            full_report = report_header + final_report + f"\n\n## Kaynaklar\n\n{source_list}"
            
            # Masaüstüne kaydet
            try:
                with open(desktop_filepath, 'w', encoding='utf-8') as f:
                    f.write(full_report)
            except Exception as e:
                logger.error(f"Desktop save error: {e}")
            
            # Research results'a da kaydet
            try:
                with open(research_filepath, 'w', encoding='utf-8') as f:
                    f.write(full_report)
            except Exception as e:
                logger.error(f"Research results save error: {e}")
            
        except Exception as e:
            final_report += f"\n\n**Not:** Dosya kaydetme hatası: {str(e)}"
        
        await self.websocket.send_json({
            "type": "message", 
            "message": "🎉 Araştırma tamamlandı! Kaynaklar txt dosyasına kaydedildi."
        })
        
        return final_report