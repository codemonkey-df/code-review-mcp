# code-review-mcp

MCP server for **AI-powered code review** using [LiteLLM](https://docs.litellm.ai/) and an OpenAI-compatible LLM proxy. Use it from Cursor (or any MCP client) to review files in your workspace and get inline suggestions.

---

## Purpose

This repo provides a **Model Context Protocol (MCP)** server that:

- **Reviews code files** via an LLM (through your proxy) and **writes inline comments** with suggestions, bug hints, security/performance notes, and style improvements.
- **Lists workspace files** so clients can discover what to review.

The server runs in a container (or locally with UV), mounts your project as a workspace, and exposes two tools: `review_code_file` and `list_workspace_files`. It is designed to work with Cursor’s MCP integration and any LLM backend exposed as an OpenAI-compatible API (e.g. LiteLLM proxy, OpenAI, Azure, etc.).

---

## Using it as MCP (e.g. in Cursor)

### 1. Configure environment

Copy the example env and set your LLM proxy and project path:

```bash
cp env.example .env
# Edit .env: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, PROJECT_DIR
```

Required variables:

| Variable       | Description |
|----------------|-------------|
| `LLM_BASE_URL` | OpenAI-compatible proxy base URL (e.g. `https://your-proxy.example.com/v1`) |
| `LLM_API_KEY`  | API key for the proxy |
| `LLM_MODEL`    | Model name (e.g. `gpt-4`, `claude-3-sonnet`, or your proxy’s model id) |
| `PROJECT_DIR`  | Absolute path to the project you want to review (used for Docker mount) |

### 2. Build the Docker image

```bash
./setup.sh
# or: docker compose build
```

### 3. Add the server to Cursor’s MCP config

In Cursor: **Settings → MCP** (or edit your MCP config file, e.g. `~/.cursor/mcp.json` or project-level config). Add a server entry like this, replacing the placeholder values with your own:

```json
{
  "mcpServers": {
    "code-review": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "LLM_BASE_URL=https://your-llm-proxy.example.com",
        "-e", "LLM_API_KEY=your_llm_proxy_api_key_here",
        "-e", "LLM_MODEL=gpt-4",
        "-v", "/absolute/path/to/your/project:/workspace:rw",
        "code-review-mcp:latest"
      ],
      "description": "AI-powered code review via LLM proxy",
      "disabled": false
    }
  }
}
```

Important:

- **`-v /path/to/your/project:/workspace:rw`** must point to the repo you want to review; the server reads and writes files under `/workspace`.
- **`LLM_*`** env vars in `args` override any defaults; use the same values as in your `.env` (or omit and rely on image defaults if you baked them into the image).

After saving, Cursor will list the **code-review** MCP server and its tools. You can then ask the AI to “review `src/main.py`” or “list files in `src`”; it will call `review_code_file` and `list_workspace_files` as needed.

### 4. (Optional) Run without Docker (local)

Install [UV](https://docs.astral.sh/uv/) and run the server directly:

```bash
uv sync
export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...
export WORKSPACE_DIR=/path/to/your/project   # or PROJECT_DIR for consistency with .env
uv run python src/server.py
```

For Cursor, you’d point MCP at this process (e.g. via a wrapper script that sets env and runs `uv run python src/server.py`) instead of the `docker run` command above.

---

## MCP tools

| Tool | Description |
|------|-------------|
| **review_code_file** | Review a file in the workspace and add inline comments with suggestions and improvements. Options: `file_path` (required), `review_depth` (`quick` / `standard` / `thorough`), `focus_areas` (e.g. `"security, performance"`). |
| **list_workspace_files** | List files under the workspace (or a subdirectory). Option: `directory` (default `"."`). Ignores `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`. |

---

## Setup reference

- **Environment:** See `env.example` for all variables. Never commit real secrets; use `.env` (gitignored) or env vars.
- **Docker:** `./setup.sh` checks Docker/Compose, creates `.env` if needed, and builds `code-review-mcp:latest`. Then `docker compose up` runs the server (stdio MCP).
- **Local dev:** `uv sync && uv run python src/server.py` (ensure `LLM_*` and `WORKSPACE_DIR` are set).

For more on Cursor MCP, see [Cursor MCP documentation](https://docs.cursor.com/context/model-context-protocol).
