"""
Configuration for FineData MCP Server.

Environment variables:
- FINEDATA_API_KEY: API key for authentication (required)
- FINEDATA_API_URL: Base URL for FineData API (default: https://api.finedata.ai)
- FINEDATA_TIMEOUT: Default timeout in seconds (default: 180)
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """FineData MCP Server configuration."""
    
    api_key: str
    api_url: str
    timeout: int
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        api_key = os.environ.get("FINEDATA_API_KEY", "")
        
        if not api_key:
            raise ValueError(
                "FINEDATA_API_KEY environment variable is required. "
                "Get your API key at https://finedata.ai"
            )
        
        return cls(
            api_key=api_key,
            api_url=os.environ.get("FINEDATA_API_URL", "https://api.finedata.ai"),
            timeout=int(os.environ.get("FINEDATA_TIMEOUT", "180")),
        )


# Global config instance (lazy loaded)
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global configuration."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
