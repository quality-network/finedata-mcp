"""Canonical escalation ladder for agent tool instructions.

Source of truth: docs/mcp-escalation-ladder-2026-07-29.md
(recalculated from scripts/benchmark_stealth_premium_proxy.json).
"""

from __future__ import annotations

# Approximate costs assume default use_antibot=True (+2).
# Always trust tokens_used in the API response — gateway strategy registry
# may override the engine and force residential/mobile for some domains.

ESCALATION_LADDER = """
Escalation ladder (cheapest → hardest). Prefer the lowest step that works
(success rates from the 2026-07 benchmark, 15 hard targets):

1. base — TLS antibot only (~3 tokens, 7% on hard targets). Simple static pages.
2. stealth_antibot + datacenter (+7 → ~10 tokens, 27%). Cloudflare / DataDome class.
3. stealth_premium + use_isp=true (~25 tokens, 60%). DEFAULT for protected sites.
   Premium on datacenter IPs is much weaker (13%) — pair premium with ISP.
4. stealth_premium_headful + use_isp=true (~34 tokens, 47%). Hardest challenges,
   when step 3 returns a block or empty page.
5. use_residential (+3, 33%) / use_mobile (+4) — geo targeting and IP-sensitive
   sites ONLY, not a default.

Do NOT start with residential. Escalate ISP before residential.
Zillow/Nordstrom/Google/G2 class sites usually need step 3 (premium + ISP).

IMPORTANT: FineData gateway may apply a domain strategy that overrides your
requested engine/proxy. Quoted costs are estimates — use tokens_used from the response.
""".strip()

SERVER_INSTRUCTIONS = f"""
FineData MCP — scrape any website for AI agents (markdown by default).

{ESCALATION_LADDER}

Tools: scrape_url (sync), scrape_async + get_job_status / cancel_job / list_jobs,
batch_scrape + get_batch_status, get_usage.

On 403 / challenge / block_reason failures, retry with the next ladder step.
Prefer formats=['markdown']. Large pages are truncated (~60k chars) with a note.
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
