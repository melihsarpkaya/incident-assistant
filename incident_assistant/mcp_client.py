"""Connects to the bank-knowledge MCP server over stdio and exposes its tools as LangChain tools."""

import os
import sys
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from incident_assistant.config import ROOT

SERVERS = {
    "bank-knowledge": {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "mcp_server.server"],
        "cwd": str(ROOT),
        "env": dict(os.environ),
    }
}


@asynccontextmanager
async def mcp_tools():
    """Keep one MCP session open for the whole investigation instead of one process per tool call."""
    client = MultiServerMCPClient(SERVERS)
    async with client.session("bank-knowledge") as session:
        yield await load_mcp_tools(session)
