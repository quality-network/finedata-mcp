"""FineData MCP Server — FastMCP (stdio + Streamable HTTP)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Annotated, Any, Optional

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import AnyHttpUrl, Field

from . import __version__
from .client import FineDataAPIError, FineDataClient, ScrapeOptions, get_client
from .client_ip import hop_headers_from_context
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

# Methods that may change something at the other end. They live in their own tool
# because a tool annotation describes the whole tool: `scrape_url` with
# `method="DELETE"` was annotated as one operation while being able to perform two
# very different ones, and a client deciding whether to ask the user first had no
# way to tell them apart.
UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


class _PassThroughTokenVerifier:
    """Accept API keys (fd_*) and OAuth JWTs issued for this resource.

    Verification of fd_* is deferred to the FineData API on first tool call.
    JWTs are verified locally when FINEDATA_JWT_SECRET is configured.

    Two audiences are accepted, and only two: this endpoint's own URL, which is
    what RFC 8707 mints, and the bare `"mcp"` that predates it. The gateway now
    puts both in every token, so this is the other half of that rollout — once no
    token carries `"mcp"` any more, drop it here and in `oauth_router._mint_access_token`.
    """

    LEGACY_AUDIENCE = "mcp"

    def __init__(
        self,
        jwt_secret: str | None,
        jwt_algorithm: str = "HS256",
        resource_url: str | None = None,
    ):
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.resource_url = (resource_url or "").rstrip("/") or None

    def _accepted_audiences(self) -> list[str]:
        if self.resource_url:
            return [self.resource_url, self.LEGACY_AUDIENCE]
        return [self.LEGACY_AUDIENCE]

    def _token_resource(self, aud: Any) -> str:
        """Which resource the token names, now that `aud` may be a list.

        Reading a list as a string used to yield `"mcp"` for a token that in fact
        named this endpoint, so the value reported upward said the opposite of the
        claim it came from.
        """
        if isinstance(aud, str):
            return aud
        if isinstance(aud, list):
            if self.resource_url and self.resource_url in aud:
                return self.resource_url
            for value in aud:
                if isinstance(value, str):
                    return value
        return self.LEGACY_AUDIENCE

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

                # python-jose takes one expected audience per call, so each accepted
                # value is tried in turn. A token for anything else fails all of them
                # and is refused — the point of checking the audience at all.
                payload = None
                last_error: Exception | None = None
                for audience in self._accepted_audiences():
                    try:
                        payload = jwt.decode(
                            token,
                            self.jwt_secret,
                            algorithms=[self.jwt_algorithm],
                            audience=audience,
                            options={"verify_aud": True},
                        )
                        break
                    except Exception as e:  # signature, expiry or wrong audience
                        last_error = e
                if payload is None:
                    raise last_error or ValueError("token rejected")
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
                    resource=self._token_resource(payload.get("aud")),
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


def _client(ctx: Context | None = None) -> FineDataClient:
    """Keyed API client for this tool call.

    The keyed client from ``get_client`` must not store the caller IP: that
    value is per-request. Hop headers are applied on a clone via
    ``with_call_headers`` and sent on each HTTP call, not on the shared
    httpx client.
    """
    return get_client(_resolve_api_key()).with_call_headers(hop_headers_from_context(ctx))


def _scrape_args(
    *,
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
) -> dict[str, Any]:
    """The wire payload shared by the read tool and the write tool.

    They differ by HTTP method and nothing else, so the request is built in one
    place: two copies of thirty options are how the same endpoint ends up with two
    dialects, one of which quietly lacks whatever was added last.
    """
    return {
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


async def _perform_scrape(
    url: str,
    args: dict[str, Any],
    ctx: Context | None = None,
) -> list[TextContent | ImageContent]:
    """Run one request and format the outcome, safe or unsafe alike.

    The failure text names the escalation step to try next, so it has to read the
    stealth flags back out of the payload rather than be told them again.
    """
    try:
        options = ScrapeOptions(**options_from_args(args))
        result = await _client(ctx).scrape(url, options)
        if not result.success:
            return format_scrape_failure(
                url,
                result,
                stealth_antibot=bool(args.get("stealth_antibot") or args.get("stealth_antibot_headful")),
                stealth_premium=bool(args.get("stealth_premium")),
                stealth_premium_headful=bool(args.get("stealth_premium_headful")),
                use_isp=bool(args.get("use_isp")),
                use_residential=bool(args.get("use_residential")),
                use_mobile=bool(args.get("use_mobile")),
            )
        return format_scrape_success(url, result)
    except FineDataAPIError as e:
        return format_api_error(e)
    except Exception as e:
        return format_api_error(e)


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
            # nine tools need all three; per-path scope checks stay on the gateway.
            required_scopes=["scrape:write", "jobs:read", "usage:read"],
            client_registration_options=ClientRegistrationOptions(
                enabled=False,  # DCR lives on gateway AS
                valid_scopes=["scrape:write", "jobs:read", "usage:read"],
                default_scopes=["scrape:write", "jobs:read", "usage:read"],
            ),
        )
        token_verifier = _PassThroughTokenVerifier(
            cfg.jwt_secret, cfg.jwt_algorithm, resource_url=cfg.resource_url
        )
    elif http_mode:
        # HTTP without full OAuth metadata still accepts Bearer via custom middleware path:
        # FastMCP requires auth settings for protected resource; if missing, rely on env key.
        token_verifier = _PassThroughTokenVerifier(
            cfg.jwt_secret, cfg.jwt_algorithm, resource_url=cfg.resource_url
        )

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
            "Read one web page and return its content, by default as markdown: an "
            "article, a product page, a listing, a catalog page, or a site's own "
            "search-results URL. Always a GET request; the target is left unmodified.\n\n"
            'REQUIRED INPUT: call this tool with {"url":"https://..."}; put search '
            "terms in that URL's encoded query string (e.g. .../search?q=wireless%20headphones). "
            'It does not accept an argument named "query" or a bare '
            "natural-language search phrase — to look something up on a site, open "
            "that site's search URL.\n\n"
            "To send POST, PUT, PATCH or DELETE — submitting a form, calling a write "
            "API — use send_http_request instead.\n\n"
            "Stealth modes consume more tokens than a plain request. Exact rates "
            "are in the documentation and via the get_usage tool."
        ),
        annotations=ToolAnnotations(
            title="Scrape URL",
            # Read-only now that the method is fixed at GET: the request leaves the
            # target as it found it. Tokens are still spent, but that is our own
            # meter — treating a paid read as a write would put this tool in the same
            # class as cancel_job and make every page fetch ask for confirmation.
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def scrape_url(
        url: Annotated[
            str,
            Field(
                description=(
                    "REQUIRED absolute HTTP(S) URL to fetch, including any encoded "
                    "search parameters. Example: "
                    "https://api.example.com/items?search=wireless%20headphones&limit=30. "
                    'Use the argument name "url", never "query".'
                ),
                pattern=r"^https?://",
                examples=["https://example.com/"],
            ),
        ],
        headers: Optional[dict[str, str]] = None,
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
        return await _perform_scrape(
            url,
            _scrape_args(
                headers=headers,
                timeout=timeout,
                max_retries=max_retries,
                auto_retry=auto_retry,
                use_antibot=use_antibot,
                tls_profile=tls_profile,
                use_isp=use_isp,
                use_residential=use_residential,
                use_mobile=use_mobile,
                proxy_sticky=proxy_sticky,
                proxy_country=proxy_country,
                proxy_profile_id=proxy_profile_id,
                stealth_antibot=stealth_antibot,
                stealth_antibot_headful=stealth_antibot_headful,
                stealth_new=stealth_new,
                stealth_premium=stealth_premium,
                stealth_premium_headful=stealth_premium_headful,
                use_js_render=use_js_render,
                js_wait_for=js_wait_for,
                js_scroll=js_scroll,
                js_actions=js_actions,
                solve_captcha=solve_captcha,
                session_id=session_id,
                session_ttl=session_ttl,
                formats=formats,
                only_main_content=only_main_content,
                extract_rules=extract_rules,
                extract_schema=extract_schema,
                extract_prompt=extract_prompt,
                ai_content_mode=ai_content_mode,
            ),
            ctx,
        )

    @mcp.tool(
        title="Send HTTP Request",
        description=(
            "Send a POST, PUT, PATCH or DELETE request through the same rendering "
            "and proxy pipeline, and return the response as markdown by default. Use this "
            "for submitting a form, calling a write API or deleting a resource.\n\n"
            "This request may change something at the other end, which is why it is a "
            "separate tool: to read a page, use scrape_url.\n\n"
            'Send the payload as a string in "body" and set the matching '
            '"headers", e.g. {"Content-Type": "application/json"}.\n\n'
            "Stealth modes consume more tokens than a plain request. Exact rates "
            "are in the documentation and via the get_usage tool."
        ),
        annotations=ToolAnnotations(
            title="Send HTTP Request",
            readOnlyHint=False,
            # The target decides what a POST or a DELETE does, and we cannot know:
            # claiming otherwise is what a client would rely on to skip asking.
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def send_http_request(
        url: Annotated[
            str,
            Field(
                description="REQUIRED absolute HTTP(S) URL to send the request to.",
                pattern=r"^https?://",
                examples=["https://api.example.com/items"],
            ),
        ],
        method: Annotated[
            str,
            Field(
                description=(
                    "REQUIRED HTTP method: POST, PUT, PATCH or DELETE. "
                    "GET belongs to scrape_url."
                ),
                examples=["POST"],
            ),
        ],
        body: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
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
        requested = (method or "").strip().upper()
        if requested not in UNSAFE_METHODS:
            # Refused rather than passed through: accepting GET here would restore
            # the very mix the split removed, and a tool marked destructive would be
            # doing safe reads under a warning nobody can then trust.
            return [
                TextContent(
                    type="text",
                    text=(
                        f"send_http_request accepts {', '.join(UNSAFE_METHODS)}. "
                        f'Got "{method}". Use scrape_url to read a page with GET.'
                    ),
                )
            ]

        return await _perform_scrape(
            url,
            _scrape_args(
                method=requested,
                body=body,
                headers=headers,
                timeout=timeout,
                max_retries=max_retries,
                auto_retry=auto_retry,
                use_antibot=use_antibot,
                tls_profile=tls_profile,
                use_isp=use_isp,
                use_residential=use_residential,
                use_mobile=use_mobile,
                proxy_sticky=proxy_sticky,
                proxy_country=proxy_country,
                proxy_profile_id=proxy_profile_id,
                stealth_antibot=stealth_antibot,
                stealth_antibot_headful=stealth_antibot_headful,
                stealth_new=stealth_new,
                stealth_premium=stealth_premium,
                stealth_premium_headful=stealth_premium_headful,
                use_js_render=use_js_render,
                js_wait_for=js_wait_for,
                js_scroll=js_scroll,
                js_actions=js_actions,
                solve_captcha=solve_captcha,
                session_id=session_id,
                session_ttl=session_ttl,
                formats=formats,
                only_main_content=only_main_content,
                extract_rules=extract_rules,
                extract_schema=extract_schema,
                extract_prompt=extract_prompt,
                ai_content_mode=ai_content_mode,
            ),
            ctx,
        )

    @mcp.tool(
        title="Scrape Async",
        description=(
            "Read a web page like scrape_url, but as an async job — for a slow page or heavy stealth. "
            "Submit an async scrape job (long-running / heavy stealth). "
            "Defaults formats=['markdown']. Poll with get_job_status. "
            "Always a GET request: POST, PUT, PATCH and DELETE go through "
            "send_http_request, which runs synchronously."
        ),
        annotations=ToolAnnotations(
            title="Scrape Async",
            # Not read-only: it creates a job that then exists, can be polled and
            # cancelled. The page it will read is left alone, hence not destructive.
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def scrape_async(
        url: str,
        headers: Optional[dict[str, str]] = None,
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
            job = await _client(ctx).scrape_async(url, options, callback_url=callback_url)
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
        description="Poll one async job by the job_id returned from scrape_async or batch_scrape. Not for finding pages or products. On completed, returns markdown (not raw HTML).",
        annotations=ToolAnnotations(
            title="Get Job Status",
            readOnlyHint=True,
            # Spelled out although the spec defaults it: both connector directories
            # check for the field itself, and an absent hint reads as unknown.
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_job_status(job_id: str, ctx: Context | None = None) -> list[TextContent | ImageContent]:
        try:
            job = await _client(ctx).get_job_status(job_id)
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
            data = await _client(ctx).cancel_job(job_id)
            return [TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return format_api_error(e)

    @mcp.tool(
        title="List Jobs",
        description="List this account's recent async scrape jobs (from scrape_async / batch_scrape). Not a history of synchronous scrape_url requests.",
        annotations=ToolAnnotations(
            title="List Jobs",
            readOnlyHint=True,
            # Spelled out although the spec defaults it: both connector directories
            # check for the field itself, and an absent hint reads as unknown.
            destructiveHint=False,
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
            data = await _client(ctx).list_jobs(limit=limit, offset=offset)
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
            "Read up to 100 web pages in one batch (e.g. many product or listing URLs). `urls` may be a list of strings "
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

            # A per-URL object is free-form, so `{"url": ..., "method": "DELETE"}`
            # used to reach the API through a tool whose schema never mentions a
            # method — the mixed-method problem the split removed, in the one place
            # a reviewer could not see it. Refused rather than quietly downgraded to
            # GET: a caller who asked to delete a hundred URLs should hear about it.
            unsafe = [
                item.get("url")
                for item in urls
                if isinstance(item, dict)
                and str(item.get("method") or "GET").strip().upper() != "GET"
            ]
            if unsafe:
                return [
                    TextContent(
                        type="text",
                        text=(
                            "batch_scrape only reads with GET. "
                            f"{len(unsafe)} entr{'y' if len(unsafe) == 1 else 'ies'} asked for "
                            "another method; send those one at a time with send_http_request."
                        ),
                    )
                ]

            requests: list[dict[str, Any]] = []
            for item in urls:
                if isinstance(item, str):
                    requests.append({"url": item, **base_public})
                elif isinstance(item, dict) and item.get("url"):
                    item = {k: v for k, v in item.items() if k not in ("method", "body")}
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

            result = await _client(ctx).batch_scrape(requests, callback_url=callback_url)
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
            # Spelled out although the spec defaults it: both connector directories
            # check for the field itself, and an absent hint reads as unknown.
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_batch_status(batch_id: str, ctx: Context | None = None) -> list[TextContent]:
        try:
            data = await _client(ctx).get_batch_status(batch_id)
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
            "Current period token usage (api_tokens_used). Not a request log. "
            "Does not include plan token limit — check the billing dashboard."
        ),
        annotations=ToolAnnotations(
            title="Get Usage",
            readOnlyHint=True,
            # Spelled out although the spec defaults it: both connector directories
            # check for the field itself, and an absent hint reads as unknown.
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_usage(ctx: Context | None = None) -> list[TextContent]:
        try:
            usage = await _client(ctx).get_usage()
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
