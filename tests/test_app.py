"""Tests for MCP app tool registration and param parsing."""

import asyncio
from pathlib import Path

import pytest

from agent import ReviewFileInput
from app import review_code_file
from utils import (
    parse_review_params,
    resolve_file_in_workspace,
    salvage_params_from_string,
)


def test_parse_review_params_accepts_dict() -> None:
    """Params passed as dict are validated and returned as ReviewFileInput."""
    raw = {"file_path": "src/main.py", "review_depth": "standard"}
    result = parse_review_params(raw)
    assert isinstance(result, ReviewFileInput)
    assert result.file_path == "src/main.py"
    assert result.review_depth == "standard"
    assert result.focus_areas is None


def test_parse_review_params_accepts_json_string() -> None:
    """Params passed as JSON string (e.g. by some LLM clients) are parsed and validated."""
    raw = '{"file_path": "src/backend/database/models/feature.py", "review_depth": "standard"}'
    result = parse_review_params(raw)
    assert isinstance(result, ReviewFileInput)
    assert result.file_path == "src/backend/database/models/feature.py"
    assert result.review_depth == "standard"


def test_parse_review_params_accepts_review_file_input() -> None:
    """If already a ReviewFileInput instance, it is returned as-is."""
    existing = ReviewFileInput(file_path="lib/utils.py", review_depth="quick")
    result = parse_review_params(existing)
    assert result is existing
    assert result.file_path == "lib/utils.py"


def test_parse_review_params_invalid_json_string_raises() -> None:
    """Invalid JSON string that cannot be salvaged raises ValueError."""
    with pytest.raises(ValueError, match="Invalid params"):
        parse_review_params("not valid json {{")


def test_parse_review_params_non_dict_or_string_raises() -> None:
    """Non-dict, non-string input raises ValueError."""
    with pytest.raises(ValueError, match="params must be a JSON object or string"):
        parse_review_params(123)


def test_salvage_extracts_file_path_from_malformed_string() -> None:
    """Malformed strings like {}'file_path: path' are salvaged."""
    assert salvage_params_from_string(
        "{}'file_path: backend/database/models/feature.py'"
    ) == {"file_path": "backend/database/models/feature.py", "review_depth": "standard"}
    assert salvage_params_from_string(
        '{}"file_path": "src/backend/database/models/feature.py"'
    ) == {"file_path": "src/backend/database/models/feature.py", "review_depth": "standard"}
    assert salvage_params_from_string(
        "file_path: src/app.py"
    ) == {"file_path": "src/app.py", "review_depth": "standard"}


def test_parse_review_params_salvages_malformed_string() -> None:
    """When JSON fails, we try to salvage file_path and accept the request."""
    result = parse_review_params("{}'file_path: backend/database/models/feature.py'")
    assert isinstance(result, ReviewFileInput)
    assert result.file_path == "backend/database/models/feature.py"
    assert result.review_depth == "standard"


def test_review_code_file_invalid_params_returns_usage_instructions() -> None:
    """When params are invalid, the error response includes how to call the tool correctly."""
    result = asyncio.run(review_code_file(params="not valid json {{"))
    assert "Invalid arguments for review_code_file" in result
    assert "How to call review_code_file correctly" in result
    assert "file_path" in result
    assert "review_depth" in result
    assert "Example:" in result


def test_resolve_file_in_workspace_direct_path(tmp_path: Path) -> None:
    """Direct path that exists is returned as-is."""
    (tmp_path / "src" / "app.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "app.py").write_text("# app")
    resolved = resolve_file_in_workspace(tmp_path, "src/app.py")
    assert resolved is not None
    assert resolved == (tmp_path / "src" / "app.py").resolve()
    assert resolved.read_text() == "# app"


def test_resolve_file_in_workspace_suffix_path(tmp_path: Path) -> None:
    """Path that is a suffix of actual path (e.g. client sent path without src/) is found."""
    (tmp_path / "src" / "backend" / "database" / "models").mkdir(parents=True, exist_ok=True)
    feature_py = tmp_path / "src" / "backend" / "database" / "models" / "feature.py"
    feature_py.write_text("# feature")
    resolved = resolve_file_in_workspace(tmp_path, "backend/database/models/feature.py")
    assert resolved is not None
    assert resolved == feature_py.resolve()
    assert resolved.read_text() == "# feature"


def test_resolve_file_in_workspace_not_found(tmp_path: Path) -> None:
    """Nonexistent path returns None."""
    assert resolve_file_in_workspace(tmp_path, "nonexistent/file.py") is None
    assert resolve_file_in_workspace(tmp_path, "src/app.py") is None


def test_resolve_file_in_workspace_rejects_traversal() -> None:
    """Paths with '..' return None."""
    workspace = Path.cwd()
    assert resolve_file_in_workspace(workspace, "../other/file.py") is None
    assert resolve_file_in_workspace(workspace, "src/../../etc/passwd") is None


def test_review_code_file_file_not_found_returns_error() -> None:
    """When file_path does not exist under workspace, return a clear file-not-found error."""
    result = asyncio.run(
        review_code_file(params={"file_path": "nonexistent/path/that/does/not/exist.py", "review_depth": "standard"})
    )
    assert "Error: File not found" in result
    assert "nonexistent/path/that/does/not/exist.py" in result
    assert "No file under the workspace matches" in result
