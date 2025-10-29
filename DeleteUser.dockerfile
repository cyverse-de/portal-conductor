# Minimal Dockerfile for running the delete-user.py CLI script
# This is designed to be used as a batch job in the Discovery Environment

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_LINK_MODE=copy
ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

# Install system dependencies required for python-ldap and python-irodsclient
RUN apt update -y && \
    apt install -y --no-install-recommends \
        build-essential \
        libsasl2-dev \
        python3-dev \
        libldap2-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY uv.lock pyproject.toml ./

# Install dependencies without the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Copy the entire project (needed for uv sync to work properly)
COPY . /app

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Clean up unnecessary files to keep image smaller
RUN rm -rf tests/ .git/ .github/ *.md start*.py handlers/ main.py

# Set PATH to include virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Set the entrypoint to run the delete-user.py script with uv
ENTRYPOINT ["uv", "run", "python", "scripts/delete-user.py"]

# Default command shows help (can be overridden with username argument)
CMD ["--help"]
