# FineData MCP Server (NPM launcher)

Node.js launcher for the Python package [`finedata-mcp`](https://pypi.org/project/finedata-mcp/).

```bash
export FINEDATA_API_KEY=fd_xxx
npx -y @finedata/mcp-server
```

Requires Python 3.10+ and **uv** (recommended) or **pipx**. Works on macOS, Linux, and Windows.

## Cursor

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

## Remote HTTP

Prefer the Python package with `--transport http`, or point Cursor at:

`https://mcp.finedata.ai/mcp` with `Authorization: Bearer fd_…`

## Docs

Full tool list and escalation ladder: https://pypi.org/project/finedata-mcp/

Version **0.2.3**
