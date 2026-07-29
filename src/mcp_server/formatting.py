"""Format scrape results for MCP tool responses."""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.types import ImageContent, TextContent

from .client import CONTENT_TRUNCATE_CHARS, ScrapeResult
from .escalation import suggest_next_step


def truncate_text(text: str, limit: int = CONTENT_TRUNCATE_CHARS) -> str:
    if not text or len(text) <= limit:
        return text or ""
    omitted = len(text) - limit
    return (
        text[:limit]
        + f"\n\n...[truncated: {omitted} chars omitted; "
        + "re-request with only_main_content=true or extract_prompt for a smaller payload]"
    )


def _content_from_result(result: ScrapeResult) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    if data.get("markdown"):
        return truncate_text(str(data["markdown"]))
    if data.get("text"):
        return truncate_text(str(data["text"]))
    return truncate_text(result.body or "")


def _screenshot_b64(result: ScrapeResult) -> str | None:
    data = result.data if isinstance(result.data, dict) else {}
    shot = data.get("screenshot")
    if isinstance(shot, str) and shot:
        # Strip data-url prefix if present
        if "," in shot and shot.startswith("data:"):
            return shot.split(",", 1)[1]
        return shot
    meta = result.meta or {}
    shots = meta.get("screenshots")
    if isinstance(shots, list) and shots and isinstance(shots[0], str):
        return shots[0]
    return None


def format_scrape_success(
    url: str,
    result: ScrapeResult,
    *,
    include_screenshot: bool = True,
) -> list[TextContent | ImageContent]:
    parts = [
        f"Successfully scraped {url}",
        f"Status: {result.status_code}",
        f"Tokens used: {result.tokens_used}",
    ]
    if result.captcha_detected:
        parts.append(f"Captcha detected: {result.captcha_type}")
        parts.append(f"Captcha solved: {'Yes' if result.captcha_solved else 'No'}")
    if result.meta.get("response_time_ms") or result.meta.get("elapsed_ms"):
        ms = result.meta.get("response_time_ms") or result.meta.get("elapsed_ms")
        parts.append(f"Response time: {ms}ms")
    if result.meta.get("strategy") or result.meta.get("strategy_name"):
        parts.append(
            "Note: gateway strategy may have overridden engine/proxy; "
            "trust tokens_used above."
        )

    parts.append("")
    parts.append("--- Content ---")
    parts.append(_content_from_result(result))

    data = result.data if isinstance(result.data, dict) else {}
    if data.get("extract") is not None:
        parts.append("")
        parts.append("--- Extracted Data ---")
        parts.append(json.dumps(data["extract"], indent=2, ensure_ascii=False))
    if data.get("links"):
        links = data["links"]
        if isinstance(links, list) and links:
            parts.append("")
            parts.append(f"--- Links ({len(links)}) ---")
            parts.append("\n".join(str(x) for x in links[:200]))

    out: list[TextContent | ImageContent] = [
        TextContent(type="text", text="\n".join(parts))
    ]
    if include_screenshot:
        b64 = _screenshot_b64(result)
        if b64:
            # Validate base64 lightly
            try:
                base64.b64decode(b64[:64] + "==", validate=False)
                out.append(ImageContent(type="image", data=b64, mimeType="image/png"))
            except Exception:
                out.append(
                    TextContent(
                        type="text",
                        text="[screenshot present but could not be decoded as ImageContent]",
                    )
                )
    return out


def format_scrape_failure(
    url: str,
    result: ScrapeResult,
    *,
    stealth_antibot: bool = False,
    stealth_premium: bool = False,
    stealth_premium_headful: bool = False,
    use_isp: bool = False,
    use_residential: bool = False,
    use_mobile: bool = False,
) -> list[TextContent]:
    error_msg = result.error or f"Request failed with status {result.status_code}"
    block_reason = (result.meta or {}).get("block_reason")
    if block_reason:
        error_msg += f" (block_reason: {block_reason})"
    hint = suggest_next_step(
        stealth_antibot=stealth_antibot,
        stealth_premium=stealth_premium,
        stealth_premium_headful=stealth_premium_headful,
        use_isp=use_isp,
        use_residential=use_residential,
        use_mobile=use_mobile,
    )
    text = f"Error scraping {url}: {error_msg}\n\nNext step: {hint}"
    return [TextContent(type="text", text=text)]


def format_api_error(exc: Exception) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {exc}")]


def options_from_args(arguments: dict[str, Any], *, async_formats: bool = False) -> dict[str, Any]:
    """Map public MCP args → ScrapeOptions kwargs (internal stealth flags)."""
    formats = arguments.get("formats")
    if formats is None and not async_formats:
        formats = ["markdown"]
    if formats is None and async_formats:
        formats = ["markdown"]
    if async_formats and isinstance(formats, list):
        formats = [f for f in formats if f not in ("csv", "xlsx")]

    return {
        "method": arguments.get("method", "GET"),
        "headers": arguments.get("headers") or {},
        "body": arguments.get("body"),
        "timeout": arguments.get("timeout", 120),
        "max_retries": arguments.get("max_retries", 5),
        "auto_retry": arguments.get("auto_retry", True),
        "tls_profile": arguments.get("tls_profile", "chrome136"),
        "use_antibot": arguments.get("use_antibot", True),
        "use_js_render": arguments.get("use_js_render", False),
        "use_isp": arguments.get("use_isp", False),
        "use_residential": arguments.get("use_residential", False),
        "use_mobile": arguments.get("use_mobile", False),
        "proxy_sticky": arguments.get("proxy_sticky", False),
        "proxy_country": arguments.get("proxy_country"),
        "proxy_profile_id": arguments.get("proxy_profile_id"),
        "use_undetected": arguments.get("stealth_antibot", False),
        "use_nodriver": arguments.get("stealth_antibot_headful", False),
        "use_patchright": arguments.get("stealth_new", False),
        "use_botbrowser": arguments.get("stealth_premium", False),
        "use_botbrowser_headful": arguments.get("stealth_premium_headful", False),
        "js_wait_for": arguments.get("js_wait_for", "networkidle"),
        "js_scroll": arguments.get("js_scroll", False),
        "js_actions": arguments.get("js_actions"),
        "solve_captcha": arguments.get("solve_captcha", False),
        "session_id": arguments.get("session_id"),
        "session_ttl": arguments.get("session_ttl", 1800),
        "formats": formats,
        "only_main_content": arguments.get("only_main_content", False),
        "extract_rules": arguments.get("extract_rules"),
        "extract_schema": arguments.get("extract_schema"),
        "extract_prompt": arguments.get("extract_prompt"),
        "ai_content_mode": arguments.get("ai_content_mode", "full"),
    }
