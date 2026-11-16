# scripts/init.sh
#!/bin/bash
uv sync --frozen --group dev
uv run pre-commit install --install-hooks
source .venv/bin/activate
curl -fsSL https://claude.ai/install.sh | bash
# The base image's yarn apt source has an expired signing key and fails `apt update`.
sudo rm -f /etc/apt/sources.list.d/yarn.list
sudo apt update
sudo apt install gh -y