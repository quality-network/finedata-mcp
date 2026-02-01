"""
HTTP Client for FineData API.

Provides async methods for all FineData scraping endpoints.
"""

import httpx
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ScrapeOptions:
    """Options for scraping requests."""
    
    # Basic options
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    tls_profile: str = "chrome124"
    max_retries: int = 5
    timeout: int = 60
    
    # Feature flags (token multipliers)
    use_antibot: bool = True
    use_js_render: bool = False
    use_residential: bool = False
    use_mobile: bool = False
    use_undetected: bool = False
    
    # JS rendering options
    js_wait_for: str = "networkidle"
    js_scroll: bool = False
    
    # Captcha solving
    solve_captcha: bool = False
    
    # Session management
    session_id: Optional[str] = None
    session_ttl: int = 1800
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to API request dict."""
        return {
            "method": self.method,
            "headers": self.headers,
            "body": self.body,
            "tls_profile": self.tls_profile,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "use_antibot": self.use_antibot,
            "use_js_render": self.use_js_render,
            "use_residential": self.use_residential,
            "use_mobile": self.use_mobile,
            "use_undetected": self.use_undetected,
            "js_wait_for": self.js_wait_for,
            "js_scroll": self.js_scroll,
            "solve_captcha": self.solve_captcha,
            "session_id": self.session_id,
            "session_ttl": self.session_ttl,
        }


@dataclass
class ScrapeResult:
    """Result from a scrape request."""
    
    success: bool
    status_code: int
    headers: dict[str, Any]
    body: str
    meta: dict[str, Any]
    tokens_used: int
    captcha_detected: bool = False
    captcha_type: Optional[str] = None
    captcha_solved: bool = False
    error: Optional[str] = None


@dataclass
class AsyncJob:
    """Async job response."""
    
    job_id: str
    status: str
    url: str
    created_at: str
    estimated_completion: Optional[str] = None
    result: Optional[ScrapeResult] = None
    error: Optional[str] = None


class FineDataClient:
    """Async HTTP client for FineData API."""
    
    def __init__(self):
        config = get_config()
        self.api_url = config.api_url.rstrip("/")
        self.api_key = config.api_key
        self.timeout = config.timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout + 30),
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "finedata-mcp/0.1.0",
                },
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def scrape(
        self,
        url: str,
        options: Optional[ScrapeOptions] = None,
    ) -> ScrapeResult:
        """
        Scrape a URL synchronously.
        
        Args:
            url: Target URL to scrape
            options: Scraping options (use defaults if not provided)
            
        Returns:
            ScrapeResult with page content and metadata
        """
        if options is None:
            options = ScrapeOptions()
        
        client = await self._get_client()
        
        payload = {"url": url, **options.to_dict()}
        
        try:
            response = await client.post(
                f"{self.api_url}/api/v1/scrape",
                json=payload,
            )
            
            if response.status_code == 401:
                return ScrapeResult(
                    success=False,
                    status_code=401,
                    headers={},
                    body="",
                    meta={},
                    tokens_used=0,
                    error="Invalid API key. Check your FINEDATA_API_KEY.",
                )
            
            if response.status_code == 402:
                return ScrapeResult(
                    success=False,
                    status_code=402,
                    headers={},
                    body="",
                    meta={},
                    tokens_used=0,
                    error="Payment required. Please add tokens or upgrade your plan.",
                )
            
            data = response.json()
            
            return ScrapeResult(
                success=data.get("success", False),
                status_code=data.get("status_code", response.status_code),
                headers=data.get("headers", {}),
                body=data.get("body", ""),
                meta=data.get("meta", {}),
                tokens_used=data.get("tokens_used", 0),
                captcha_detected=data.get("captcha_detected", False),
                captcha_type=data.get("captcha_type"),
                captcha_solved=data.get("captcha_solved", False),
            )
            
        except httpx.TimeoutException:
            return ScrapeResult(
                success=False,
                status_code=504,
                headers={},
                body="",
                meta={},
                tokens_used=0,
                error=f"Request timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.error(f"Scrape request failed: {e}")
            return ScrapeResult(
                success=False,
                status_code=500,
                headers={},
                body="",
                meta={},
                tokens_used=0,
                error=str(e),
            )
    
    async def scrape_async(
        self,
        url: str,
        options: Optional[ScrapeOptions] = None,
        callback_url: Optional[str] = None,
        callback_headers: Optional[dict[str, str]] = None,
    ) -> AsyncJob:
        """
        Submit an async scrape job.
        
        Args:
            url: Target URL to scrape
            options: Scraping options
            callback_url: Webhook URL for result notification
            callback_headers: Custom headers for webhook
            
        Returns:
            AsyncJob with job_id for status polling
        """
        if options is None:
            options = ScrapeOptions()
        
        client = await self._get_client()
        
        payload = {
            "url": url,
            **options.to_dict(),
            "callback_url": callback_url,
            "callback_headers": callback_headers,
        }
        
        try:
            response = await client.post(
                f"{self.api_url}/api/v1/async/scrape",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            return AsyncJob(
                job_id=data["job_id"],
                status=data["status"],
                url=data["url"],
                created_at=data["created_at"],
                estimated_completion=data.get("estimated_completion"),
            )
            
        except Exception as e:
            logger.error(f"Async scrape request failed: {e}")
            raise
    
    async def get_job_status(self, job_id: str) -> AsyncJob:
        """
        Get status of an async job.
        
        Args:
            job_id: Job ID from scrape_async
            
        Returns:
            AsyncJob with current status and result if completed
        """
        client = await self._get_client()
        
        try:
            response = await client.get(
                f"{self.api_url}/api/v1/async/jobs/{job_id}",
            )
            response.raise_for_status()
            data = response.json()
            
            result = None
            if data.get("result"):
                r = data["result"]
                result = ScrapeResult(
                    success=r.get("success", False),
                    status_code=r.get("status_code", 0),
                    headers=r.get("headers", {}),
                    body=r.get("body", ""),
                    meta=r.get("meta", {}),
                    tokens_used=data.get("tokens_used", 0),
                )
            
            return AsyncJob(
                job_id=data["job_id"],
                status=data["status"],
                url=data["url"],
                created_at=data["created_at"],
                result=result,
                error=data.get("error"),
            )
            
        except Exception as e:
            logger.error(f"Get job status failed: {e}")
            raise
    
    async def batch_scrape(
        self,
        urls: list[str],
        options: Optional[ScrapeOptions] = None,
        callback_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Submit a batch scrape job for multiple URLs.
        
        Args:
            urls: List of URLs to scrape (max 100)
            options: Scraping options (applied to all URLs)
            callback_url: Webhook URL for batch completion
            
        Returns:
            Batch job info with batch_id and job_ids
        """
        if options is None:
            options = ScrapeOptions()
        
        if len(urls) > 100:
            raise ValueError("Maximum 100 URLs per batch")
        
        client = await self._get_client()
        
        # Build requests list
        requests = [{"url": url, **options.to_dict()} for url in urls]
        
        payload = {
            "requests": requests,
            "callback_url": callback_url,
        }
        
        try:
            response = await client.post(
                f"{self.api_url}/api/v1/async/batch",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Batch scrape request failed: {e}")
            raise
    
    async def get_usage(self) -> dict[str, Any]:
        """
        Get current token usage for the API key.
        
        Returns:
            Usage statistics including tokens used and limits
        """
        client = await self._get_client()
        
        try:
            response = await client.get(f"{self.api_url}/api/v1/usage")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Get usage failed: {e}")
            raise


# Global client instance (lazy loaded)
_client: Optional[FineDataClient] = None


def get_client() -> FineDataClient:
    """Get or create the global client."""
    global _client
    if _client is None:
        _client = FineDataClient()
    return _client
