# FineData MCP Server

MCP (Model Context Protocol) server for [FineData](https://finedata.ai) web scraping API.

Enables AI agents like Claude, Cursor, and GPT to scrape any website with:

- **Antibot Bypass** - Cloudflare, DataDome, PerimeterX, and more
- **JavaScript Rendering** - Full browser rendering with Playwright
- **Captcha Solving** - reCAPTCHA, hCaptcha, Cloudflare Turnstile, Yandex
- **Proxy Rotation** - 87K+ datacenter, residential, and mobile proxies
- **Smart Retry** - Automatic retries with block detection

## Installation

### Using uvx (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run directly with uvx
FINEDATA_API_KEY=fd_xxx uvx finedata-mcp
```

### Using pip

```bash
pip install finedata-mcp

# Run
FINEDATA_API_KEY=fd_xxx finedata-mcp
```

### Using npx

```bash
npx -y @finedata/mcp-server
```

## Configuration

### Cursor IDE

**Step 1:** Open Cursor Settings → MCP

Or create/edit `~/.cursor/mcp.json`:

**macOS/Linux:**
```bash
mkdir -p ~/.cursor && nano ~/.cursor/mcp.json
```

**Windows:**
```
%USERPROFILE%\.cursor\mcp.json
```

**Step 2:** Add FineData MCP server:

```json
{
  "mcpServers": {
    "finedata": {
      "command": "uvx",
      "args": ["finedata-mcp"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key_here"
      }
    }
  }
}
```

**Step 3:** Restart Cursor

**Step 4:** Test by asking the agent:
> "Scrape https://example.com and show me the title"

#### Alternative: Using npx (if uv not installed)

```json
{
  "mcpServers": {
    "finedata": {
      "command": "npx",
      "args": ["-y", "@finedata/mcp-server"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key_here"
      }
    }
  }
}
```

> **Note:** npx requires Python 3.10+ and uv/pipx installed. uvx is recommended.

---

### Claude Desktop

**Step 1:** Open config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Step 2:** Add MCP server:

```json
{
  "mcpServers": {
    "finedata": {
      "command": "uvx",
      "args": ["finedata-mcp"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key_here"
      }
    }
  }
}
```

**Step 3:** Restart Claude Desktop

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FINEDATA_API_KEY` | Yes | Your FineData API key |
| `FINEDATA_API_URL` | No | API URL (default: https://api.finedata.ai) |
| `FINEDATA_TIMEOUT` | No | Default timeout in seconds (default: 60) |

## Available Tools

### scrape_url

Scrape content from any web page with antibot bypass.

```
scrape_url(
  url: "https://example.com",
  use_js_render: false,      # Enable Playwright for SPAs
  use_residential: false,    # Use residential proxy
  use_undetected: false,     # Use Undetected Chrome
  solve_captcha: false,      # Auto-solve captchas
  timeout: 60                # Timeout in seconds
)
```

**Token costs:**
- Base request: 1 token
- Antibot bypass: +2 tokens
- JS rendering: +5 tokens
- Residential proxy: +3 tokens
- Captcha solving: +10 tokens

### scrape_async

Submit an async scraping job for long-running requests.

```
scrape_async(
  url: "https://heavy-site.com",
  use_js_render: true,
  timeout: 120,
  callback_url: "https://your-webhook.com/callback"
)
```

Returns a `job_id` for status polling.

### get_job_status

Get the status of an async scraping job.

```
get_job_status(job_id: "550e8400-e29b-41d4-a716-446655440000")
```

Statuses: `pending`, `processing`, `completed`, `failed`, `cancelled`

### batch_scrape

Scrape multiple URLs in a single batch (up to 100 URLs).

```
batch_scrape(
  urls: ["https://example.com/1", "https://example.com/2"],
  use_js_render: false,
  callback_url: "https://your-webhook.com/batch-done"
)
```

### get_usage

Get current API token usage.

```
get_usage()
```

## Examples

### Basic Scraping

Ask Claude or your AI agent:

> "Scrape https://example.com and show me the content"

### JavaScript Rendered Page

> "Scrape https://spa-website.com with JavaScript rendering enabled"

### Protected Site with Captcha

> "Scrape https://protected-site.com using residential proxy and captcha solving"

### Batch Scraping

> "Scrape these URLs: https://example.com/1, https://example.com/2, https://example.com/3"

## Pricing

FineData uses token-based pricing. Each feature adds tokens:

| Feature | Tokens |
|---------|--------|
| Base request | 1 |
| Antibot (TLS fingerprinting) | +2 |
| JS Rendering (Playwright) | +5 |
| Undetected Chrome | +5 |
| Residential Proxy | +3 |
| Mobile Proxy | +4 |
| reCAPTCHA / hCaptcha | +10 |
| Cloudflare Turnstile | +12 |
| Yandex SmartCaptcha | +15 |

Get your API key and free trial tokens at [finedata.ai](https://finedata.ai).

## Troubleshooting

### "No module named finedata_mcp"

Install uv and use uvx:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "externally-managed-environment" on macOS

This happens with Homebrew Python. Use uvx instead of pip:
```json
{
  "command": "uvx",
  "args": ["finedata-mcp"]
}
```

### MCP server not appearing in Cursor

1. Check `~/.cursor/mcp.json` syntax (valid JSON)
2. Ensure `FINEDATA_API_KEY` is set
3. Restart Cursor completely
4. Check Cursor Output → MCP for errors

## Support

- Documentation: https://docs.finedata.ai
- Email: support@finedata.ai
- Issues: https://github.com/quality-network/finedata-mcp/issues

## License

MIT
