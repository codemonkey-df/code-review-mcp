"""
Configuration for the Code Review MCP server.

Loads and validates environment variables (LLM proxy and workspace).
Docker Compose injects env from .env automatically; load_dotenv() is a no-op if vars are already set.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Validated configuration from environment (set at build, runtime, or via .env)."""

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    workspace_dir: Path

    def __repr__(self) -> str:
        """Repr that masks API key to avoid accidental exposure in logs."""
        return (
            f"Settings(llm_base_url={self.llm_base_url!r}, "
            "llm_api_key='***REDACTED***', "
            f"llm_model={self.llm_model!r}, "
            f"workspace_dir={self.workspace_dir!r})"
        )

    __str__ = __repr__


def get_settings() -> Settings:
    """Load and validate settings; exit with error if required vars are missing."""
    missing = []
    llm_base_url = os.getenv("LLM_BASE_URL")
    llm_api_key = os.getenv("LLM_API_KEY")
    llm_model = os.getenv("LLM_MODEL")
    if not llm_base_url:
        missing.append("LLM_BASE_URL")
    if not llm_api_key:
        missing.append("LLM_API_KEY")
    if not llm_model:
        missing.append("LLM_MODEL")
    if missing:
        print(
            f"ERROR: Required environment variable(s) not set: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    workspace_dir = Path(os.getenv("WORKSPACE_DIR", "/workspace")).resolve()
    if not workspace_dir.is_dir():
        print(
            f"ERROR: WORKSPACE_DIR is not a directory: {workspace_dir}",
            file=sys.stderr,
        )
        sys.exit(1)
    return Settings(
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        workspace_dir=workspace_dir,
    )


# Singleton used by other modules
settings = get_settings()
