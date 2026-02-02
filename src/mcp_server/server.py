"""
FineData MCP Server

Main entry point for the MCP server that exposes FineData scraping
capabilities to AI agents via the Model Context Protocol.
"""

import asyncio
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from .tools import TOOLS, call_tool
from .client import get_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("finedata-mcp")

# Create the MCP server instance
server = Server("finedata")


@server.list_tools()
async def list_tools():
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocation."""
    logger.info(f"Tool called: {name}")
    return await call_tool(name, arguments or {})


async def run_server():
    """Run the MCP server."""
    logger.info("Starting FineData MCP Server...")
    
    try:
        # Validate configuration on startup
        from .config import get_config
        config = get_config()
        logger.info(f"API URL: {config.api_url}")
        logger.info("API Key: ****" + config.api_key[-4:] if len(config.api_key) > 4 else "***")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
    
    # Cleanup
    client = get_client()
    await client.close()
    logger.info("FineData MCP Server stopped")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
