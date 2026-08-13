"""Configuration for FineData MCP Server.

Environment variables:
- FINEDATA_API_KEY: API key (required for stdio; optional for HTTP — per-request Bearer)
- FINEDATA_API_URL: Base URL (default: https://api.finedata.ai)
- FINEDATA_TIMEOUT: Default client timeout seconds (default: 180)
- FINEDATA_MCP_HOST / FINEDATA_MCP_PORT: HTTP bind (default 0.0.0.0:8080)
- FINEDATA_OAUTH_ISSUER: Authorization server URL (gateway) for remote MCP
- FINEDATA_MCP_RESOURCE_URL: Public MCP endpoint URL, path included
  (https://mcp.finedata.ai/mcp). It is published verbatim as `resource` in the
  protected-resource document and decides where that document is served, so the
  origin alone makes the server advertise an identifier that is not itself.
- FINEDATA_JWT_SECRET: Shared secret to verify OAuth access tokens (aud=mcp)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    api_key: str
    api_url: str
    timeout: int
    host: str
    port: int
    oauth_issuer: str | None
    resource_url: str | None
    jwt_secret: str | None
    jwt_algorithm: str

    @classmethod
    def from_env(cls, *, require_api_key: bool = True) -> "Config":
        api_key = os.environ.get("FINEDATA_API_KEY", "")
        if require_api_key and not api_key:
            raise ValueError(
                "FINEDATA_API_KEY environment variable is required. "
                "Get your API key at https://finedata.ai"
            )
        return cls(
            api_key=api_key,
            api_url=os.environ.get("FINEDATA_API_URL", "https://api.finedata.ai"),
            timeout=int(os.environ.get("FINEDATA_TIMEOUT", "180")),
            host=os.environ.get("FINEDATA_MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("FINEDATA_MCP_PORT", "8080")),
            oauth_issuer=os.environ.get("FINEDATA_OAUTH_ISSUER") or None,
            resource_url=os.environ.get("FINEDATA_MCP_RESOURCE_URL") or None,
            jwt_secret=os.environ.get("FINEDATA_JWT_SECRET")
            or os.environ.get("JWT_SECRET")
            or None,
            jwt_algorithm=os.environ.get("FINEDATA_JWT_ALGORITHM", "HS256"),
        )


_config: Config | None = None


def get_config(*, require_api_key: bool = True) -> Config:
    global _config
    if _config is None:
        _config = Config.from_env(require_api_key=require_api_key)
    return _config


def reset_config() -> None:
    """Test helper."""
    global _config
    _config = None
