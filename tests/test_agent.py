"""Unit tests for agent review comment writing."""

import tempfile
from pathlib import Path

import pytest

from agent import write_review_comments


def test_write_review_comments_preserves_multiline_comment() -> None:
    """Continuation lines after [LINE N] are captured and written as full comment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "example.py"
        original = "def foo():\n    pass\n"
        path.write_text(original, encoding="utf-8")

        review = """[LINE 1] SUGGESTION: The docstring could be more descriptive. Consider expanding it to include:
- A brief description of what the function returns
- Any side effects or exceptions
"""
        write_review_comments(path, original, review)

        content = path.read_text(encoding="utf-8")
        assert "=== CODE REVIEW COMMENT ===" in content
        assert "Consider expanding it to include:" in content
        assert "A brief description of what the function returns" in content
        assert "Any side effects or exceptions" in content
        assert "def foo():" in content


def test_write_review_comments_multiple_lines_same_line_number() -> None:
    """Multiple [LINE N] comments for same line are all preserved; continuation lines attach to the last [LINE N]."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "example.py"
        original = "x = 1\ny = 2\n"
        path.write_text(original, encoding="utf-8")

        review = """[LINE 1] SUGGESTION: First point.
[LINE 1] SUGGESTION: Second point with details:
- detail A
- detail B
"""
        write_review_comments(path, original, review)

        content = path.read_text(encoding="utf-8")
        assert "First point." in content
        assert "Second point with details:" in content
        assert "detail A" in content
        assert "detail B" in content
