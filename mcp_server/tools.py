"""
MCP Tool definitions for FineData.

Defines the tools that AI agents can use to interact with FineData API.
"""

from typing import Any
from mcp.types import Tool, TextContent

from .client import get_client, ScrapeOptions


# Tool definitions
TOOLS = [
    Tool(
        name="scrape_url",
        description="""Scrape content from any web page with advanced antibot bypass.

Features:
- TLS fingerprinting (Chrome, Firefox, Safari profiles)
- JavaScript rendering for SPAs (React, Vue, Angular)
- Captcha solving (reCAPTCHA, hCaptcha, Cloudflare Turnstile)
- Residential and mobile proxy support
- Automatic retry with smart detection

Use cases:
- Extract text/HTML from any website
- Scrape JavaScript-rendered content
- Access pages behind Cloudflare or other protections
- Get data from pages with captchas

Token costs:
- Base request: 1 token
- Antibot bypass: +2 tokens
- JS rendering: +5 tokens  
- Nodriver (max stealth): +6 tokens
- Residential proxy: +3 tokens
- Captcha solving: +10 tokens""",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to scrape (required)",
                },
                "use_js_render": {
                    "type": "boolean",
                    "description": "Enable JavaScript rendering with Playwright. Use for SPAs, React, Vue sites. Default: false",
                    "default": False,
                },
                "use_residential": {
                    "type": "boolean",
                    "description": "Use residential proxy instead of datacenter. Better for protected sites. Default: false",
                    "default": False,
                },
                "use_mobile": {
                    "type": "boolean",
                    "description": "Use mobile proxy (Russian carriers: MTS, Megafon, Beeline). Best for Russian sites. Default: false",
                    "default": False,
                },
                "use_undetected": {
                    "type": "boolean",
                    "description": "Use Undetected Chrome for antibot bypass. Default: false",
                    "default": False,
                },
                "use_nodriver": {
                    "type": "boolean",
                    "description": "Use Nodriver (better than UC) - no WebDriver markers, direct CDP. Best for maximum stealth. Default: false",
                    "default": False,
                },
                "solve_captcha": {
                    "type": "boolean",
                    "description": "Automatically detect and solve captchas. Default: false",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (5-300). Default: 180",
                    "default": 180,
                    "minimum": 5,
                    "maximum": 300,
                },
                "js_wait_for": {
                    "type": "string",
                    "description": "Wait strategy for JS rendering: 'networkidle', 'load', 'domcontentloaded', or 'selector:.css-selector'. Default: networkidle",
                    "default": "networkidle",
                },
                "session_id": {
                    "type": "string",
                    "description": "Sticky session ID - all requests with same ID use same proxy IP. Good for auth flows.",
                },
                "tls_profile": {
                    "type": "string",
                    "description": "TLS fingerprint profile. Options: 'chrome120', 'chrome124', 'firefox121', 'safari17', 'vip' (premium auto-rotation), 'vip:ios', 'vip:android', 'vip:windows', 'vip:mobile'. Default: chrome124",
                    "default": "chrome124",
                },
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="scrape_async",
        description="""Submit an async scraping job for long-running requests.

Use this for:
- Pages that take > 60 seconds to load
- Heavy JS rendering tasks
- When you don't need immediate results
- Batch processing workflows

Returns a job_id that you can poll with get_job_status.""",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to scrape",
                },
                "use_js_render": {
                    "type": "boolean",
                    "description": "Enable JavaScript rendering",
                    "default": False,
                },
                "use_residential": {
                    "type": "boolean",
                    "description": "Use residential proxy",
                    "default": False,
                },
                "use_undetected": {
                    "type": "boolean",
                    "description": "Use Undetected Chrome",
                    "default": False,
                },
                "solve_captcha": {
                    "type": "boolean",
                    "description": "Auto-solve captchas",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 120,
                },
                "callback_url": {
                    "type": "string",
                    "description": "Webhook URL to receive result when job completes",
                },
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="get_job_status",
        description="""Get the status of an async scraping job.

Statuses:
- pending: Job is queued
- processing: Worker is scraping
- completed: Success, result available
- failed: Error occurred
- cancelled: Job was cancelled

Poll this endpoint until status is 'completed' or 'failed'.""",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID returned from scrape_async",
                },
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="batch_scrape",
        description="""Scrape multiple URLs in a single batch request.

Benefits:
- Submit up to 100 URLs at once
- Parallel processing for speed
- Single webhook notification when all complete

Returns a batch_id and list of job_ids for tracking.""",
        inputSchema={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to scrape (max 100)",
                    "maxItems": 100,
                },
                "use_js_render": {
                    "type": "boolean",
                    "description": "Enable JS rendering for all URLs",
                    "default": False,
                },
                "use_residential": {
                    "type": "boolean",
                    "description": "Use residential proxy for all URLs",
                    "default": False,
                },
                "callback_url": {
                    "type": "string",
                    "description": "Webhook URL for batch completion",
                },
            },
            "required": ["urls"],
        },
    ),
    Tool(
        name="get_usage",
        description="""Get current API usage and token statistics.

Returns:
- Tokens used this billing period
- Token limit for your plan
- Usage breakdown by feature""",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


async def handle_scrape_url(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle scrape_url tool call."""
    url = arguments.get("url")
    if not url:
        return [TextContent(type="text", text="Error: url is required")]
    
    options = ScrapeOptions(
        use_js_render=arguments.get("use_js_render", False),
        use_residential=arguments.get("use_residential", False),
        use_mobile=arguments.get("use_mobile", False),
        use_undetected=arguments.get("use_undetected", False),
        use_nodriver=arguments.get("use_nodriver", False),
        solve_captcha=arguments.get("solve_captcha", False),
        timeout=arguments.get("timeout", 180),
        js_wait_for=arguments.get("js_wait_for", "networkidle"),
        session_id=arguments.get("session_id"),
        tls_profile=arguments.get("tls_profile", "chrome124"),
    )
    
    client = get_client()
    result = await client.scrape(url, options)
    
    if not result.success:
        error_msg = result.error or f"Request failed with status {result.status_code}"
        if result.meta.get("block_reason"):
            error_msg += f" (block_reason: {result.meta['block_reason']})"
        return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    # Format response
    response_parts = [
        f"Successfully scraped {url}",
        f"Status: {result.status_code}",
        f"Tokens used: {result.tokens_used}",
    ]
    
    if result.captcha_detected:
        response_parts.append(f"Captcha detected: {result.captcha_type}")
        if result.captcha_solved:
            response_parts.append("Captcha solved: Yes")
    
    if result.meta.get("response_time_ms"):
        response_parts.append(f"Response time: {result.meta['response_time_ms']}ms")
    
    response_parts.append("")
    response_parts.append("--- Content ---")
    response_parts.append(result.body)
    
    return [TextContent(type="text", text="\n".join(response_parts))]


async def handle_scrape_async(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle scrape_async tool call."""
    url = arguments.get("url")
    if not url:
        return [TextContent(type="text", text="Error: url is required")]
    
    options = ScrapeOptions(
        use_js_render=arguments.get("use_js_render", False),
        use_residential=arguments.get("use_residential", False),
        use_mobile=arguments.get("use_mobile", False),
        use_undetected=arguments.get("use_undetected", False),
        use_nodriver=arguments.get("use_nodriver", False),
        solve_captcha=arguments.get("solve_captcha", False),
        timeout=arguments.get("timeout", 180),
    )
    
    client = get_client()
    job = await client.scrape_async(
        url,
        options,
        callback_url=arguments.get("callback_url"),
    )
    
    response = f"""Async job submitted successfully.

Job ID: {job.job_id}
Status: {job.status}
URL: {job.url}
Created: {job.created_at}

Use get_job_status with job_id="{job.job_id}" to check progress."""
    
    return [TextContent(type="text", text=response)]


async def handle_get_job_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_job_status tool call."""
    job_id = arguments.get("job_id")
    if not job_id:
        return [TextContent(type="text", text="Error: job_id is required")]
    
    client = get_client()
    job = await client.get_job_status(job_id)
    
    response_parts = [
        f"Job ID: {job.job_id}",
        f"Status: {job.status}",
        f"URL: {job.url}",
        f"Created: {job.created_at}",
    ]
    
    if job.error:
        response_parts.append(f"Error: {job.error}")
    
    if job.result:
        response_parts.append("")
        response_parts.append("--- Result ---")
        response_parts.append(f"Success: {job.result.success}")
        response_parts.append(f"Status code: {job.result.status_code}")
        response_parts.append(f"Tokens used: {job.result.tokens_used}")
        response_parts.append("")
        response_parts.append("--- Content ---")
        response_parts.append(job.result.body)
    
    return [TextContent(type="text", text="\n".join(response_parts))]


async def handle_batch_scrape(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle batch_scrape tool call."""
    urls = arguments.get("urls", [])
    if not urls:
        return [TextContent(type="text", text="Error: urls array is required")]
    
    if len(urls) > 100:
        return [TextContent(type="text", text="Error: Maximum 100 URLs per batch")]
    
    options = ScrapeOptions(
        use_js_render=arguments.get("use_js_render", False),
        use_residential=arguments.get("use_residential", False),
        use_mobile=arguments.get("use_mobile", False),
    )
    
    client = get_client()
    result = await client.batch_scrape(
        urls,
        options,
        callback_url=arguments.get("callback_url"),
    )
    
    response = f"""Batch submitted successfully.

Batch ID: {result.get('batch_id')}
Total jobs: {result.get('total_jobs')}
Status: {result.get('status')}

Job IDs:
{chr(10).join(f"  - {jid}" for jid in result.get('job_ids', []))}

Use get_job_status to check individual job progress."""
    
    return [TextContent(type="text", text=response)]


async def handle_get_usage(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_usage tool call."""
    client = get_client()
    usage = await client.get_usage()
    
    customer_usage = usage.get("customer_usage", {})
    charges = customer_usage.get("charges_usage", [{}])
    
    tokens_used = "0"
    if charges and len(charges) > 0:
        tokens_used = charges[0].get("units", "0")
    
    response = f"""Current Usage

Period: {customer_usage.get('from_datetime', 'N/A')} to {customer_usage.get('to_datetime', 'N/A')}
Tokens used: {tokens_used}

For detailed billing, visit https://finedata.ai/billing"""
    
    return [TextContent(type="text", text=response)]


# Tool handler mapping
TOOL_HANDLERS = {
    "scrape_url": handle_scrape_url,
    "scrape_async": handle_scrape_async,
    "get_job_status": handle_get_job_status,
    "batch_scrape": handle_batch_scrape,
    "get_usage": handle_get_usage,
}


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """
    Call a tool by name with given arguments.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        List of TextContent with the result
    """
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]
    
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
