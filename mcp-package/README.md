# @finedata/mcp-server

MCP Server for [FineData](https://finedata.ai) web scraping API.

This is a Node.js wrapper that launches the Python MCP server.

## Quick Start

```bash
# Set your API key and run
FINEDATA_API_KEY=fd_xxx npx @finedata/mcp-server
```

## Configuration

### Claude Desktop

Add to `claude_desktop_config.json`:

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

### Cursor IDE

Add to MCP settings:

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

## Requirements

- Node.js 18+
- Python 3.10+ OR [uv](https://github.com/astral-sh/uv) (recommended)

## Recommended: Using uvx

For better performance, install [uv](https://github.com/astral-sh/uv) and use uvx directly:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then configure:

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

## Features

- **Antibot Bypass** - Cloudflare, DataDome, PerimeterX
- **JavaScript Rendering** - Playwright for SPAs
- **Captcha Solving** - reCAPTCHA, hCaptcha, Turnstile
- **Proxy Rotation** - 87K+ datacenter + residential

## Get Your API Key

Sign up at [finedata.ai](https://finedata.ai) to get your API key and free trial tokens.

## Documentation

See the full documentation at https://docs.finedata.ai

## Issues

https://github.com/quality-network/finedata-mcp/issues
