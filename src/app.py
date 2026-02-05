"""
MCP server and tool registration for the Code Review MCP server.

Single responsibility: FastMCP instance and tool handlers
(review_code_file, list_workspace_files).
"""

from mcp.server.fastmcp import FastMCP
from pydantic import Field, ValidationError

import config as config_module
from agent import perform_code_review, read_file_content, write_review_comments
from utils import (
    REVIEW_CODE_FILE_USAGE,
    parse_review_params,
    resolve_file_in_workspace,
)

mcp = FastMCP("code_review_mcp")

# Max file size for review (10MB).
_MAX_REVIEW_FILE_SIZE = 10 * 1024 * 1024


@mcp.tool(
    name="review_code_file",
    annotations={
        "title": "AI Code Review",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def review_code_file(params: object) -> str:
    """Review a code file and add inline comments with suggestions and improvements.

    This tool performs AI-powered code review using LiteLLM and your configured LLM proxy. It analyzes
    the code for bugs, security issues, performance problems, and best practices violations.
    The review is added directly to the file as inline comments.

    Args:
        params: Review parameters as a dict or JSON string with keys: file_path (required, relative path
            within workspace, e.g. 'src/main.py'), review_depth ('quick' | 'standard' | 'thorough'),
            focus_areas (optional, e.g. 'security, performance').

    Returns:
        Success message with file path, or error message if review failed.
    """
    try:
        parsed = parse_review_params(params)
    except (ValueError, ValidationError) as e:
        return (
            f"Error: Invalid arguments for review_code_file: {e}"
            f"{REVIEW_CODE_FILE_USAGE}"
        )

    try:
        workspace_dir = config_module.settings.workspace_dir
        full_path = resolve_file_in_workspace(workspace_dir, parsed.file_path)
        if full_path is None:
            return (
                f"Error: File not found: {parsed.file_path}\n"
                f"Workspace directory: {workspace_dir}\n"
                "No file under the workspace matches that path or path suffix."
            )
        workspace_resolved = workspace_dir.resolve()
        if not full_path.is_relative_to(workspace_resolved):
            return f"Error: Path escapes workspace: {parsed.file_path}"

        if not full_path.is_file():
            return f"Error: Path is not a file: {parsed.file_path}"

        if full_path.stat().st_size > _MAX_REVIEW_FILE_SIZE:
            return f"Error: File too large for review (max 10MB): {parsed.file_path}"

        original_content = read_file_content(full_path)
        review_result = await perform_code_review(
            full_path,
            parsed.review_depth,
            parsed.focus_areas,
        )
        write_review_comments(full_path, original_content, review_result)
        resolved_rel = str(full_path.relative_to(workspace_dir)).replace("\\", "/")
        return (
            f"✅ Review completed. Comments added to: {resolved_rel}\n\n"
            "Please check the file to see the inline review comments."
        )
    except Exception as e:
        return f"Error during code review: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="list_workspace_files",
    annotations={
        "title": "List Workspace Files",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_workspace_files(
    directory: str = Field(
        default=".",
        description="Subdirectory to list (relative to workspace root, e.g., 'src', 'lib')",
    ),
) -> str:
    """List all files in the workspace directory or a subdirectory.

    Helps discover which files are available for review in the mounted workspace.

    Args:
        directory: Subdirectory path relative to workspace root.

    Returns:
        List of files with their relative paths.
    """
    try:
        workspace_dir = config_module.settings.workspace_dir
        target_dir = (workspace_dir / directory).resolve()
        workspace_resolved = workspace_dir.resolve()
        if not target_dir.is_relative_to(workspace_resolved):
            return f"Error: Directory path escapes workspace: {directory}"

        if not target_dir.exists():
            return f"Error: Directory not found: {directory}"

        if not target_dir.is_dir():
            return f"Error: Path is not a directory: {directory}"

        ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        files = []
        for path in sorted(target_dir.rglob("*")):
            if path.is_file():
                if any(ign in path.parts for ign in ignore_dirs):
                    continue
                relative_path = path.relative_to(workspace_dir)
                files.append(str(relative_path))

        if not files:
            return f"No files found in: {directory}"

        result = f"Files in workspace (total: {len(files)}):\n\n"
        for file_path in files:
            result += f"  - {file_path}\n"
        return result
    except Exception as e:
        return f"Error listing files: {type(e).__name__}: {str(e)}"


if __name__ == "__main__":
    mcp.run()
