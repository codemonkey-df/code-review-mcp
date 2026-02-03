#!/usr/bin/env python3
"""
Code Review MCP Server — entry point.

An MCP server that provides code review capabilities using LiteLLM and an LLM proxy.
Canonical entry: from project root run `uv run python src/server.py` (or `uv run python src/app.py`).
"""

import sys

from app import mcp

if __name__ == "__main__":
    try:
        mcp.run()
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
