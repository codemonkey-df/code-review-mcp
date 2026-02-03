"""Unit tests for review strategy and orchestration."""

from pathlib import Path

from review_strategy import (
    ReviewOrchestrator,
    add_line_numbers_to_section,
    SPLIT_THRESHOLD_LINES,
)
from sections import Section


def test_should_split_small_file_returns_false() -> None:
    """Files below threshold do not split."""
    orchestrator = ReviewOrchestrator()
    content = "\n".join(["print('hello')" for _ in range(50)])
    assert not orchestrator.should_split(content, Path("small.py"))


def test_should_split_large_python_returns_true() -> None:
    """Files at or above threshold with .py extension split."""
    orchestrator = ReviewOrchestrator()
    content = "\n".join(["# line"] * SPLIT_THRESHOLD_LINES)
    assert orchestrator.should_split(content, Path("large.py"))


def test_should_split_large_unsupported_extension_returns_false() -> None:
    """Files at or above threshold but unsupported extension do not split."""
    orchestrator = ReviewOrchestrator()
    content = "\n".join(["line"] * 200)
    assert not orchestrator.should_split(content, Path("data.txt"))


def test_resolve_section_identifier_by_kind_and_name() -> None:
    """Resolve identifier as 'function name' or 'class Name'."""
    section_func = Section(
        kind="function",
        name="parse_config",
        start_line=10,
        end_line=20,
        text="def parse_config():\n    pass",
    )
    section_class = Section(
        kind="class",
        name="Handler",
        start_line=22,
        end_line=30,
        text="class Handler:\n    pass",
    )
    orchestrator = ReviewOrchestrator()
    orchestrator.sections = [section_func, section_class]

    assert (
        orchestrator.resolve_section_identifier("function parse_config") is section_func
    )
    assert orchestrator.resolve_section_identifier("class handler") is section_class


def test_resolve_section_identifier_by_name_only() -> None:
    """Resolve identifier by name only (e.g. 'parse_config')."""
    section = Section(
        kind="function",
        name="parse_config",
        start_line=1,
        end_line=5,
        text="def parse_config():\n    pass",
    )
    orchestrator = ReviewOrchestrator()
    orchestrator.sections = [section]

    assert orchestrator.resolve_section_identifier("parse_config") is section


def test_resolve_section_identifier_by_lines() -> None:
    """Resolve identifier by 'lines start-end'."""
    section = Section(
        kind="imports",
        name="imports",
        start_line=1,
        end_line=10,
        text="import os\nimport sys",
    )
    orchestrator = ReviewOrchestrator()
    orchestrator.sections = [section]

    assert orchestrator.resolve_section_identifier("lines 1-10") is section


def test_resolve_section_identifier_unknown_returns_none() -> None:
    """Unknown identifier returns None."""
    orchestrator = ReviewOrchestrator()
    orchestrator.sections = []

    assert orchestrator.resolve_section_identifier("unknown_thing") is None


def test_parse_context_request_extracts_identifier() -> None:
    """REQUEST_CONTEXT line is parsed and identifier returned."""
    orchestrator = ReviewOrchestrator()
    text = "REQUEST_CONTEXT: function parse_config\n\n[LINE 1] SUGGESTION: ..."
    assert orchestrator.parse_context_request(text) == "function parse_config"


def test_parse_context_request_no_match_returns_none() -> None:
    """Text without REQUEST_CONTEXT returns None."""
    orchestrator = ReviewOrchestrator()
    text = "[LINE 1] SUGGESTION: some comment"
    assert orchestrator.parse_context_request(text) is None


def test_parse_review_comments_extracts_line_comments() -> None:
    """Lines starting with [LINE are collected."""
    orchestrator = ReviewOrchestrator()
    text = "[LINE 5] CRITICAL: bug here\n[LINE 10] SUGGESTION: improve\nNot a comment"
    comments = orchestrator.parse_review_comments(text)
    assert len(comments) == 2
    assert "[LINE 5]" in comments[0]
    assert "[LINE 10]" in comments[1]


def test_add_line_numbers_to_section() -> None:
    """Section text gets line numbers matching original file."""
    section = Section(
        kind="function",
        name="f",
        start_line=14,
        end_line=16,
        text="def f():\n    pass\n",
    )
    numbered = add_line_numbers_to_section(section)
    lines = numbered.split("\n")
    assert lines[0].startswith("  14 |")
    assert lines[1].startswith("  15 |")
    assert len(lines) >= 2  # section.text splitlines() may omit trailing blank
