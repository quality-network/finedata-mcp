"""Per-failure escalation hints for tool responses.

This module intentionally does not describe the escalation ladder in the
server or tool *descriptions* — those are read on every list-tools call and
must stay narrow (what a tool does, when to use it, what it returns), per the
Claude Connectors Directory review requirements. The ladder knowledge instead
surfaces exactly when it is actionable: `suggest_next_step` is called from
`formatting.format_scrape_failure` and appended to the error text of a failed
scrape, naming the next stealth/proxy combination to try.

Source of truth for the underlying data: docs/mcp-escalation-ladder-2026-07-29.md
(recalculated from scripts/benchmark_stealth_premium_proxy.json).
"""

from __future__ import annotations

# Approximate costs assume default use_antibot=True (+2).
# Always trust tokens_used in the API response — gateway strategy registry
# may override the engine and force residential/mobile for some domains.

SERVER_INSTRUCTIONS = """
FineData retrieves public or user-authorized web pages and returns AI-ready
markdown or structured data.

scrape_url reads one URL synchronously (GET only). send_http_request sends
POST/PUT/PATCH/DELETE through the same pipeline, for form submissions or write
APIs. scrape_async and batch_scrape submit longer-running jobs — one URL or up
to 100 — polled with get_job_status, get_batch_status, list_jobs and
cancel_job. get_usage reports token consumption for the current period.

Every response reports tokens_used; a failed request is not billed. Formats
default to markdown; large pages are truncated (~60k chars) with a note.
""".strip()

NEXT_STEP_HINTS = [
    ("base", "Retry with stealth_antibot=true (datacenter, ~10 tokens)."),
    ("stealth_antibot", "Retry with stealth_premium=true and use_isp=true (~25 tokens)."),
    ("stealth_premium", "Retry with stealth_premium=true and use_isp=true (~25 tokens)."),
    (
        "stealth_premium_isp",
        "Retry with stealth_premium_headful=true and use_isp=true (~34 tokens).",
    ),
    (
        "stealth_premium_headful",
        "Retry with use_residential=true or use_mobile=true only if geo/IP-sensitive.",
    ),
]


def suggest_next_step(
    *,
    stealth_antibot: bool = False,
    stealth_premium: bool = False,
    stealth_premium_headful: bool = False,
    use_isp: bool = False,
    use_residential: bool = False,
    use_mobile: bool = False,
) -> str:
    if use_residential or use_mobile:
        return "Already on residential/mobile. Try a different proxy_country or proxy_sticky=true."
    if stealth_premium_headful:
        return NEXT_STEP_HINTS[-1][1]
    if stealth_premium and use_isp:
        return NEXT_STEP_HINTS[3][1]
    if stealth_premium:
        return NEXT_STEP_HINTS[2][1]
    if stealth_antibot:
        return NEXT_STEP_HINTS[1][1]
    return NEXT_STEP_HINTS[0][1]
