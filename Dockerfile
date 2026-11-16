# syntax=docker/dockerfile:1
#
# Image for portfolio-knowledge-graph. It carries the same instructions as
# .devcontainer/devcontainer.json (keep the two in step; see README "Container image"):
#   - base image  mcr.microsoft.com/devcontainers/python:1-3.12-bookworm
#   - feature     ghcr.io/va-h/devcontainers-features/uv:1 -> uv, here from the
#                 official astral-sh/uv image (same binary, pinned; see UV_VERSION)
#   - remoteEnv   UV_LINK_MODE=copy
#   - postCreate  scripts/init.sh (uv sync --frozen --group dev, pre-commit hooks,
#                 Claude Code CLI, gh)
#
# Not carried over, because they only make sense inside VS Code / at `docker run`:
#   - "mounts"  (the THESIS_HOST_DIR bind to /workspaces/thesis) -> pass it at run time
#   - "runArgs" (--env-file .env)                                 -> pass it at run time
#   - "customizations.vscode" (extensions/settings)
#   - `pre-commit install`: the image has no .git. Run it once in a mounted checkout
#     (README "Container image"); the pre-commit tool itself is in the image's .venv.
#
# Build:  docker build -t portfolio-knowledge-graph .
# Run:    see README "Container image".
#
# Build needs network access: PyPI, the portfolio-common git tag on GitHub
# (pyproject.toml [tool.uv.sources]), claude.ai and the Debian mirrors.

ARG UV_VERSION=0.13.8
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The devcontainer "uv" feature: install uv and its shell completion.
COPY --from=uv /uv /uvx /usr/local/bin/
RUN uv generate-shell-completion bash > /etc/bash_completion.d/uv

# remoteEnv
ENV UV_LINK_MODE=copy

# The devcontainer base image's non-root user (the devcontainer runs as it too).
USER vscode
WORKDIR /workspaces/portfolio-knowledge-graph

# postCreateCommand step 1 (init.sh: uv sync --frozen --group dev). Only the
# dependency inputs are copied first, so editing a doc or a test does not
# re-download the dependencies. `package = false` in pyproject.toml means the
# project itself is never installed, so --no-install-project is the whole sync.
COPY --chown=vscode:vscode pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --group dev --no-install-project
ENV PATH="/workspaces/portfolio-knowledge-graph/.venv/bin:${PATH}"

# The code, minus what .dockerignore excludes (.env, .venv, .git, caches).
COPY --chown=vscode:vscode . .

# postCreateCommand steps 3-4 (Claude Code CLI and gh). The installer verifies the
# binary's checksum; the version is pinned (bump it deliberately). Debian's gh
# (2.23.0) is what init.sh installs too. The base image's yarn apt source has an
# expired signing key and would fail `apt-get update`; drop it (init.sh needs
# the same fix, see the note there).
ARG CLAUDE_CODE_VERSION=2.1.325
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- ${CLAUDE_CODE_VERSION} \
    && sudo rm -f /etc/apt/sources.list.d/yarn.list \
    && sudo apt-get update \
    && sudo apt-get install -y --no-install-recommends gh \
    && sudo rm -rf /var/lib/apt/lists/*
ENV PATH="/home/vscode/.local/bin:${PATH}"

CMD ["bash"]
