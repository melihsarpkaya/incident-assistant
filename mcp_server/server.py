"""MCP server exposing the bank knowledge layer.

Used by the incident agent and by coding assistants such as Claude Code.
Run: python -m mcp_server.server   (stdio transport)
"""

import logging

from mcp.server.fastmcp import FastMCP

from incident_assistant.config import DATA_DIR
from mcp_server import repository, retrieval

logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = FastMCP("bank-knowledge", log_level="WARNING")


@mcp.tool()
def lookup_error_code(code: str) -> dict:
    """Look up an error code (e.g. EFT-4042) in the error code catalog. Returns the owning service and component."""
    return repository.lookup_error_code(code)


@mcp.tool()
def search_logs(query: str, service: str | None = None) -> dict:
    """Search service log lines by keywords such as a transaction id or error code. service: eft-service or card-service."""
    return repository.search_logs(query, service)


@mcp.tool()
def search_code(query: str, service: str | None = None) -> dict:
    """Search Java source code lines by keywords such as a class name, method or error code. service: eft-service or card-service."""
    return repository.search_code(query, service)


@mcp.tool()
def read_file(path: str, start_line: int = 1, end_line: int = 120) -> dict:
    """Read lines of a source file. path is the file part of a code ref returned by search_code."""
    return repository.read_file(path, start_line, end_line)


@mcp.tool()
def search_docs(query: str) -> dict:
    """Semantic search in service documentation: business rules, validation rules, retry policy, coding standards."""
    return retrieval.search_docs(query)


@mcp.tool()
def get_transaction(transaction_id: str) -> dict:
    """Get all records of a transaction id (e.g. TX-20261028-0412) from the transaction database."""
    return repository.get_transaction(transaction_id)


@mcp.tool()
def list_customer_transactions(customer_id: str, date: str) -> dict:
    """List a customer's transactions on a date (YYYY-MM-DD). Useful to detect duplicate charges."""
    return repository.list_customer_transactions(customer_id, date)


@mcp.resource("docs://coding-standards")
def coding_standards() -> str:
    """Team coding standards to follow when implementing a fix."""
    return (DATA_DIR / "docs" / "coding-standards.md").read_text()


if __name__ == "__main__":
    mcp.run()
