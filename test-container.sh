#!/bin/bash
# Script to test the MCP Atlassian container

set -e

CONTAINER_NAME="mcp-atlassian-server"
PORT="8000"

echo "🧪 Testing MCP Atlassian Container"
echo "================================="

# Check if container is running
if ! docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Container '${CONTAINER_NAME}' is not running"
    echo "   Run './run-container.sh' first"
    exit 1
fi

echo "✅ Container is running"
echo

# Wait a moment for the server to start
echo "⏳ Waiting for server to be ready..."
sleep 3

# Test if the server is responding
echo "🔍 Testing server connectivity..."

# Try to connect to the server (basic connectivity test)
if curl -s -f "http://localhost:${PORT}" > /dev/null 2>&1; then
    echo "✅ Server is responding on port ${PORT}"
elif curl -s -f "http://localhost:${PORT}/health" > /dev/null 2>&1; then
    echo "✅ Server health endpoint is responding"
else
    echo "⚠️  Server might still be starting up or there could be an issue"
    echo "   Checking container logs..."
    echo
    docker logs --tail=20 "${CONTAINER_NAME}"
fi

echo
echo "📊 Container Status:"
docker ps --filter name="${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "📋 Recent Container Logs:"
echo "-------------------------"
docker logs --tail=10 "${CONTAINER_NAME}"

echo
echo "🔧 Useful Commands:"
echo "   View all logs: docker logs ${CONTAINER_NAME}"
echo "   Follow logs: docker logs -f ${CONTAINER_NAME}"
echo "   Enter container: docker exec -it ${CONTAINER_NAME} /bin/sh"
echo "   Stop container: ./stop-container.sh"
