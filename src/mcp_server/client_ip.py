"""Extract the real client IP from an incoming MCP HTTP request.

This package is published independently of the gateway and must not import
from it. The hop-selection rules are the same as
``gateway/utils/network.py::get_client_ip`` when forwarded headers are
trusted (our ingress is the last hop on ``mcp.finedata.ai``):

1. ``CF-Connecting-IP`` if present (Cloudflare overwrites it; unused on
   ``mcp.finedata.ai``, which is not behind Cloudflare).
2. The RIGHTMOST ``X-Forwarded-For`` hop — the address our ingress appended,
   not the left-most client-supplied entry.
3. ``X-Real-IP``.
4. The socket peer.

stdio (local launch) has no HTTP request: callers get ``None`` and must not
crash.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional

# Internal hop header. Not part of the public scrape schema.
MCP_CLIENT_IP_HEADER = "X-FineData-MCP-Client-IP"


def rightmost_forwarded_hop(forwarded_for: str) -> Optional[str]:
    """Return the last non-empty XFF hop, or None.

    Same rule as gateway: the rightmost value is the one our own proxy
    appended. The leftmost hop is attacker-controlled.
    """
    hops = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    return hops[-1] if hops else None


def _header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        if isinstance(headers, dict):
            lowered = {str(k).lower(): v for k, v in headers.items()}
            value = lowered.get(name.lower(), "")
            return value.strip() if isinstance(value, str) else ""
        return ""
    value = getter(name, "")
    if value is None:
        return ""
    return str(value).strip()


def extract_client_ip(request: Any) -> Optional[str]:
    """Best-effort client IP from a Starlette-like request. None if unusable."""
    if request is None:
        return None

    headers = getattr(request, "headers", None)
    cf_ip = _header(headers, "CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    forwarded = _header(headers, "X-Forwarded-For")
    hop = rightmost_forwarded_hop(forwarded) if forwarded else None
    if hop:
        return hop

    real_ip = _header(headers, "X-Real-IP")
    if real_ip:
        return real_ip

    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    if isinstance(host, str) and host.strip():
        return host.strip()
    return None


def http_request_from_context(ctx: Any) -> Any | None:
    """Starlette Request from FastMCP Context, or None in stdio / no-request.

    Official MCP SDK 1.26.0 (``mcp.server.fastmcp``) has no ``get_http_request()``
    — that helper belongs to the unrelated Prefect ``fastmcp`` package. The
    request is ``RequestContext.request``, reached via
    ``Context.request_context``. The property raises ``ValueError`` when no
    request context exists; we read ``_request_context`` first so stdio does
    not throw.
    """
    if ctx is None:
        return None
    rc = getattr(ctx, "_request_context", None)
    if rc is None:
        try:
            rc = ctx.request_context
        except (ValueError, AttributeError, LookupError):
            return None
    if rc is None:
        return None
    request = getattr(rc, "request", None)
    if request is None or getattr(request, "headers", None) is None:
        return None
    return request


def extract_client_ip_from_context(ctx: Any) -> Optional[str]:
    """Client IP for this tool call, or None when there is no HTTP request."""
    request = http_request_from_context(ctx)
    if request is None:
        return None
    return extract_client_ip(request)


def hop_headers_from_context(ctx: Any) -> dict[str, str]:
    """Per-call headers to send to the gateway. Empty in stdio."""
    ip = extract_client_ip_from_context(ctx)
    if not ip:
        return {}
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return {}
    return {MCP_CLIENT_IP_HEADER: ip}
