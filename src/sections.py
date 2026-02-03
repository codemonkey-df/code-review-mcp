"""
Section parsing for code files.

Splits files into logical sections (imports, globals, functions, classes) for review.
"""

from pathlib import Path
from typing import List
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Section(BaseModel):
    """Represents a logical section of code."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(
        ...,
        description="One of: imports, globals, function, class, other",
    )
    name: str = Field(
        ...,
        description="Section name, e.g. parse_config, Handler, or imports",
    )
    start_line: int = Field(..., ge=1, description="First line number (1-based).")
    end_line: int = Field(..., ge=1, description="Last line number (1-based).")
    text: str = Field(..., description="Section content.")

    @model_validator(mode="after")
    def end_line_not_before_start(self) -> "Section":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self

    @property
    def identifier(self) -> str:
        """Unique identifier for this section (for context requests)."""
        if self.kind in ("imports", "globals", "other"):
            return f"{self.kind}: lines {self.start_line}-{self.end_line}"
        return f"{self.kind} {self.name}: lines {self.start_line}-{self.end_line}"


class SectionParser:
    """Parse code files into logical sections based on language."""

    # Language detection by extension
    PYTHON_EXTS = {".py", ".pyw"}
    JS_TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    def __init__(self, content: str, file_path: Path) -> None:
        """Initialize parser with file content and path."""
        self.content = content
        self.lines = content.splitlines()
        self.file_path = file_path
        self.ext = file_path.suffix.lower()

    def parse(self) -> List[Section]:
        """Parse file into sections based on language."""
        if self.ext in self.PYTHON_EXTS:
            return self._parse_python()
        if self.ext in self.JS_TS_EXTS:
            return self._parse_javascript()
        # Unsupported language: return entire file as one section
        return [
            Section(
                kind="other",
                name="entire file",
                start_line=1,
                end_line=len(self.lines),
                text=self.content,
            )
        ]

    def _find_decorators_start(self, def_line_idx: int) -> int:
        """Find the starting line of decorators above a function/class definition.

        Args:
            def_line_idx: Index (0-based) of the def/class line.

        Returns:
            Index (0-based) where decorators start, or def_line_idx if no decorators.
        """
        i = def_line_idx - 1
        decorator_start = def_line_idx
        while i >= 0:
            line = self.lines[i]
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                i -= 1
                continue
            if stripped.startswith("@"):
                decorator_start = i
                i -= 1
                continue
            break
        return decorator_start

    def _parse_python(self) -> List[Section]:
        """Parse Python file into sections."""
        sections: List[Section] = []

        import_end = 0
        globals_end = 0

        # 1. Find imports (consecutive import/from lines at top)
        import_start: int | None = None
        for i, line in enumerate(self.lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(("import ", "from ")):
                if import_start is None:
                    import_start = i
                import_end = i
            elif import_start is not None and stripped and not stripped.startswith("#"):
                break

        if import_start is not None:
            sections.append(
                Section(
                    kind="imports",
                    name="imports",
                    start_line=import_start,
                    end_line=import_end,
                    text="\n".join(self.lines[import_start - 1 : import_end]),
                )
            )

        # 2. Find top-level assignments (globals)
        globals_start: int | None = None
        for i in range(import_end, len(self.lines)):
            line = self.lines[i]
            stripped = line.lstrip()

            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("@") or re.match(
                r"^(async\s+)?(def|class)\s+\w+", stripped
            ):
                break

            # Top-level globals only (column 0)
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
                if globals_start is None:
                    globals_start = i + 1
                globals_end = i + 1

        if globals_start is not None:
            sections.append(
                Section(
                    kind="globals",
                    name="globals",
                    start_line=globals_start,
                    end_line=globals_end,
                    text="\n".join(self.lines[globals_start - 1 : globals_end]),
                )
            )

        # 3. Find functions and classes (with decorators)
        i = max(import_end, globals_end)
        while i < len(self.lines):
            line = self.lines[i]
            stripped = line.lstrip()

            func_match = re.match(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
            async_func_match = re.match(
                r"^async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", line
            )
            if func_match or async_func_match:
                func_name = (func_match or async_func_match).group(1)
                decorator_start_idx = self._find_decorators_start(i)
                start = decorator_start_idx + 1
                end = self._find_block_end(i)
                sections.append(
                    Section(
                        kind="function",
                        name=func_name,
                        start_line=start,
                        end_line=end,
                        text="\n".join(self.lines[decorator_start_idx:end]),
                    )
                )
                i = end
                continue

            class_match = re.match(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if class_match:
                class_name = class_match.group(1)
                decorator_start_idx = self._find_decorators_start(i)
                start = decorator_start_idx + 1
                end = self._find_block_end(i)
                sections.append(
                    Section(
                        kind="class",
                        name=class_name,
                        start_line=start,
                        end_line=end,
                        text="\n".join(self.lines[decorator_start_idx:end]),
                    )
                )
                i = end
                continue

            i += 1

        if sections:
            return sections
        return [
            Section(
                kind="other",
                name="entire file",
                start_line=1,
                end_line=len(self.lines),
                text=self.content,
            )
        ]

    def _find_js_decorators_start(self, def_line_idx: int) -> int:
        """Find the starting line of decorators/JSDoc above a JS/TS function/class.

        Handles TypeScript decorators (@Component, including multi-line) and
        JSDoc (/** ... */).

        Args:
            def_line_idx: Index (0-based) of the function/class line.

        Returns:
            Index (0-based) where decorators/docs start, or def_line_idx if none.
        """
        i = def_line_idx - 1
        decorator_start = def_line_idx
        in_jsdoc = False
        while i >= 0:
            line = self.lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                i -= 1
                continue
            if stripped.endswith("*/"):
                in_jsdoc = True
                decorator_start = i
                i -= 1
                continue
            if in_jsdoc and stripped.startswith("/**"):
                decorator_start = i
                in_jsdoc = False
                i -= 1
                continue
            if in_jsdoc:
                decorator_start = i
                i -= 1
                continue
            if stripped.startswith("@"):
                decorator_start = i
                i -= 1
                continue
            # Multi-line decorator: closing line (e.g. "})") or indented content
            if re.match(r"^[\]})\s,;]+$", stripped):
                decorator_start = i
                i -= 1
                continue
            if decorator_start < def_line_idx and line and line[0] in " \t":
                decorator_start = i
                i -= 1
                continue
            break
        return decorator_start

    def _parse_javascript(self) -> List[Section]:
        """Parse JavaScript/TypeScript file into sections."""
        sections: List[Section] = []

        import_start = None
        import_end = 0
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if re.match(
                r'^import\s+.*from|^import\s+["\']|^const.*=\s*require\(',
                stripped,
            ):
                if import_start is None:
                    import_start = i
                import_end = i
            elif (
                import_start is not None and stripped and not stripped.startswith("//")
            ):
                break

        if import_start is not None:
            sections.append(
                Section(
                    kind="imports",
                    name="imports",
                    start_line=import_start,
                    end_line=import_end,
                    text="\n".join(self.lines[import_start - 1 : import_end]),
                )
            )

        globals_start = None
        globals_end = 0
        arrow_pattern = re.compile(
            r"^(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*(?:async\s*)?\(.*\)\s*=>"
        )
        for i in range(import_end, len(self.lines)):
            line = self.lines[i]
            stripped = line.strip()

            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            if stripped.startswith("@") or re.match(
                r"^(function|class)\s+\w+", stripped
            ):
                break

            if arrow_pattern.match(stripped):
                continue

            if re.match(r"^(const|let|var)\s+\w+", stripped):
                if globals_start is None:
                    globals_start = i + 1
                globals_end = i + 1

        if globals_start is not None:
            sections.append(
                Section(
                    kind="globals",
                    name="globals",
                    start_line=globals_start,
                    end_line=globals_end,
                    text="\n".join(self.lines[globals_start - 1 : globals_end]),
                )
            )

        i = max(import_end, globals_end)
        while i < len(self.lines):
            line = self.lines[i]
            stripped = line.strip()

            func_match = re.match(
                r"^function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", stripped
            )
            async_match = re.match(
                r"^async\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", stripped
            )
            arrow_match = re.match(
                r"^(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\(.*\)\s*=>",
                stripped,
            )

            if func_match or arrow_match or async_match:
                func_name = (func_match or arrow_match or async_match).group(1)
                decorator_start_idx = self._find_js_decorators_start(i)
                start = decorator_start_idx + 1
                end = self._find_js_block_end(i)
                sections.append(
                    Section(
                        kind="function",
                        name=func_name,
                        start_line=start,
                        end_line=end,
                        text="\n".join(self.lines[decorator_start_idx:end]),
                    )
                )
                i = end
                continue

            class_match = re.match(r"^class\s+([A-Za-z_$][A-Za-z0-9_$]*)", stripped)
            if class_match:
                class_name = class_match.group(1)
                decorator_start_idx = self._find_js_decorators_start(i)
                start = decorator_start_idx + 1
                end = self._find_js_block_end(i)
                sections.append(
                    Section(
                        kind="class",
                        name=class_name,
                        start_line=start,
                        end_line=end,
                        text="\n".join(self.lines[decorator_start_idx:end]),
                    )
                )
                i = end
                continue

            i += 1

        if sections:
            return sections
        return [
            Section(
                kind="other",
                name="entire file",
                start_line=1,
                end_line=len(self.lines),
                text=self.content,
            )
        ]

    def _find_block_end(self, start_idx: int) -> int:
        """Find end of Python block (function/class) by indentation."""
        if start_idx >= len(self.lines):
            return len(self.lines)

        base_indent = len(self.lines[start_idx]) - len(self.lines[start_idx].lstrip())

        for i in range(start_idx + 1, len(self.lines)):
            line = self.lines[i]
            if not line.strip():
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                return i

        return len(self.lines)

    def _find_js_block_end(self, start_idx: int) -> int:
        """Find end of JS/TS block by brace matching."""
        if start_idx >= len(self.lines):
            return len(self.lines)

        brace_count = 0
        started = False

        for i in range(start_idx, len(self.lines)):
            line = self.lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    started = True
                elif char == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        return i + 1

        return len(self.lines)


def build_section_map(sections: List[Section]) -> str:
    """Build a readable section map for LLM context."""
    lines = ["SECTION MAP (for reference):"]
    for section in sections:
        lines.append(f"  {section.identifier}")
    return "\n".join(lines)


def parse_sections(content: str, file_path: Path) -> List[Section]:
    """Main entry point: parse file content into sections."""
    parser = SectionParser(content, file_path)
    return parser.parse()
