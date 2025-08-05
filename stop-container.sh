#!/bin/bash
# Script to stop and clean up the MCP Atlassian container

set -e

CONTAINER_NAME="mcp-atlassian-server"

echo "🛑 Stopping MCP Atlassian Container"
echo "==================================="

# Check if container is running
if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "⏹️  Stopping running container..."
    docker stop "${CONTAINER_NAME}"
    echo "✅ Container stopped"
else
    echo "ℹ️  Container is not currently running"
fi

# Remove the container
if docker ps -a --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "🧹 Removing stopped container..."
    docker rm "${CONTAINER_NAME}"
    echo "✅ Container removed"
else
    echo "ℹ️  No container to remove"
fi

echo
echo "🏁 Cleanup complete!"
echo "   You can now run './run-container.sh' to start a fresh container"
