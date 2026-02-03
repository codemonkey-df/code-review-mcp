"""
Review logic and LLM/file I/O for the Code Review MCP server.

Single responsibility: input model, file helpers, and performing the code review
via LiteLLM.
"""

import logging
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Literal, Optional

import litellm
from pydantic import BaseModel, ConfigDict, Field, field_validator

import config as config_module
import prompt as prompt_module
from review_strategy import ReviewOrchestrator, add_line_numbers_to_section

logger = logging.getLogger(__name__)


class ReviewFileInput(BaseModel):
    """Input model for code review tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    file_path: str = Field(
        ...,
        description="Relative path to the file within the workspace to review (e.g., 'src/main.py', 'lib/utils.js')",
        min_length=1,
    )

    review_depth: Literal["quick", "standard", "thorough"] = Field(
        default="standard",
        description="Review depth: 'quick' for basic checks, 'standard' for comprehensive review, 'thorough' for in-depth analysis",
    )

    focus_areas: Optional[str] = Field(
        default=None,
        description="Specific areas to focus on (e.g., 'security', 'performance', 'error handling'). Leave empty for general review.",
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate that file path is relative and doesn't attempt path traversal."""
        if v.startswith("/"):
            raise ValueError(
                "File path must be relative and cannot contain '..' or start with '/'"
            )
        parts = Path(v).parts
        if ".." in parts:
            raise ValueError(
                "File path must be relative and cannot contain '..' or start with '/'"
            )
        return v


def add_line_numbers(content: str) -> str:
    """Add line numbers to file content for easier reference in reviews."""
    lines = content.splitlines()
    numbered_lines = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered_lines)


def read_file_content(file_path: Path) -> str:
    """Read file content, attempting UTF-8 first, falling back to latin-1 if decoding fails."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        logger.warning(
            "File %s could not be decoded as UTF-8; falling back to latin-1",
            file_path,
        )
        with open(file_path, "r", encoding="latin-1") as f:
            return f.read()


def write_review_comments(file_path: Path, original_content: str, review: str) -> None:
    """Write review comments to the original file as inline comments.

    Expects review lines in the form [LINE N] TYPE: comment (N is 1-indexed).
    Comments are inserted immediately before the line they reference.

    Args:
        file_path: Path to the file to write.
        original_content: Original file content before review.
        review: Raw review text from the LLM (may contain [LINE N] ... lines).
    """
    ext = file_path.suffix.lower()
    # Each value is (comment_prefix, comment_suffix) for inline comments.
    comment_styles: dict[str, tuple[str, str]] = {
        ".py": ("#", ""),
        ".js": ("//", ""),
        ".ts": ("//", ""),
        ".jsx": ("//", ""),
        ".tsx": ("//", ""),
        ".java": ("//", ""),
        ".c": ("//", ""),
        ".cpp": ("//", ""),
        ".cs": ("//", ""),
        ".go": ("//", ""),
        ".rs": ("//", ""),
        ".rb": ("#", ""),
        ".sh": ("#", ""),
        ".yaml": ("#", ""),
        ".yml": ("#", ""),
        ".html": ("<!--", " -->"),
        ".css": ("/*", " */"),
        ".sql": ("--", ""),
    }
    comment_prefix, comment_suffix = comment_styles.get(ext, ("#", ""))
    if ext not in comment_styles and ext:
        logger.warning(
            "Unknown file extension %r; using # for comments. Review may not render correctly.",
            ext,
        )

    review_lines = review.strip().splitlines()
    comments_by_line: dict[int, list[str]] = defaultdict(list)
    current_line_num: int | None = None
    current_comment_lines: list[str] = []

    def flush_comment() -> None:
        if current_line_num is not None and current_comment_lines:
            comments_by_line[current_line_num].append("\n".join(current_comment_lines))

    for line in review_lines:
        if line.strip().startswith("[LINE "):
            flush_comment()
            try:
                parts = line.split("]", 1)
                if len(parts) != 2:
                    continue
                line_num = int(parts[0].replace("[LINE ", "").strip())
                comment_text = parts[1].strip()
                current_line_num = line_num
                current_comment_lines = [comment_text]
            except (ValueError, IndexError):
                logger.debug("Skipping malformed review line: %r", line[:80])
                current_line_num = None
                current_comment_lines = []
        elif current_line_num is not None:
            current_comment_lines.append(line.strip())

    flush_comment()

    if not comments_by_line:
        header = f"{comment_prefix} === CODE REVIEW RESULTS ==={comment_suffix}\n"
        for rev_line in review_lines:
            header += f"{comment_prefix} {rev_line}{comment_suffix}\n"
        header += f"{comment_prefix} {'=' * 50}{comment_suffix}\n\n"
        _atomic_write(file_path, header + original_content)
        return

    original_lines = original_content.splitlines()
    new_lines = []
    for i, line in enumerate(original_lines, start=1):
        if i in comments_by_line:
            new_lines.append(
                f"{comment_prefix} === CODE REVIEW COMMENT ==={comment_suffix}"
            )
            for comment in comments_by_line[i]:
                for comment_line in comment.splitlines():
                    new_lines.append(
                        f"{comment_prefix} {comment_line}{comment_suffix}"
                    )
            new_lines.append(f"{comment_prefix} {'=' * 50}{comment_suffix}")
        new_lines.append(line)

    _atomic_write(file_path, "\n".join(new_lines))


def _atomic_write(file_path: Path, content: str) -> None:
    """Write content to file atomically (temp file + rename) to avoid corruption on failure."""
    import os

    fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent, prefix=".review_", suffix=".tmp"
    )
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(file_path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp_path).unlink(missing_ok=True)
        raise


async def _call_llm(prompt: str) -> str:
    """Call LiteLLM with the given prompt and return response text."""
    cfg = config_module.settings
    messages = [{"role": "user", "content": prompt}]
    response = await litellm.acompletion(
        model=cfg.llm_model,
        messages=messages,
        api_base=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        temperature=0.3,
        max_tokens=8192,
    )
    if not response.choices:
        logger.warning("LLM returned no choices")
        return ""
    content = response.choices[0].message.content
    if content is None:
        logger.warning("LLM returned None content")
        return ""
    return content


async def perform_code_review(
    file_path: Path,
    review_depth: str,
    focus_areas: Optional[str],
) -> str:
    """Perform code review using LiteLLM and the configured LLM proxy.

    Automatically chooses between whole-file and section-based review based on
    file size and language support.

    Args:
        file_path: Path to the file to review.
        review_depth: One of 'quick', 'standard', 'thorough'.
        focus_areas: Optional focus areas string.

    Returns:
        Raw review text from the LLM (all sections merged for section-based path).
    """
    content = read_file_content(file_path)
    orchestrator = ReviewOrchestrator()

    if not orchestrator.should_split(content, file_path):
        return await _perform_whole_file_review(
            file_path, content, review_depth, focus_areas
        )

    return await _perform_section_based_review(
        file_path, content, review_depth, focus_areas, orchestrator
    )


async def _perform_whole_file_review(
    file_path: Path,
    content: str,
    review_depth: str,
    focus_areas: Optional[str],
) -> str:
    """Perform whole-file review (single prompt, single LLM call)."""
    logger.info(
        "Starting whole-file review: path=%s depth=%s focus=%s",
        file_path,
        review_depth,
        focus_areas or "(none)",
    )
    numbered_content = add_line_numbers(content)
    prompt = prompt_module.build_review_prompt(
        file_path, numbered_content, review_depth, focus_areas
    )
    result = await _call_llm(prompt)
    logger.info("Whole-file review completed: path=%s", file_path)
    return result


async def _perform_section_based_review(
    file_path: Path,
    content: str,
    review_depth: str,
    focus_areas: Optional[str],
    orchestrator: ReviewOrchestrator,
) -> str:
    """Perform section-based review with context request support."""
    logger.info(
        "Starting section-based review: path=%s depth=%s focus=%s max_iter=%s",
        file_path,
        review_depth,
        focus_areas or "(none)",
        orchestrator.max_iterations,
    )
    orchestrator.prepare_sections(content, file_path)
    num_sections = len(orchestrator.sections)
    logger.info("Prepared %s section(s) for review: path=%s", num_sections, file_path)

    for section_index in range(num_sections):
        if orchestrator.iterations_used >= orchestrator.max_iterations:
            logger.warning(
                "Stopping section loop: max iterations reached (%s): path=%s",
                orchestrator.max_iterations,
                file_path,
            )
            break

        section = orchestrator.sections[section_index]
        logger.info(
            "Reviewing section %s/%s (iter %s/%s): path=%s",
            section_index + 1,
            num_sections,
            orchestrator.iterations_used + 1,
            orchestrator.max_iterations,
            file_path,
        )

        section_numbered = add_line_numbers_to_section(section)
        section_context = orchestrator.get_section_context_for_review(section)
        section_context["section_text"] = section_numbered

        prompt = prompt_module.build_section_review_prompt(
            file_path, section_context, review_depth, focus_areas
        )
        review_response = await _call_llm(prompt)

        comments = orchestrator.parse_review_comments(review_response)
        orchestrator.accumulated_reviews.extend(comments)
        orchestrator.iterations_used += 1
        logger.debug(
            "Section %s produced %s comment(s): path=%s",
            section_index + 1,
            len(comments),
            file_path,
        )

        context_request = orchestrator.parse_context_request(review_response)

        if (
            context_request
            and orchestrator.iterations_used < orchestrator.max_iterations
        ):
            logger.info(
                "Context request for section: request=%s path=%s",
                context_request,
                file_path,
            )
            requested_section = orchestrator.resolve_section_identifier(context_request)

            if requested_section:
                requested_numbered = add_line_numbers_to_section(requested_section)

                followup_prompt = prompt_module.build_section_context_followup_prompt(
                    file_path, section_context, requested_numbered
                )
                followup_response = await _call_llm(followup_prompt)

                followup_comments = orchestrator.parse_review_comments(
                    followup_response
                )
                orchestrator.accumulated_reviews.extend(followup_comments)
                orchestrator.iterations_used += 1
                logger.info(
                    "Context followup completed: +%s comment(s) iter=%s/%s path=%s",
                    len(followup_comments),
                    orchestrator.iterations_used,
                    orchestrator.max_iterations,
                    file_path,
                )
            else:
                logger.warning(
                    "Context request could not resolve section: request=%s path=%s",
                    context_request,
                    file_path,
                )

    total_comments = len(orchestrator.accumulated_reviews)
    logger.info(
        "Section-based review completed: path=%s sections=%s iterations=%s comments=%s",
        file_path,
        num_sections,
        orchestrator.iterations_used,
        total_comments,
    )
    return "\n".join(orchestrator.accumulated_reviews)
