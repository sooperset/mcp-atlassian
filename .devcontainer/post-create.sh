#! /bin/bash

set -xe

# Install dependencies globally in the container (no venv needed)
# Use sudo since we're installing to system directories
# Install with dev dependency group
sudo uv pip install --system -e . --group dev

# Fix git safe.directory for Windows mounts
git config --global --add safe.directory /workspaces/mcp-atlassian

# Install GitHub CLI
echo "Installing GitHub CLI..."
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
  sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg

sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
  sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# Fix Yarn repository GPG key issue (if it exists)
if [ -f /etc/apt/sources.list.d/yarn.list ]; then
  echo "Fixing Yarn repository..."
  curl -fsSL https://dl.yarnpkg.com/debian/pubkey.gpg | sudo gpg --dearmor -o /usr/share/keyrings/yarnkey.gpg
  echo "deb [signed-by=/usr/share/keyrings/yarnkey.gpg] https://dl.yarnpkg.com/debian stable main" | \
    sudo tee /etc/apt/sources.list.d/yarn.list > /dev/null
fi

sudo apt update
sudo apt install gh -y

echo "✅ GitHub CLI installed successfully!"
echo ""
echo "ℹ️  GitHub Copilot is built into this version of gh"
echo "⚠️  To use it, authenticate with: gh auth login"
echo "📝 Then try: gh copilot suggest 'your command here'"
echo ""
