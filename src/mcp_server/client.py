"""HTTP client for FineData public API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from . import __version__
from .config import get_config

logger = logging.getLogger(__name__)

CONTENT_TRUNCATE_CHARS = 60_000


class FineDataAPIError(Exception):
    """API error with HTTP status and parsed body for agents."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.body = body

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.message}"


@dataclass
class ScrapeOptions:
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    tls_profile: str = "chrome136"
    max_retries: int = 5
    timeout: int = 120
    auto_retry: bool = True

    use_antibot: bool = True
    use_js_render: bool = False
    use_isp: bool = False
    use_residential: bool = False
    use_mobile: bool = False
    proxy_sticky: bool = False
    proxy_country: Optional[str] = None
    proxy_profile_id: Optional[int] = None

    use_undetected: bool = False  # stealth_antibot
    use_nodriver: bool = False  # stealth_antibot_headful
    use_patchright: bool = False  # stealth_new
    use_botbrowser: bool = False  # stealth_premium
    use_botbrowser_headful: bool = False  # stealth_premium_headful

    js_wait_for: str = "networkidle"
    js_scroll: bool = False
    js_actions: Optional[list[dict[str, Any]]] = None
    solve_captcha: bool = False
    session_id: Optional[str] = None
    session_ttl: int = 1800

    formats: Optional[list[str]] = None
    only_main_content: bool = False

    extract_rules: Optional[dict[str, Any]] = None
    extract_schema: Optional[dict[str, Any]] = None
    extract_prompt: Optional[str] = None
    ai_content_mode: str = "full"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "headers": self.headers,
            "body": self.body,
            "tls_profile": self.tls_profile,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "auto_retry": self.auto_retry,
            "use_antibot": self.use_antibot,
            "use_js_render": self.use_js_render,
            "use_isp": self.use_isp,
            "use_residential": self.use_residential,
            "use_mobile": self.use_mobile,
            "proxy_sticky": self.proxy_sticky,
            "proxy_country": self.proxy_country,
            "proxy_profile_id": self.proxy_profile_id,
            "stealth_antibot": self.use_undetected,
            "stealth_antibot_headful": self.use_nodriver,
            "stealth_new": self.use_patchright,
            "stealth_premium": self.use_botbrowser,
            "stealth_premium_headful": self.use_botbrowser_headful,
            "js_wait_for": self.js_wait_for,
            "js_scroll": self.js_scroll,
            "js_actions": self.js_actions,
            "solve_captcha": self.solve_captcha,
            "session_id": self.session_id,
            "session_ttl": self.session_ttl,
            "formats": self.formats,
            "only_main_content": self.only_main_content,
            "extract_rules": self.extract_rules,
            "extract_schema": self.extract_schema,
            "extract_prompt": self.extract_prompt,
            "ai_content_mode": self.ai_content_mode,
        }
        return {k: v for k, v in payload.items() if v is not None}


@dataclass
class ScrapeResult:
    success: bool
    status_code: int
    headers: dict[str, Any]
    body: str
    data: Optional[dict[str, Any]] = None
    meta: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    captcha_detected: bool = False
    captcha_type: Optional[str] = None
    captcha_solved: bool = False
    error: Optional[str] = None


@dataclass
class AsyncJob:
    job_id: str
    status: str
    url: str
    created_at: str
    estimated_completion: Optional[str] = None
    result: Optional[ScrapeResult] = None
    error: Optional[str] = None
    tokens_used: int = 0
    raw: Optional[dict[str, Any]] = None


def _error_message_from_body(status_code: int, body: Any) -> str:
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message")
        if isinstance(detail, list):
            # FastAPI validation errors
            parts = []
            for item in detail[:5]:
                if isinstance(item, dict):
                    loc = ".".join(str(x) for x in item.get("loc", [])[-2:])
                    parts.append(f"{loc}: {item.get('msg')}")
                else:
                    parts.append(str(item))
            detail = "; ".join(parts)
        if detail:
            return str(detail)
    if isinstance(body, str) and body.strip():
        return body[:500]
    return f"Request failed with status {status_code}"


class FineDataClient:
    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        config = get_config(require_api_key=False)
        self.api_url = (api_url or config.api_url).rstrip("/")
        self.api_key = api_key if api_key is not None else config.api_key
        self.timeout = config.timeout
        self._client: Optional[httpx.AsyncClient] = None
        # Per-call hop headers. Never written onto the shared httpx client:
        # two users on a cached FineDataClient must not see each other's IP.
        self._call_headers: dict[str, str] = {}

    def with_api_key(self, api_key: str) -> "FineDataClient":
        return FineDataClient(api_key=api_key, api_url=self.api_url)

    def with_call_headers(self, headers: dict[str, str]) -> "FineDataClient":
        """Return a client that sends ``headers`` on each HTTP call.

        Empty headers reuse this instance (nothing to leak). Non-empty headers
        always clone: the cached client from ``get_client`` must stay clean.
        """
        cleaned = {k: v for k, v in headers.items() if v}
        if not cleaned:
            return self
        clone = FineDataClient(api_key=self.api_key, api_url=self.api_url)
        clone._call_headers = cleaned
        return clone

    def _request_headers(self) -> dict[str, str] | None:
        return self._call_headers or None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"finedata-mcp/{__version__}",
            }
            if self.api_key:
                if self.api_key.startswith("fd_"):
                    headers["x-api-key"] = self.api_key
                    headers["Authorization"] = f"Bearer {self.api_key}"
                else:
                    headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout + 30),
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        msg = _error_message_from_body(response.status_code, body)
        if response.status_code == 401:
            msg = "Invalid or expired credentials. Check FINEDATA_API_KEY / OAuth token."
        elif response.status_code == 402:
            msg = "Payment required. Add tokens or upgrade your plan at https://finedata.ai"
        elif response.status_code == 429:
            msg = f"Rate limited. {msg}"
        raise FineDataAPIError(response.status_code, msg, body)

    def _parse_scrape_result(self, data: dict[str, Any], http_status: int) -> ScrapeResult:
        return ScrapeResult(
            success=data.get("success", False),
            status_code=data.get("status_code", http_status),
            headers=data.get("headers", {}) or {},
            body=data.get("body", "") or "",
            data=data.get("data"),
            meta=data.get("meta", {}) or {},
            tokens_used=int(data.get("tokens_used") or 0),
            captcha_detected=bool(data.get("captcha_detected", False)),
            captcha_type=data.get("captcha_type"),
            captcha_solved=bool(data.get("captcha_solved", False)),
            error=data.get("error") or data.get("detail"),
        )

    async def scrape(self, url: str, options: Optional[ScrapeOptions] = None) -> ScrapeResult:
        if options is None:
            options = ScrapeOptions()
        client = await self._get_client()
        payload = {"url": url, **options.to_dict()}
        try:
            response = await client.post(
                f"{self.api_url}/api/v1/scrape",
                json=payload,
                headers=self._request_headers(),
            )
            if response.status_code in (401, 402, 422, 429):
                await self._raise_for_status(response)
            if response.status_code >= 400:
                await self._raise_for_status(response)
            data = response.json()
            return self._parse_scrape_result(data, response.status_code)
        except FineDataAPIError:
            raise
        except httpx.TimeoutException:
            return ScrapeResult(
                success=False,
                status_code=504,
                headers={},
                body="",
                error=f"Request timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.error("Scrape request failed: %s", e)
            return ScrapeResult(
                success=False,
                status_code=500,
                headers={},
                body="",
                error=str(e),
            )

    async def scrape_async(
        self,
        url: str,
        options: Optional[ScrapeOptions] = None,
        callback_url: Optional[str] = None,
        callback_headers: Optional[dict[str, str]] = None,
    ) -> AsyncJob:
        if options is None:
            options = ScrapeOptions(formats=["markdown"])
        client = await self._get_client()
        payload = {
            "url": url,
            **options.to_dict(),
            "callback_url": callback_url,
            "callback_headers": callback_headers,
        }
        response = await client.post(
            f"{self.api_url}/api/v1/async/scrape",
            json=payload,
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        data = response.json()
        return AsyncJob(
            job_id=data["job_id"],
            status=data["status"],
            url=data["url"],
            created_at=data["created_at"],
            estimated_completion=data.get("estimated_completion"),
            raw=data,
        )

    async def get_job_status(self, job_id: str) -> AsyncJob:
        client = await self._get_client()
        response = await client.get(
            f"{self.api_url}/api/v1/async/jobs/{job_id}",
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        data = response.json()
        result = None
        if data.get("result"):
            r = data["result"]
            result = self._parse_scrape_result(r, r.get("status_code", 0))
            if not result.tokens_used:
                result.tokens_used = int(data.get("tokens_used") or 0)
        return AsyncJob(
            job_id=data["job_id"],
            status=data["status"],
            url=data["url"],
            created_at=data["created_at"],
            result=result,
            error=data.get("error"),
            tokens_used=int(data.get("tokens_used") or 0),
            raw=data,
        )

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.delete(
            f"{self.api_url}/api/v1/async/jobs/{job_id}",
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        if response.content:
            try:
                return response.json()
            except Exception:
                pass
        return {"job_id": job_id, "status": "cancelled"}

    async def list_jobs(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.get(
            f"{self.api_url}/api/v1/async/jobs",
            params={"limit": limit, "offset": offset},
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        return response.json()

    async def batch_scrape(
        self,
        requests: list[dict[str, Any]],
        callback_url: Optional[str] = None,
    ) -> dict[str, Any]:
        if len(requests) > 100:
            raise ValueError("Maximum 100 URLs per batch")
        client = await self._get_client()
        payload: dict[str, Any] = {"requests": requests}
        if callback_url:
            payload["callback_url"] = callback_url
        response = await client.post(
            f"{self.api_url}/api/v1/async/batch",
            json=payload,
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        return response.json()

    async def get_batch_status(self, batch_id: str) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.get(
            f"{self.api_url}/api/v1/async/batch/{batch_id}",
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        return response.json()

    async def get_usage(self) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.get(
            f"{self.api_url}/api/v1/usage",
            headers=self._request_headers(),
        )
        await self._raise_for_status(response)
        return response.json()


_client: Optional[FineDataClient] = None


def get_client(api_key: Optional[str] = None) -> FineDataClient:
    """Return a client. If api_key is set, return a fresh keyed client."""
    global _client
    if api_key:
        base = _client or FineDataClient()
        return base.with_api_key(api_key)
    if _client is None:
        _client = FineDataClient()
    return _client
