"""
Review strategy and orchestration for section-based code review.

Handles split decision, section iteration, and context requests.
"""

from pathlib import Path
from typing import List, Optional
import re

from sections import Section, build_section_map, parse_sections


# Configuration constants
SPLIT_THRESHOLD_LINES = 150  # Files below this use whole-file review
EXTRA_ITERATIONS = 4  # Budget for context requests; when max reached, section loop stops (no error).


class ReviewOrchestrator:
    """Orchestrates section-based code review with context request support."""

    def __init__(self) -> None:
        """Initialize orchestrator state."""
        self.sections: List[Section] = []
        self.section_map: str = ""
        # Accumulated [LINE N] TYPE: comment lines from section reviews (used by agent).
        self.accumulated_reviews: List[str] = []
        self.iterations_used: int = 0
        self.max_iterations: int = 0

    def should_split(self, content: str, file_path: Path) -> bool:
        """Decide whether to split file into sections or use whole-file review."""
        line_count = len(content.splitlines())

        if line_count < SPLIT_THRESHOLD_LINES:
            return False

        ext = file_path.suffix.lower()
        supported_exts = {
            ".py",
            ".pyw",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".mjs",
            ".cjs",
        }
        return ext in supported_exts

    def prepare_sections(self, content: str, file_path: Path) -> None:
        """Parse file into sections and build section map."""
        self.sections = parse_sections(content, file_path)
        self.section_map = build_section_map(self.sections)
        self.max_iterations = len(self.sections) + EXTRA_ITERATIONS
        self.iterations_used = 0
        self.accumulated_reviews = []

    def resolve_section_identifier(self, identifier: str) -> Optional[Section]:
        """Resolve a section identifier to a Section object.

        Supports:
        - "function parse_config"
        - "class Handler"
        - "lines 12-18"
        - "imports"
        """
        identifier = identifier.strip().lower()
        # Normalize "lines 12-18" / "lines  12-18" / "lines 12 - 18" style
        lines_match = re.search(r"lines\s*(\d+)\s*-\s*(\d+)", identifier)
        if lines_match:
            identifier = f"lines {lines_match.group(1)}-{lines_match.group(2)}"

        for section in self.sections:
            if f"{section.kind} {section.name}".lower() == identifier:
                return section

            if section.name.lower() == identifier:
                return section

            if f"lines {section.start_line}-{section.end_line}" == identifier:
                return section

        return None

    def parse_context_request(self, review_text: str) -> Optional[str]:
        """Extract REQUEST_CONTEXT identifier from LLM response.

        Returns:
            Section identifier if found, None otherwise.
        """
        match = re.search(
            r"REQUEST_CONTEXT:\s*(.+?)(?:\n|$)", review_text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
        return None

    def parse_review_comments(self, review_text: str) -> List[str]:
        """Extract [LINE X] comment lines from review text."""
        comments = []
        for line in review_text.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith("[LINE "):
                comments.append(stripped)
        return comments

    def get_section_context_for_review(self, section: Section) -> dict[str, str | int]:
        """Build context dict for section review prompt."""
        return {
            "section_kind": section.kind,
            "section_name": section.name,
            "section_text": section.text,
            "section_start_line": section.start_line,
            "section_end_line": section.end_line,
            "section_map": self.section_map,
        }


def add_line_numbers_to_section(section: Section) -> str:
    """Add line numbers to section text matching original file line numbers."""
    section_lines = section.text.splitlines()
    numbered_lines = []

    for i, line in enumerate(section_lines):
        actual_line_num = section.start_line + i
        numbered_lines.append(f"{actual_line_num:4d} | {line}")

    return "\n".join(numbered_lines)
