# syntax=docker/dockerfile:1
#
# Image for portfolio-knowledge-graph. It carries the same instructions as
# .devcontainer/devcontainer.json (keep the two in step):
#   - base image  mcr.microsoft.com/devcontainers/python:1-3.12-bookworm
#   - feature     ghcr.io/va-h/devcontainers-features/uv:1 (latest)
#   - remoteEnv   UV_LINK_MODE=copy
#   - postCreate  scripts/init.sh (uv sync --frozen --group dev, pre-commit hooks,
#                 Claude Code CLI, gh)
#
# Not carried over, because they only make sense inside VS Code / at `docker run`:
#   - "mounts"  (the THESIS_HOST_DIR bind to /workspaces/thesis) -> pass it at run time
#   - "runArgs" (--env-file .env)                                 -> pass it at run time
#   - "customizations.vscode" (extensions/settings)
#
# Build:  docker build -t portfolio-knowledge-graph .
# Run:    docker run --rm -it --env-file .env \
#           -v "$THESIS_HOST_DIR:/workspaces/thesis" portfolio-knowledge-graph

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The devcontainer "uv" feature: install uv (latest) and its shell completion.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN uv generate-shell-completion bash > /etc/bash_completion.d/uv 2>/dev/null || true

# remoteEnv
ENV UV_LINK_MODE=copy

# The devcontainer base image's non-root user (the devcontainer runs as it too).
USER vscode
WORKDIR /workspaces/portfolio-knowledge-graph

# The code, minus what .dockerignore excludes (.env, .venv, .git, caches).
COPY --chown=vscode:vscode . .

# postCreateCommand: bash scripts/init.sh. Its steps are run explicitly so a
# failure points at one of them, and so that the ones that need a git checkout
# (pre-commit) or the network at run time don't break the build.
RUN uv sync --frozen --group dev
ENV PATH="/workspaces/portfolio-knowledge-graph/.venv/bin:${PATH}"

# init.sh's remaining steps (the Claude Code CLI and gh). The base image's yarn
# apt source has an expired signing key and would fail `apt-get update`; drop it.
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && sudo rm -f /etc/apt/sources.list.d/yarn.list \
    && sudo apt-get update \
    && sudo apt-get install -y --no-install-recommends gh \
    && sudo rm -rf /var/lib/apt/lists/*
ENV PATH="/home/vscode/.local/bin:${PATH}"

CMD ["bash"]
