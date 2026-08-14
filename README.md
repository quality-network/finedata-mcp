<!-- mcp-name: io.github.quality-network/finedata-mcp -->

# FineData MCP Server

MCP (Model Context Protocol) server for [FineData](https://finedata.ai) web scraping API.

Enables AI agents (Claude, Cursor, GPT, …) to fetch pages that need a full
browser and return clean data:

- JavaScript rendering and browser actions
- Captcha solving
- Datacenter / ISP / residential / mobile proxies
- Markdown or JSON output (markdown by default)
- AI structured extraction
- Local **stdio** or remote **Streamable HTTP** (+ OAuth 2.1)

Version: **0.3.1**

## Modes

Start with a plain request. Stealth and proxy modes are available when a page
needs a full browser; they consume more tokens than a plain request. Exact
rates are in the documentation and via `get_usage`. Gateway may apply a domain
strategy that overrides the requested engine or proxy; trust `tokens_used` in
the response.

## Installation

### uvx (recommended)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
FINEDATA_API_KEY=fd_xxx uvx finedata-mcp
```

### pip

```bash
pip install finedata-mcp
FINEDATA_API_KEY=fd_xxx finedata-mcp
```

### npx

```bash
npx -y @finedata/mcp-server
```

## Cursor

`~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`):

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

Cursor deeplink (after publishing): install via MCP directory / “Add to Cursor”.

### Remote (Streamable HTTP)

```json
{
  "mcpServers": {
    "finedata": {
      "url": "https://mcp.finedata.ai/mcp",
      "headers": {
        "Authorization": "Bearer fd_your_api_key_here"
      }
    }
  }
}
```

OAuth 2.1 (Claude.ai / ChatGPT connectors): register via AS at `https://api.finedata.ai`, consent in the cabinet, then use the access token as Bearer.

## Environment

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FINEDATA_API_KEY` | stdio: yes | — | API key |
| `FINEDATA_API_URL` | no | `https://api.finedata.ai` | API base |
| `FINEDATA_TIMEOUT` | no | `180` | HTTP client timeout (seconds) |
| `FINEDATA_MCP_HOST` | HTTP | `0.0.0.0` | Bind host |
| `FINEDATA_MCP_PORT` | HTTP | `8080` | Bind port |
| `FINEDATA_OAUTH_ISSUER` | remote OAuth | — | AS URL (gateway) |
| `FINEDATA_MCP_RESOURCE_URL` | remote OAuth | — | Public MCP URL |
| `FINEDATA_JWT_SECRET` | remote OAuth | — | Verify `aud=mcp` JWTs |

## Tools

| Tool | Purpose |
|------|---------|
| `scrape_url` | Sync scrape with GET, read-only (markdown default) |
| `send_http_request` | Sync POST / PUT / PATCH / DELETE through the same pipeline |
| `scrape_async` | Async job, GET (`formats=['markdown']` default) |
| `get_job_status` | Poll job (markdown, not raw HTML) |
| `cancel_job` | Cancel job |
| `list_jobs` | List jobs |
| `batch_scrape` | Up to 100 URLs (string or `{url,...}` objects) |
| `get_batch_status` | Batch progress |
| `get_usage` | Period usage via `api_tokens_used` |

Notable parameters: `use_antibot`, `proxy_country`, `proxy_sticky`, `proxy_profile_id`, `auto_retry`, stealth modes, `formats`, `only_main_content`, extract_*.

Async/batch: no `csv`/`xlsx` formats (sync only).

## HTTP transport

```bash
finedata-mcp --transport http --host 0.0.0.0 --port 8080
```

Health: `GET /health`. Protected resource metadata is served at the path-scoped
URL for the endpoint — `GET /.well-known/oauth-protected-resource/mcp` — because
`FINEDATA_MCP_RESOURCE_URL` carries the `/mcp` path. Clients normally find it
from the `WWW-Authenticate` header on a `401` rather than guessing.

## Support

- Docs: https://finedata.ai/docs
- Issues: https://github.com/quality-network/finedata-mcp/issues

## License

MIT
