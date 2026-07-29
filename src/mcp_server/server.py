"""FineData MCP Server — FastMCP (stdio + Streamable HTTP)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Optional

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import AnyHttpUrl

from . import __version__
from .client import FineDataAPIError, FineDataClient, ScrapeOptions, get_client
from .config import get_config
from .escalation import SERVER_INSTRUCTIONS
from .formatting import (
    format_api_error,
    format_scrape_failure,
    format_scrape_success,
    options_from_args,
    truncate_text,
)

logger = logging.getLogger("finedata-mcp")

SYNC_FORMATS = ["markdown", "rawHtml", "text", "links", "screenshot", "csv", "xlsx"]
ASYNC_FORMATS = ["markdown", "rawHtml", "text", "links", "screenshot"]


class _PassThroughTokenVerifier:
    """Accept API keys (fd_*) and OAuth JWTs (aud=mcp).

    Verification of fd_* is deferred to the FineData API on first tool call.
    JWTs are verified locally when FINEDATA_JWT_SECRET is configured.
    """

    def __init__(self, jwt_secret: str | None, jwt_algorithm: str = "HS256"):
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        if token.startswith("fd_"):
            return AccessToken(
                token=token,
                client_id="api_key",
                scopes=["scrape:write", "jobs:read", "usage:read"],
            )
        if self.jwt_secret:
            try:
                from jose import jwt

                payload = jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=[self.jwt_algorithm],
                    audience="mcp",
                    options={"verify_aud": True},
                )
                scopes = payload.get("scope", "")
                if isinstance(scopes, str):
                    scope_list = [s for s in scopes.split() if s]
                elif isinstance(scopes, list):
                    scope_list = [str(s) for s in scopes]
                else:
                    scope_list = ["scrape:write", "jobs:read", "usage:read"]
                return AccessToken(
                    token=token,
                    client_id=str(payload.get("client_id") or payload.get("sub") or "oauth"),
                    scopes=scope_list or ["scrape:write", "jobs:read", "usage:read"],
                    expires_at=payload.get("exp"),
                    resource=payload.get("aud") if isinstance(payload.get("aud"), str) else "mcp",
                )
            except Exception as e:
                logger.warning("OAuth token verification failed: %s", e)
                return None
        # No JWT secret — treat opaque bearer as pass-through (gateway validates)
        return AccessToken(
            token=token,
            client_id="bearer",
            scopes=["scrape:write", "jobs:read", "usage:read"],
        )


def _resolve_api_key(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    access = get_access_token()
    if access and access.token:
        return access.token
    cfg = get_config(require_api_key=False)
    if cfg.api_key:
        return cfg.api_key
    raise FineDataAPIError(
        401,
        "No API key. Set FINEDATA_API_KEY or send Authorization: Bearer fd_… / OAuth token.",
    )


def _client() -> FineDataClient:
    return get_client(_resolve_api_key())


def create_mcp(*, http_mode: bool = False) -> FastMCP:
    cfg = get_config(require_api_key=not http_mode)

    auth_settings = None
    token_verifier = None
    if http_mode and cfg.oauth_issuer and cfg.resource_url:
        auth_settings = AuthSettings(
            issuer_url=AnyHttpUrl(cfg.oauth_issuer),
            resource_server_url=AnyHttpUrl(cfg.resource_url),
            # This list does double duty: FastMCP enforces it *and* publishes it as
            # `scopes_supported` in the protected-resource document, which is where a
            # client reads what to ask the authorization server for. Listing only
            # scrape:write made Cursor request exactly that, so job and usage tools
            # would have failed with 403 on a token the user had just approved. The
            # eight tools need all three; per-path scope checks stay on the gateway.
            required_scopes=["scrape:write", "jobs:read", "usage:read"],
            client_registration_options=ClientRegistrationOptions(
                enabled=False,  # DCR lives on gateway AS
                valid_scopes=["scrape:write", "jobs:read", "usage:read"],
                default_scopes=["scrape:write", "jobs:read", "usage:read"],
            ),
        )
        token_verifier = _PassThroughTokenVerifier(cfg.jwt_secret, cfg.jwt_algorithm)
    elif http_mode:
        # HTTP without full OAuth metadata still accepts Bearer via custom middleware path:
        # FastMCP requires auth settings for protected resource; if missing, rely on env key.
        token_verifier = _PassThroughTokenVerifier(cfg.jwt_secret, cfg.jwt_algorithm)

    mcp = FastMCP(
        name="finedata",
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://finedata.ai",
        host=cfg.host,
        port=cfg.port,
        stateless_http=True,
        json_response=True,
        auth=auth_settings,
        token_verifier=token_verifier if auth_settings else None,
    )

    # FastMCP takes no `version`, so serverInfo falls back to the MCP SDK's own
    # version and clients show that instead of ours (they displayed 1.29.0).
    mcp._mcp_server.version = __version__

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request):
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok", "version": __version__})

    # No custom_route for /.well-known/oauth-protected-resource: FastMCP serves it
    # from AuthSettings above. A hand-rolled copy here is shadowed by the SDK's
    # route and only misleads whoever reads this file — it listed all three scopes
    # while prod was serving one.

    # ---- tools ----

    @mcp.tool(
        title="Scrape URL",
        description=(
            "Scrape a web page with antibot bypass. Returns markdown by default.\n\n"
            + SERVER_INSTRUCTIONS
            + "\n\nToken costs (estimates, use_antibot default +2 included): "
            "base ~3; stealth_antibot +7; stealth_premium +20 (~23 total with DC); "
            "stealth_premium+ISP ~25; stealth_premium_headful +30; ISP +2; "
            "residential +3; mobile +4; captcha +10; AI extract +5. "
            "js_actions +2 each."
        ),
        annotations=ToolAnnotations(
            title="Scrape URL",
            readOnlyHint=False,  # bills tokens; method can be POST/PUT/DELETE
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def scrape_url(
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 5,
        auto_retry: bool = True,
        use_antibot: bool = True,
        tls_profile: str = "chrome136",
        use_isp: bool = False,
        use_residential: bool = False,
        use_mobile: bool = False,
        proxy_sticky: bool = False,
        proxy_country: Optional[str] = None,
        proxy_profile_id: Optional[int] = None,
        stealth_antibot: bool = False,
        stealth_antibot_headful: bool = False,
        stealth_new: bool = False,
        stealth_premium: bool = False,
        stealth_premium_headful: bool = False,
        use_js_render: bool = False,
        js_wait_for: str = "networkidle",
        js_scroll: bool = False,
        js_actions: Optional[list[dict[str, Any]]] = None,
        solve_captcha: bool = False,
        session_id: Optional[str] = None,
        session_ttl: int = 1800,
        formats: Optional[list[str]] = None,
        only_main_content: bool = False,
        extract_rules: Optional[dict[str, Any]] = None,
        extract_schema: Optional[dict[str, Any]] = None,
        extract_prompt: Optional[str] = None,
        ai_content_mode: str = "full",
        ctx: Context | None = None,
    ) -> list[TextContent | ImageContent]:
        args = {
            "method": method,
            "headers": headers,
            "body": body,
            "timeout": timeout,
            "max_retries": max_retries,
            "auto_retry": auto_retry,
            "use_antibot": use_antibot,
            "tls_profile": tls_profile,
            "use_isp": use_isp,
            "use_residential": use_residential,
            "use_mobile": use_mobile,
            "proxy_sticky": proxy_sticky,
            "proxy_country": proxy_country,
            "proxy_profile_id": proxy_profile_id,
            "stealth_antibot": stealth_antibot,
            "stealth_antibot_headful": stealth_antibot_headful,
            "stealth_new": stealth_new,
            "stealth_premium": stealth_premium,
            "stealth_premium_headful": stealth_premium_headful,
            "use_js_render": use_js_render,
            "js_wait_for": js_wait_for,
            "js_scroll": js_scroll,
            "js_actions": js_actions,
            "solve_captcha": solve_captcha,
            "session_id": session_id,
            "session_ttl": session_ttl,
            "formats": formats or ["markdown"],
            "only_main_content": only_main_content,
            "extract_rules": extract_rules,
            "extract_schema": extract_schema,
            "extract_prompt": extract_prompt,
            "ai_content_mode": ai_content_mode,
        }
        try:
            options = ScrapeOptions(**options_from_args(args))
            result = await _client().scrape(url, options)
            if not result.success:
                return format_scrape_failure(
                    url,
                    result,
                    stealth_antibot=stealth_antibot or stealth_antibot_headful,
                    stealth_premium=stealth_premium,
                    stealth_premium_headful=stealth_premium_headful,
                    use_isp=use_isp,
                    use_residential=use_residential,
                    use_mobile=use_mobile,
                )
            return format_scrape_success(url, result)
        except FineDataAPIError as e:
            return format_api_error(e)
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Scrape Async",
        description=(
            "Submit an async scrape job (long-running / heavy stealth). "
            "Defaults formats=['markdown']. Poll with get_job_status."
        ),
        annotations=ToolAnnotations(
            title="Scrape Async",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def scrape_async(
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 5,
        tls_profile: str = "chrome136",
        use_antibot: bool = True,
        use_js_render: bool = False,
        use_isp: bool = False,
        use_residential: bool = False,
        use_mobile: bool = False,
        proxy_sticky: bool = False,
        proxy_country: Optional[str] = None,
        proxy_profile_id: Optional[int] = None,
        stealth_antibot: bool = False,
        stealth_antibot_headful: bool = False,
        stealth_new: bool = False,
        stealth_premium: bool = False,
        stealth_premium_headful: bool = False,
        js_wait_for: str = "networkidle",
        js_scroll: bool = False,
        js_actions: Optional[list[dict[str, Any]]] = None,
        solve_captcha: bool = False,
        session_id: Optional[str] = None,
        session_ttl: int = 1800,
        formats: Optional[list[str]] = None,
        only_main_content: bool = False,
        extract_rules: Optional[dict[str, Any]] = None,
        extract_schema: Optional[dict[str, Any]] = None,
        extract_prompt: Optional[str] = None,
        ai_content_mode: str = "full",
        callback_url: Optional[str] = None,
        ctx: Context | None = None,
    ) -> list[TextContent]:
        args = locals()
        args.pop("ctx", None)
        args.pop("callback_url", None)
        args.pop("url")
        try:
            options = ScrapeOptions(**options_from_args(args, async_formats=True))
            job = await _client().scrape_async(url, options, callback_url=callback_url)
            text = (
                f"Async job submitted.\n\n"
                f"Job ID: {job.job_id}\nStatus: {job.status}\nURL: {job.url}\n"
                f"Created: {job.created_at}\n\n"
                f'Use get_job_status with job_id="{job.job_id}".'
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Get Job Status",
        description="Poll async job status. On completed, returns markdown (not raw HTML).",
        annotations=ToolAnnotations(
            title="Get Job Status",
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_job_status(job_id: str, ctx: Context | None = None) -> list[TextContent | ImageContent]:
        try:
            job = await _client().get_job_status(job_id)
            parts = [
                f"Job ID: {job.job_id}",
                f"Status: {job.status}",
                f"URL: {job.url}",
                f"Created: {job.created_at}",
            ]
            if job.error:
                parts.append(f"Error: {job.error}")
            if job.result:
                parts.append(f"Tokens used: {job.result.tokens_used or job.tokens_used}")
                if job.result.success:
                    return format_scrape_success(job.url, job.result)  # type: ignore[arg-type]
                parts.append(f"Result error: {job.result.error or job.result.status_code}")
                parts.append("--- Content ---")
                parts.append(truncate_text(job.result.body or ""))
            return [TextContent(type="text", text="\n".join(parts))]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Cancel Job",
        description="Cancel a pending/processing async job.",
        annotations=ToolAnnotations(
            title="Cancel Job",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def cancel_job(job_id: str, ctx: Context | None = None) -> list[TextContent]:
        try:
            data = await _client().cancel_job(job_id)
            return [TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="List Jobs",
        description="List recent async jobs for the authenticated account.",
        annotations=ToolAnnotations(
            title="List Jobs",
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def list_jobs(
        limit: int = 20,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> list[TextContent]:
        try:
            data = await _client().list_jobs(limit=limit, offset=offset)
            return [
                TextContent(
                    type="text",
                    text=truncate_text(json.dumps(data, indent=2, ensure_ascii=False)),
                )
            ]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Batch Scrape",
        description=(
            "Submit up to 100 URLs as a batch. `urls` may be a list of strings "
            "or objects {url, ...overrides}. Defaults formats=['markdown'] per item. "
            "Poll with get_batch_status."
        ),
        annotations=ToolAnnotations(
            title="Batch Scrape",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def batch_scrape(
        urls: list[Any],
        use_js_render: bool = False,
        use_isp: bool = False,
        use_residential: bool = False,
        use_mobile: bool = False,
        stealth_antibot: bool = False,
        stealth_premium: bool = False,
        stealth_premium_headful: bool = False,
        stealth_new: bool = False,
        formats: Optional[list[str]] = None,
        only_main_content: bool = False,
        extract_prompt: Optional[str] = None,
        extract_schema: Optional[dict[str, Any]] = None,
        proxy_country: Optional[str] = None,
        callback_url: Optional[str] = None,
        ctx: Context | None = None,
    ) -> list[TextContent]:
        try:
            if not urls:
                return [TextContent(type="text", text="Error: urls is required")]
            if len(urls) > 100:
                return [TextContent(type="text", text="Error: Maximum 100 URLs per batch")]

            base = options_from_args(
                {
                    "use_js_render": use_js_render,
                    "use_isp": use_isp,
                    "use_residential": use_residential,
                    "use_mobile": use_mobile,
                    "stealth_antibot": stealth_antibot,
                    "stealth_premium": stealth_premium,
                    "stealth_premium_headful": stealth_premium_headful,
                    "stealth_new": stealth_new,
                    "formats": formats or ["markdown"],
                    "only_main_content": only_main_content,
                    "extract_prompt": extract_prompt,
                    "extract_schema": extract_schema,
                    "proxy_country": proxy_country,
                },
                async_formats=True,
            )
            # Convert to public API field names for batch payload
            base_public = ScrapeOptions(**base).to_dict()

            requests: list[dict[str, Any]] = []
            for item in urls:
                if isinstance(item, str):
                    requests.append({"url": item, **base_public})
                elif isinstance(item, dict) and item.get("url"):
                    overrides = options_from_args({**base, **item}, async_formats=True)
                    # item may already use public stealth_* names
                    pub = ScrapeOptions(**{k: overrides.get(k) for k in overrides}).to_dict()
                    # Prefer explicit public keys from item when present
                    for k in (
                        "stealth_antibot",
                        "stealth_premium",
                        "stealth_premium_headful",
                        "stealth_new",
                        "stealth_antibot_headful",
                        "use_js_render",
                        "use_isp",
                        "use_residential",
                        "use_mobile",
                        "formats",
                        "only_main_content",
                        "extract_prompt",
                        "extract_schema",
                        "proxy_country",
                        "proxy_sticky",
                        "proxy_profile_id",
                        "timeout",
                    ):
                        if k in item and item[k] is not None:
                            pub[k] = item[k]
                    requests.append({"url": item["url"], **pub})
                else:
                    return [
                        TextContent(
                            type="text",
                            text="Error: each urls item must be a string URL or object with url",
                        )
                    ]

            result = await _client().batch_scrape(requests, callback_url=callback_url)
            text = (
                f"Batch submitted.\n\n"
                f"Batch ID: {result.get('batch_id')}\n"
                f"Total jobs: {result.get('total_jobs')}\n"
                f"Status: {result.get('status')}\n\n"
                f"Job IDs:\n"
                + "\n".join(f"  - {jid}" for jid in result.get("job_ids", []))
                + f"\n\nUse get_batch_status with batch_id=\"{result.get('batch_id')}\"."
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Get Batch Status",
        description="Get overall batch status and per-job results.",
        annotations=ToolAnnotations(
            title="Get Batch Status",
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_batch_status(batch_id: str, ctx: Context | None = None) -> list[TextContent]:
        try:
            data = await _client().get_batch_status(batch_id)
            return [
                TextContent(
                    type="text",
                    text=truncate_text(json.dumps(data, indent=2, ensure_ascii=False)),
                )
            ]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="Get Usage",
        description=(
            "Current period token usage (api_tokens_used). "
            "Does not include plan token limit — check the billing dashboard."
        ),
        annotations=ToolAnnotations(
            title="Get Usage",
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_usage(ctx: Context | None = None) -> list[TextContent]:
        try:
            usage = await _client().get_usage()
            customer_usage = usage.get("customer_usage", {}) if isinstance(usage, dict) else {}
            tokens_used = customer_usage.get("api_tokens_used")
            if tokens_used is None:
                # Legacy fallback — do not prefer charges_usage[0].units
                tokens_used = customer_usage.get("total_amount_cents", "N/A")
            text = (
                f"Current Usage\n\n"
                f"Period: {customer_usage.get('from_datetime', 'N/A')} "
                f"to {customer_usage.get('to_datetime', 'N/A')}\n"
                f"Tokens used: {tokens_used}\n\n"
                f"For plan limits and billing, visit https://finedata.ai/billing"
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return format_api_error(e)

    return mcp


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(prog="finedata-mcp")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http", "sse"],
        default="stdio",
        help="MCP transport (default: stdio). 'http' is an alias for streamable-http.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    transport = args.transport
    if transport == "http":
        transport = "streamable-http"

    http_mode = transport in ("streamable-http", "sse")
    if args.host:
        import os

        os.environ["FINEDATA_MCP_HOST"] = args.host
    if args.port:
        import os

        os.environ["FINEDATA_MCP_PORT"] = str(args.port)

    try:
        mcp = create_mcp(http_mode=http_mode)
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    logger.info("Starting FineData MCP Server v%s (%s)", __version__, transport)
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
