# Adapted from https://github.com/astral-sh/uv-docker-example/blob/main/Dockerfile

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_LINK_MODE=copy

# Install system dependencies
RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    libsasl2-dev \
    python3-dev \
    libldap2-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY uv.lock pyproject.toml ./

# Install dependencies without the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Copy the entire project
COPY . /app

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Set PATH to include virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Expose ports for both HTTP and HTTPS
EXPOSE 8000 8443

# Use our dual-port startup script with SSL support
CMD ["python", "start_dual.py"]
