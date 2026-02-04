"""
Prompt text and assembly for the Code Review MCP server.

Single responsibility: system prompt constant, depth instructions, and building
the full user prompt (whole-file and section-based).
"""

from pathlib import Path
from typing import Any, Optional


# Review priority guidelines (embedded in all prompts)
REVIEW_PRIORITIES = """
REVIEW PRIORITIES (high to low):
1. Architecture & Design - structure, boundaries, coupling, separation of concerns
2. Correctness - logic errors, edge cases, invariants
3. Readability - clarity, naming, structure (NOT formatting style)
4. Security - injection, validation, secrets, permissions
5. Performance - algorithms, I/O, unnecessary work
6. Error Handling - exceptions, recovery, logging

CODE STANDARDS:
- Apply PEP 8 for structure and naming; use max line length 120 and max function length 50 lines (recommend splitting if longer).
- Apply SOLID principles; if a class or function does too much, suggest splitting it (Single Responsibility).

DE-PRIORITIZE: Style-only formatting (spacing, quotes, minor PEP 8 nitpicks). State "tools can automate these"
and avoid requesting changes unless they affect readability or consistency meaningfully.

FEEDBACK STYLE:
- Be specific and constructive
- Explain WHY a change matters
- Suggest concrete solutions
- Use explicit actions: "Request changes: ...", "Suggest: ...", "Consider: ..."
"""


CODE_REVIEW_PROMPT = """You are an expert code reviewer. Analyze the following code file and provide detailed, constructive feedback.

{priorities}

FILE: {file_path}

{depth_instruction}

{focus_instruction}

FILE CONTENT:
```
{content}
```

Provide your review as specific line-by-line comments using this format:
[LINE X] TYPE: Your comment here

You may continue a comment on the next lines; only use a new "[LINE N]" when starting a comment for a different line. 
Where TYPE is one of: CRITICAL, SUGGESTION, QUESTION, PRAISE

Focus on the priorities and CODE STANDARDS above (PEP 8, line length 120, function length ≤50 lines, SOLID). 
Be specific, explain your reasoning, and provide actionable suggestions. Always check and comment on CODE STANDARDS violations when present.
"""


SECTION_REVIEW_PROMPT = """You are an expert code reviewer. You are reviewing ONE SECTION of a larger file.

{priorities}

FILE: {file_path}

{section_map}

CURRENT SECTION: {section_kind} "{section_name}" (lines {section_start}-{section_end})

{depth_instruction}

{focus_instruction}

SECTION CONTENT:
```
{section_content}
```

**CONTEXT REQUEST CAPABILITY:**
If you need to see the full content of another section for context (e.g., a function called 
by this one, or a class this inherits from), output exactly ONE line:

REQUEST_CONTEXT: <section_identifier>

Where <section_identifier> is from the SECTION MAP above (e.g., "function parse_config", 
"class Handler", or "lines 12-18").

Put this line at the START of your response if needed. If you don't need another section, 
do NOT output REQUEST_CONTEXT.

**OUTPUT FORMAT:**
Provide your review as specific line-by-line comments:
[LINE X] TYPE: Your comment here

You may continue a comment on the next lines; only use a new "[LINE N]" when starting a comment for a different line. 
Where TYPE is one of: CRITICAL, SUGGESTION, QUESTION, PRAISE.

Focus on the priorities and CODE STANDARDS above (PEP 8, line length 120, function length ≤50 lines, SOLID). 
Be specific and actionable. Always check and comment on CODE STANDARDS violations when present.
"""


SECTION_CONTEXT_FOLLOWUP_PROMPT = """You are continuing your review of a section with additional context.

{priorities}

FILE: {file_path}

CURRENT SECTION: {section_kind} "{section_name}" (lines {section_start}-{section_end})

CURRENT SECTION CONTENT:
```
{section_content}
```

ADDITIONAL CONTEXT (requested section):
```
{context_section_content}
```

Using this additional context, complete or refine your review of the CURRENT SECTION.

Do NOT output REQUEST_CONTEXT again.

Provide your review as:
[LINE X] TYPE: Your comment here

You may continue a comment on the next lines; only use a new "[LINE N]" when starting a comment for a different line. 
Focus on the priorities and CODE STANDARDS above and how this context affects your review of the current section.
"""


def build_review_prompt(
    file_path: Path,
    numbered_content: str,
    review_depth: str,
    focus_areas: Optional[str],
) -> str:
    """Build the whole-file review prompt.

    Args:
        file_path: Path to the file being reviewed.
        numbered_content: File content with line numbers already applied.
        review_depth: One of 'quick', 'standard', 'thorough'.
        focus_areas: Optional string of areas to focus on, or None.

    Returns:
        Complete prompt string to send to the LLM.
    """
    depth_instructions = {
        "quick": "Perform a quick scan focusing on obvious issues and critical problems.",
        "standard": "Perform a comprehensive review covering all priority areas.",
        "thorough": "Perform an in-depth analysis with detailed explanations and examples.",
    }

    depth_instruction = depth_instructions.get(
        review_depth, depth_instructions["standard"]
    )
    focus_instruction = (
        f"**SPECIAL FOCUS**: Pay particular attention to: {focus_areas}"
        if focus_areas
        else ""
    )

    return CODE_REVIEW_PROMPT.format(
        priorities=REVIEW_PRIORITIES,
        file_path=str(file_path),
        depth_instruction=depth_instruction,
        focus_instruction=focus_instruction,
        content=numbered_content,
    )


def build_section_review_prompt(
    file_path: Path,
    section_context: dict[str, Any],
    review_depth: str,
    focus_areas: Optional[str],
) -> str:
    """Build prompt for reviewing a single section with section map context.

    Args:
        file_path: Path to the file being reviewed.
        section_context: Dict with section_map, section_kind, section_name,
            section_start_line, section_end_line, section_text.
        review_depth: One of 'quick', 'standard', 'thorough'.
        focus_areas: Optional string of areas to focus on, or None.

    Returns:
        Complete prompt string for section review.
    """
    depth_instructions = {
        "quick": "Perform a quick scan focusing on obvious issues.",
        "standard": "Perform a comprehensive review.",
        "thorough": "Perform an in-depth analysis with detailed explanations.",
    }

    depth_instruction = depth_instructions.get(
        review_depth, depth_instructions["standard"]
    )
    focus_instruction = f"**SPECIAL FOCUS**: {focus_areas}" if focus_areas else ""

    return SECTION_REVIEW_PROMPT.format(
        priorities=REVIEW_PRIORITIES,
        file_path=str(file_path),
        section_map=section_context["section_map"],
        section_kind=section_context["section_kind"],
        section_name=section_context["section_name"],
        section_start=section_context["section_start_line"],
        section_end=section_context["section_end_line"],
        section_content=section_context["section_text"],
        depth_instruction=depth_instruction,
        focus_instruction=focus_instruction,
    )


def build_section_context_followup_prompt(
    file_path: Path,
    section_context: dict[str, Any],
    context_section_text: str,
) -> str:
    """Build prompt for follow-up review after context request.

    Args:
        file_path: Path to the file being reviewed.
        section_context: Dict with section_kind, section_name, section_start_line,
            section_end_line, section_text.
        context_section_text: Text of the requested context section (with line numbers).

    Returns:
        Complete prompt string for follow-up review.
    """
    return SECTION_CONTEXT_FOLLOWUP_PROMPT.format(
        priorities=REVIEW_PRIORITIES,
        file_path=str(file_path),
        section_kind=section_context["section_kind"],
        section_name=section_context["section_name"],
        section_start=section_context["section_start_line"],
        section_end=section_context["section_end_line"],
        section_content=section_context["section_text"],
        context_section_content=context_section_text,
    )
