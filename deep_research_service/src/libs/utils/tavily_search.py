import asyncio
import os
from dataclasses import dataclass
from typing import Optional

# Tavily istemcisi opsiyonel olarak içe aktarılır
try:
    from tavily import AsyncTavilyClient, TavilyClient  # type: ignore
except ImportError:  # Paket kurulu değilse
    TavilyClient = None  # type: ignore
    AsyncTavilyClient = None  # type: ignore

# Google tabanlı arama için gerekli bağımlılıkları opsiyonel içe aktar
try:
    from googlesearch import search as google_search  # type: ignore
    from bs4 import BeautifulSoup  # type: ignore
    import requests  # type: ignore
except ImportError:
    google_search = None  # type: ignore
    BeautifulSoup = None  # type: ignore
    requests = None  # type: ignore


@dataclass(frozen=True, kw_only=True)
class SearchResult:
    title: str
    link: str
    content: str
    raw_content: Optional[str] = None

    def __str__(self, include_raw=True):
        result = f"Title: {self.title}\n" f"Link: {self.link}\n" f"Content: {self.content}"
        if include_raw and self.raw_content:
            result += f"\nRaw Content: {self.raw_content}"
        return result

    def short_str(self):
        return self.__str__(include_raw=False)


@dataclass(frozen=True, kw_only=True)
class SearchResults:
    results: list[SearchResult]

    def __str__(self, short=False):
        if short:
            result_strs = [result.short_str() for result in self.results]
        else:
            result_strs = [str(result) for result in self.results]
        return "\n\n".join(f"[{i+1}] {result_str}" for i, result_str in enumerate(result_strs))

    def __add__(self, other):
        return SearchResults(results=self.results + other.results)

    def short_str(self):
        return self.__str__(short=True)


def extract_tavily_results(response) -> SearchResults:
    """Extract key information from Tavily search results."""
    results = []
    for item in response.get("results", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                link=item.get("url", ""),
                content=item.get("content", ""),
                raw_content=item.get("raw_content", ""),
            )
        )
    return SearchResults(results=results)


# ----------------- Fallback Google arama yardımcıları ----------------------


class FallbackSearchError(RuntimeError):
    """Tavily ve Google bağımlılıkları olmadığında fırlatılır."""


def _google_fallback_search(query: str, max_results: int = 3, include_raw: bool = True) -> "SearchResults":
    """Tavily kullanılamadığında basit Google araması gerçekleştirir.

    Gerekli paketler eksikse 'FallbackSearchError' fırlatır. Hiç sonuç dönmezse de aynı hata fırlatılır.
    """

    if google_search is None or requests is None or BeautifulSoup is None:
        raise FallbackSearchError(
            "Google tabanlı arama için gerekli bağımlılıklar yüklü değil (googlesearch-python, requests, beautifulsoup4)."
        )

    results_list: list[SearchResult] = []

    for url in google_search(query, num_results=max_results):
        try:
            # İçeriği çek ve özetle
            title = url
            raw_content: Optional[str] = None
            content = ""

            if include_raw:
                # Security headers and user agent
                headers = {
                    'User-Agent': 'Mozilla/5.0 (compatible; LocoDex-DeepSearch/1.0)',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                resp = requests.get(url, timeout=10, headers=headers, allow_redirects=True, 
                                  max_redirects=3, stream=False, verify=True)
                resp.raise_for_status()
                
                # Content length validation
                if len(resp.content) > 10 * 1024 * 1024:  # 10MB limit
                    raise Exception("Content too large")
                
                # Content type validation
                content_type = resp.headers.get('content-type', '').lower()
                if not any(ct in content_type for ct in ['text/html', 'text/plain', 'application/xml']):
                    raise Exception("Invalid content type")
                
                soup = BeautifulSoup(resp.content, "html.parser")
                
                # Remove potentially dangerous elements
                for tag in soup(["script", "style", "iframe", "object", "embed"]):
                    tag.decompose()
                
                title = soup.title.string.strip() if soup.title and soup.title.string else url
                raw_content = soup.get_text(separator="\n", strip=True)
                
                # Content length limit
                if len(raw_content) > 50000:  # 50KB limit
                    raw_content = raw_content[:50000] + "...[truncated]"
                
                content = (raw_content[:500] + "...") if len(raw_content) > 500 else raw_content

            results_list.append(SearchResult(title=title, link=url, content=content, raw_content=raw_content))
        except Exception as e:
            # Log security-related errors but continue
            print(f"Skipping URL {url}: {str(e)[:100]}")
            continue

    if not results_list:
        raise FallbackSearchError("Google araması hiçbir sonuç döndürmedi veya tüm istekler başarısız oldu.")

    return SearchResults(results=results_list)


# ------------------ Tavily araması (opsiyonel) -----------------------------


def tavily_search(query: str, max_results: int = 3, include_raw: bool = True) -> "SearchResults":
    """Önce Tavily ardından Google fallback ile arama yapar."""

    api_key = os.getenv("TAVILY_API_KEY")

    # Tavily tercihli
    if api_key and TavilyClient is not None:
        try:
            client = TavilyClient(api_key)
            resp = client.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
                include_raw_content=include_raw,
            )
            return extract_tavily_results(resp)
        except Exception:
            # Tavily başarısızsa Google'a geç
            pass

    # Fallback
    return _google_fallback_search(query, max_results=max_results, include_raw=include_raw)


async def atavily_search_results(query: str, max_results: int = 3, include_raw: bool = True) -> "SearchResults":
    """Asenkron sürüm – Tavily varsa onu, yoksa Google fallback'i kullanır."""

    api_key = os.getenv("TAVILY_API_KEY")

    if api_key and AsyncTavilyClient is not None:
        try:
            client = AsyncTavilyClient(api_key)
            resp = await client.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
                include_raw_content=include_raw,
            )
            return extract_tavily_results(resp)
        except Exception:
            # Tavily'de hata olursa fallback'e geç
            pass

    # Senkron fallback'i çalıştır (bloklayıcı olabilir; küçük istekler için yeterli)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _google_fallback_search, query, max_results, include_raw
    )


if __name__ == "__main__":
    print(asyncio.run(atavily_search_results("What is the capital of France?")))