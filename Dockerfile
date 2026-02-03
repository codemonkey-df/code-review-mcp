FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build-time args for LLM proxy config (supply via docker build --build-arg or compose build args)
ARG LLM_API_KEY
ARG LLM_BASE_URL
ARG LLM_MODEL
ENV LLM_API_KEY=${LLM_API_KEY}
ENV LLM_BASE_URL=${LLM_BASE_URL}
ENV LLM_MODEL=${LLM_MODEL}

# Copy dependency manifests and install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy server code from src/ into /app (so CMD can run server.py)
COPY src/ .
COPY README.md .

# Create workspace directory (will be mounted from host)
RUN mkdir -p /workspace

# Runtime environment
ENV PYTHONUNBUFFERED=1
ENV WORKSPACE_DIR=/workspace

RUN chmod +x server.py

# Run MCP server with UV
CMD ["uv", "run", "server.py"]
