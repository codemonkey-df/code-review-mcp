"""Unit tests for section parsing."""

from pathlib import Path

from sections import Section, build_section_map, parse_sections


def test_python_sections_imports_globals_function_class() -> None:
    """Parse Python with imports, globals, one def, one class."""
    content = """
import os
import sys

DEBUG = True

def main():
    pass

class Handler:
    def process(self):
        pass
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    assert len(sections) == 4
    assert sections[0].kind == "imports"
    assert sections[0].name == "imports"
    assert sections[1].kind == "globals"
    assert sections[1].name == "globals"
    assert sections[2].kind == "function"
    assert sections[2].name == "main"
    assert sections[3].kind == "class"
    assert sections[3].name == "Handler"


def test_python_sections_identifiers() -> None:
    """Section identifiers follow expected format."""
    content = "import os\n\ndef foo():\n    pass\n"
    sections = parse_sections(content, Path("x.py"))
    assert len(sections) >= 2
    assert sections[0].identifier == "imports: lines 1-1"
    assert "function" in sections[1].identifier
    assert "foo" in sections[1].identifier


def test_unsupported_extension_returns_single_section() -> None:
    """Unsupported extension returns entire file as one section."""
    content = "line1\nline2\nline3"
    sections = parse_sections(content, Path("file.txt"))
    assert len(sections) == 1
    assert sections[0].kind == "other"
    assert sections[0].name == "entire file"
    assert sections[0].start_line == 1
    assert sections[0].end_line == 3
    assert sections[0].text == content


def test_build_section_map() -> None:
    """Section map lists all section identifiers."""
    content = "import os\n\ndef f():\n    pass\n"
    sections = parse_sections(content, Path("a.py"))
    section_map = build_section_map(sections)
    assert "SECTION MAP" in section_map
    assert "imports" in section_map
    assert "function" in section_map or "f" in section_map


def test_class_section_model() -> None:
    """Classes produce Section with correct kind, name, lines, text and identifier."""
    content = """
class Handler:
    def process(self):
        pass
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    assert len(sections) == 1
    s = sections[0]
    assert s.kind == "class"
    assert s.name == "Handler"
    assert s.start_line >= 1
    assert s.end_line >= s.start_line
    assert "class Handler" in s.text
    assert "def process" in s.text
    assert s.identifier == f"class Handler: lines {s.start_line}-{s.end_line}"


def test_inner_function_not_separate_section() -> None:
    """Top-level function with inner def yields one section; inner def is in text."""
    content = """
def x():
    def y():
        pass
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    assert len(sections) == 1
    func_section = sections[0]
    assert func_section.kind == "function"
    assert func_section.name == "x"
    assert "def y()" in func_section.text
    assert "def x()" in func_section.text


def test_python_async_def_as_separate_section() -> None:
    """Top-level async def is parsed as a function section with correct name."""
    content = """
import os

def sync_main():
    pass

async def fetch_data():
    return await get()
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    assert len(sections) >= 3
    funcs = [s for s in sections if s.kind == "function"]
    assert len(funcs) == 2
    names = {s.name for s in funcs}
    assert names == {"sync_main", "fetch_data"}
    async_section = next(s for s in funcs if s.name == "fetch_data")
    assert "async def fetch_data" in async_section.text
    assert async_section.identifier.startswith("function fetch_data")
