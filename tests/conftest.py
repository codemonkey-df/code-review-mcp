"""Pytest configuration and fixtures."""

import os

# Set WORKSPACE_DIR before any module imports agent/config (default /workspace may not exist).
if not os.environ.get("WORKSPACE_DIR"):
    os.environ["WORKSPACE_DIR"] = os.getcwd()
