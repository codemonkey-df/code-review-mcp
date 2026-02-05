"""Path and workspace file resolution utilities."""

from pathlib import Path

# Directories to skip when searching workspace for a file by path suffix.
WORKSPACE_SEARCH_IGNORE = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "venv"}
)


def resolve_file_in_workspace(workspace_dir: Path, file_path: str) -> Path | None:
    """Resolve client file_path to an existing file under workspace_dir.

    Clients may send a path that is a suffix of the actual path (e.g.
    backend/database/models/feature.py when the real path is
    src/backend/database/models/feature.py). This tries the direct path first,
    then searches the workspace for any file whose relative path ends with
    the given file_path.

    Returns:
        Resolved absolute Path to the file, or None if not found or path
        escapes workspace.
    """
    normalized = file_path.strip().lstrip("/").replace("\\", "/")
    if not normalized or ".." in normalized:
        return None
    workspace_resolved = workspace_dir.resolve()
    candidate = (workspace_dir / normalized).resolve()
    if candidate.is_file() and candidate.is_relative_to(workspace_resolved):
        return candidate
    # Search for a file whose relative path ends with the given path.
    matches: list[Path] = []
    for path in workspace_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(ign in path.parts for ign in WORKSPACE_SEARCH_IGNORE):
            continue
        try:
            rel = path.relative_to(workspace_dir)
            rel_str = str(rel).replace("\\", "/")
            if rel_str == normalized:
                matches.append(path.resolve())
            elif rel_str.endswith(normalized) and (
                len(rel_str) == len(normalized) or rel_str[-len(normalized) - 1] == "/"
            ):
                matches.append(path.resolve())
        except ValueError:
            continue
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Prefer exact relative path match.
    for m in matches:
        try:
            if str(m.relative_to(workspace_dir)).replace("\\", "/") == normalized:
                return m
        except ValueError:
            continue
    return min(matches, key=lambda p: len(str(p)))
