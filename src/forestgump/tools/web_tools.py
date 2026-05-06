"""Web tools for ForestGump: search, crawl, and information gathering.

This module provides web-based reconnaissance tools including:
- Search engines (Google, DuckDuckGo)
- Parallel web crawling
- HTML parsing and extraction
- URL validation and normalization
"""

import asyncio
import requests
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


@dataclass
class SearchResult:
    """Result from a search query."""
    
    title: str
    url: str
    snippet: str
    source: str = "unknown"
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class CrawlResult:
    """Result from crawling a URL."""
    
    url: str
    status_code: int
    content_type: str
    title: Optional[str] = None
    links: List[str] = None
    text_content: Optional[str] = None
    error: Optional[str] = None
    response_time: float = 0.0
    
    def __post_init__(self):
        if self.links is None:
            self.links = []


class URLValidator:
    """Validate and normalize URLs."""
    
    @staticmethod
    def is_valid(url: str) -> bool:
        """
        Check if URL is valid.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    @staticmethod
    def normalize(url: str) -> str:
        """
        Normalize URL (ensure scheme, trim whitespace).
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL
        """
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url


class WebSearch:
    """Web search tool using public search engines."""
    
    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None):
        """
        Initialize web search tool.
        
        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with proper headers."""
        session = requests.Session()
        session.headers.update({'User-Agent': self.user_agent})
        return session
    
    def search_duckduckgo(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Search using DuckDuckGo (no API key needed).
        
        Args:
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of search results
        """
        results = []
        try:
            # DuckDuckGo search - simple HTML scraping approach
            url = "https://html.duckduckgo.com/"
            params = {'q': query}
            
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            if not HAS_BS4:
                # Fallback if BeautifulSoup not available
                return self._parse_search_fallback(response.text, query, max_results)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results_divs = soup.find_all('div', class_='result')
            
            for result_div in results_divs[:max_results]:
                try:
                    # Extract title and URL
                    link_elem = result_div.find('a', class_='result__url')
                    title_elem = result_div.find('a', class_='result__title')
                    snippet_elem = result_div.find('a', class_='result__snippet')
                    
                    if not link_elem:
                        continue
                    
                    url = link_elem.get('href', '')
                    title = title_elem.text.strip() if title_elem else ''
                    snippet = snippet_elem.text.strip() if snippet_elem else ''
                    
                    if url:
                        results.append(SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            source="duckduckgo"
                        ))
                except Exception:
                    continue
        
        except Exception as e:
            # Log error but don't raise - return partial results
            pass
        
        return results[:max_results]
    
    def _parse_search_fallback(
        self,
        html: str,
        query: str,
        max_results: int
    ) -> List[SearchResult]:
        """Fallback parsing without BeautifulSoup."""
        results = []
        try:
            # Simple regex-based extraction
            url_pattern = r'href=["\']([^"\']+)["\']'
            urls = re.findall(url_pattern, html)
            
            for url in urls[:max_results]:
                if url.startswith('http') and query.lower() in html.lower():
                    results.append(SearchResult(
                        title=urlparse(url).netloc,
                        url=url,
                        snippet=f"Result for '{query}'",
                        source="duckduckgo_fallback"
                    ))
        except Exception:
            pass
        
        return results
    
    def close(self):
        """Close the session."""
        self.session.close()


class WebCrawler:
    """Parallel web crawler for reconnaissance."""
    
    def __init__(
        self,
        timeout: int = 10,
        max_workers: int = 5,
        user_agent: Optional[str] = None,
        depth: int = 1
    ):
        """
        Initialize web crawler.
        
        Args:
            timeout: Request timeout in seconds
            max_workers: Max concurrent requests
            user_agent: Custom user agent
            depth: Crawl depth (1 = only specified URLs, 2+ = follow links)
        """
        self.timeout = timeout
        self.max_workers = max_workers
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
        self.depth = depth
        self.visited_urls = set()
        self.results = {}
    
    def crawl_urls(self, urls: List[str]) -> Dict[str, CrawlResult]:
        """
        Crawl multiple URLs in parallel.
        
        Args:
            urls: List of URLs to crawl
            
        Returns:
            Dictionary mapping URLs to crawl results
        """
        self.visited_urls.clear()
        self.results.clear()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all URLs for crawling
            future_to_url = {
                executor.submit(self._crawl_single, url): url
                for url in urls
            }
            
            # Process completed requests
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    self.results[url] = result
                except Exception as e:
                    self.results[url] = CrawlResult(
                        url=url,
                        status_code=0,
                        content_type="",
                        error=str(e)
                    )
        
        return self.results
    
    def _crawl_single(self, url: str) -> CrawlResult:
        """
        Crawl a single URL.
        
        Args:
            url: URL to crawl
            
        Returns:
            Crawl result
        """
        if url in self.visited_urls:
            return CrawlResult(
                url=url,
                status_code=0,
                content_type="",
                error="URL already visited"
            )
        
        self.visited_urls.add(url)
        
        try:
            url = URLValidator.normalize(url)
            if not URLValidator.is_valid(url):
                return CrawlResult(
                    url=url,
                    status_code=0,
                    content_type="",
                    error="Invalid URL"
                )
            
            start_time = time.time()
            headers = {'User-Agent': self.user_agent}
            
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                verify=False
            )
            
            response_time = time.time() - start_time
            
            # Extract content
            content_type = response.headers.get('content-type', 'unknown')
            title = None
            links = []
            text_content = None
            
            # Parse HTML if applicable
            if 'text/html' in content_type and HAS_BS4:
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract title
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                    
                    # Extract links
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        # Convert relative URLs to absolute
                        if not href.startswith(('http://', 'https://')):
                            href = urljoin(url, href)
                        links.append(href)
                    
                    # Extract text
                    text_content = soup.get_text(separator='\n', strip=True)[:500]
                
                except Exception:
                    pass
            
            return CrawlResult(
                url=url,
                status_code=response.status_code,
                content_type=content_type,
                title=title,
                links=links[:10],  # Limit to 10 links
                text_content=text_content,
                response_time=response_time
            )
        
        except requests.Timeout:
            return CrawlResult(
                url=url,
                status_code=0,
                content_type="",
                error=f"Timeout after {self.timeout}s"
            )
        
        except requests.RequestException as e:
            return CrawlResult(
                url=url,
                status_code=0,
                content_type="",
                error=str(e)
            )
        
        except Exception as e:
            return CrawlResult(
                url=url,
                status_code=0,
                content_type="",
                error=f"Unknown error: {str(e)}"
            )


def search_web(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search the web using DuckDuckGo.
    
    This is a convenience function for the tool registry.
    
    Args:
        query: Search query
        max_results: Maximum results to return
        
    Returns:
        List of search result dictionaries
    """
    searcher = WebSearch()
    try:
        results = searcher.search_duckduckgo(query, max_results)
        return [
            {
                'title': r.title,
                'url': r.url,
                'snippet': r.snippet,
                'source': r.source
            }
            for r in results
        ]
    finally:
        searcher.close()


def crawl_urls(urls: List[str], timeout: int = 10, max_workers: int = 5) -> Dict[str, Dict]:
    """
    Crawl multiple URLs in parallel.
    
    This is a convenience function for the tool registry.
    
    Args:
        urls: List of URLs to crawl
        timeout: Request timeout in seconds
        max_workers: Maximum concurrent requests
        
    Returns:
        Dictionary mapping URLs to crawl results
    """
    crawler = WebCrawler(timeout=timeout, max_workers=max_workers)
    results = crawler.crawl_urls(urls)
    
    # Convert to dictionaries for JSON serialization
    return {
        url: {
            'url': result.url,
            'status_code': result.status_code,
            'content_type': result.content_type,
            'title': result.title,
            'links_count': len(result.links),
            'links': result.links,
            'text_preview': result.text_content[:200] if result.text_content else None,
            'response_time': result.response_time,
            'error': result.error
        }
        for url, result in results.items()
    }
