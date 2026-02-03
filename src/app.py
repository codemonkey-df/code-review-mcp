"""
MCP server and tool registration for the Code Review MCP server.

Single responsibility: FastMCP instance and tool handlers (review_code_file, list_workspace_files).
"""

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import config as config_module
from agent import (
    ReviewFileInput,
    perform_code_review,
    read_file_content,
    write_review_comments,
)

mcp = FastMCP("code_review_mcp")


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
async def review_code_file(params: ReviewFileInput) -> str:
    """Review a code file and add inline comments with suggestions and improvements.

    This tool performs AI-powered code review using LiteLLM and your configured LLM proxy. It analyzes
    the code for bugs, security issues, performance problems, and best practices violations.
    The review is added directly to the file as inline comments.

    Args:
        params: Review parameters (file_path, review_depth, focus_areas).

    Returns:
        Success message with file path, or error message if review failed.
    """
    try:
        workspace_dir = config_module.settings.workspace_dir
        full_path = (workspace_dir / params.file_path).resolve()
        workspace_resolved = workspace_dir.resolve()
        if not full_path.is_relative_to(workspace_resolved):
            return f"Error: Path escapes workspace: {params.file_path}"

        if not full_path.exists():
            return f"Error: File not found: {params.file_path}\nWorkspace directory: {workspace_dir}"

        if not full_path.is_file():
            return f"Error: Path is not a file: {params.file_path}"

        max_size = 10 * 1024 * 1024  # 10MB
        if full_path.stat().st_size > max_size:
            return f"Error: File too large for review (max 10MB): {params.file_path}"

        original_content = read_file_content(full_path)
        review_result = await perform_code_review(
            full_path,
            params.review_depth,
            params.focus_areas,
        )
        write_review_comments(full_path, original_content, review_result)
        return (
            f"✅ Review completed. Comments added to: {params.file_path}\n\n"
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
