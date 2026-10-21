from pathlib import Path
from typing import Literal
from fastmcp import FastMCP
from tools import repository as repo
from tools.runner import run_candidate, Candidate

mcp = FastMCP("api-gap-tools")
Variant = Literal["healthy", "buggy", "covered"]

@mcp.tool()
def list_endpoints() -> dict:
    """List the three available API operations."""
    return repo.list_endpoints()

@mcp.tool()
def search_rules(query: str = "") -> dict:
    """Retrieve numbered business rules. Small corpus: returns all rules."""
    return repo.search_rules(query)

@mcp.tool()
def inspect_schema(operation_id: str) -> dict:
    """Get request schema and fixture preparation for an operation."""
    return repo.inspect_schema(operation_id)

@mcp.tool()
def search_tests(variant: Variant, query: str = "") -> dict:
    """List every existing test file, including shared access tests."""
    return repo.search_tests(variant, query)

@mcp.tool()
def read_test_file(variant: Variant, path: str) -> dict:
    """Read an allowlisted test file with line numbers."""
    return repo.read_test_file(variant, path)

@mcp.tool()
def run_candidate_test(variant: Variant, run_id: str, candidate: Candidate) -> dict:
    """Validate structured HTTP steps, generate pytest and execute in a fresh fixture app."""
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("invalid run_id")
    return run_candidate(variant, repo.ROOT / "outputs" / run_id, candidate.model_dump())

if __name__ == "__main__":
    mcp.run(show_banner=False)
