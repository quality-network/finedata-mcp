"""
FineData MCP Server

MCP (Model Context Protocol) server for FineData web scraping API.
Allows AI agents (Claude, Cursor, GPT) to scrape websites with antibot bypass,
JS rendering, captcha solving, and proxy rotation.
"""

__version__ = "0.1.6"
__author__ = "FineData"

from .server import main

__all__ = ["main", "__version__"]
