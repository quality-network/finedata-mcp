# @finedata/mcp-server

MCP Server for [FineData](https://finedata.ai) web scraping API.

This is a Node.js wrapper that launches the Python MCP server.

## Quick Start

```bash
# Set your API key and run
FINEDATA_API_KEY=fd_xxx npx -y @finedata/mcp-server
```

## Configuration

### Cursor IDE Setup

**Step 1:** Create or edit MCP config file:

**macOS/Linux:**
```bash
mkdir -p ~/.cursor && nano ~/.cursor/mcp.json
```

**Windows:** Edit `%USERPROFILE%\.cursor\mcp.json`

**Step 2:** Add FineData server (using uvx - recommended):

```json
{
  "mcpServers": {
    "finedata": {
      "command": "uvx",
      "args": ["finedata-mcp"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key"
      }
    }
  }
}
```

**Step 3:** Restart Cursor

**Step 4:** Test it by asking:
> "Scrape https://example.com and show me the title"

#### Using npx (alternative)

```json
{
  "mcpServers": {
    "finedata": {
      "command": "npx",
      "args": ["-y", "@finedata/mcp-server"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key"
      }
    }
  }
}
```

---

### Claude Desktop Setup

**Step 1:** Open config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Step 2:** Add MCP server:

```json
{
  "mcpServers": {
    "finedata": {
      "command": "uvx",
      "args": ["finedata-mcp"],
      "env": {
        "FINEDATA_API_KEY": "fd_your_api_key"
      }
    }
  }
}
```

**Step 3:** Restart Claude Desktop

---

## Requirements

- Node.js 18+ (for npx)
- [uv](https://github.com/astral-sh/uv) (recommended) OR Python 3.10+

### Install uv (Recommended)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

uv provides `uvx` which runs Python tools in isolated environments automatically.

## Features

- **Antibot Bypass** - Cloudflare, DataDome, PerimeterX
- **JavaScript Rendering** - Playwright for SPAs
- **Captcha Solving** - reCAPTCHA, hCaptcha, Turnstile
- **Proxy Rotation** - 87K+ datacenter + residential

## Available Tools

| Tool | Description |
|------|-------------|
| `scrape_url` | Sync scraping with antibot, JS render, captcha |
| `scrape_async` | Async scraping, returns job_id |
| `get_job_status` | Check async job status |
| `batch_scrape` | Batch scrape up to 100 URLs |
| `get_usage` | Current token usage |

## Troubleshooting

### "No module named finedata_mcp"

Install uv and use uvx config instead:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "externally-managed-environment" error on macOS

Use uvx instead of npx:
```json
{
  "command": "uvx",
  "args": ["finedata-mcp"]
}
```

### MCP not working in Cursor

1. Check `~/.cursor/mcp.json` is valid JSON
2. Restart Cursor
3. Check Output → MCP panel for errors

## Get Your API Key

Sign up at [finedata.ai](https://finedata.ai) to get your API key and free trial tokens.

## Documentation

Full documentation: https://docs.finedata.ai

## Issues

https://github.com/quality-network/finedata-mcp/issues

## License

MIT
