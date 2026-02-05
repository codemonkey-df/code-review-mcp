"""Review tool parameter parsing and salvage from malformed client input."""

import json
import re
from typing import Any

from agent import ReviewFileInput

# Instructional error text so the calling AI agent can fix the next tool call.
REVIEW_CODE_FILE_USAGE = """
How to call review_code_file correctly on your next try:
- Pass a single JSON object (not a string) with these keys:
  - file_path (required): relative path to the file inside the workspace, e.g. "src/main.py" or "backend/database/models/feature.py". No leading slash, no "..".
  - review_depth (optional): "quick" | "standard" | "thorough". Default: "standard".
  - focus_areas (optional): e.g. "security, performance" or null.
Example: {"file_path": "src/app.py", "review_depth": "standard"}
If your client sends tool arguments as a string, send the object structure instead so the server receives a dict.
"""

# Patterns to salvage file_path from malformed strings.
_FILE_PATH_PATTERNS = [
    re.compile(r'''["']?file_path["']?\s*:\s*["']([^"']+)["']''', re.IGNORECASE),
    re.compile(r'''["']?file_path["']?\s*:\s*([^\s,}'"]+)''', re.IGNORECASE),
    re.compile(r'''(\b(?:src|backend|lib|app|tests)/[a-zA-Z0-9_./\-]+\.[a-zA-Z0-9]+)'''),
]


def salvage_params_from_string(s: str) -> dict[str, Any] | None:
    """Try to extract file_path (and optionally review_depth) from a malformed string.

    Handles common LLM/client mistakes like {}'file_path: backend/...' or
    file_path: backend/database/models/feature.py.
    """
    s = s.strip()
    if not s:
        return None
    file_path: str | None = None
    for pat in _FILE_PATH_PATTERNS:
        m = pat.search(s)
        if m:
            file_path = m.group(1).strip().strip("'\"")
            if file_path and "/" in file_path and not file_path.startswith("{"):
                break
    if not file_path or ".." in file_path or file_path.startswith("/"):
        return None
    review_depth = "standard"
    if "thorough" in s.lower():
        review_depth = "thorough"
    elif "quick" in s.lower():
        review_depth = "quick"
    return {"file_path": file_path, "review_depth": review_depth}


def parse_review_params(raw: Any) -> ReviewFileInput:
    """Parse tool arguments that may be passed as a string or dict by the client.

    Some clients (e.g. Cursor/OpenAI-style tool calls) send the whole params
    object as a JSON string; this normalizes to ReviewFileInput. If the string
    is malformed (e.g. {}'file_path: path'), we try to salvage file_path and
    proceed.
    """
    if isinstance(raw, ReviewFileInput):
        return raw
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            salvaged = salvage_params_from_string(raw)
            if salvaged is not None:
                return ReviewFileInput.model_validate(salvaged)
            raise ValueError(
                "Invalid params (expected JSON). Use exactly: {\"file_path\": \"path/to/file.py\", \"review_depth\": \"standard\"}"
            ) from e
    if isinstance(raw, dict):
        return ReviewFileInput.model_validate(raw)
    raise ValueError(
        f"params must be a JSON object or string, got {type(raw).__name__}"
    )
