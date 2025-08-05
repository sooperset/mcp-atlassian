#!/bin/bash
# Script to run the MCP Atlassian container

set -e

echo "🐳 Starting MCP Atlassian Container"
echo "=================================="

# Default values
CONTAINER_NAME="mcp-atlassian-server"
PORT="8000"
IMAGE_NAME="mcp-atlassian:latest"

# Check if container is already running
if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Container '${CONTAINER_NAME}' is already running"
    echo "   Use 'docker stop ${CONTAINER_NAME}' to stop it first"
    exit 1
fi

# Remove existing stopped container if it exists
if docker ps -a --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "🧹 Removing existing stopped container..."
    docker rm "${CONTAINER_NAME}"
fi

echo "🚀 Starting new container..."
echo "   📦 Image: ${IMAGE_NAME}"
echo "   🏷️  Name: ${CONTAINER_NAME}"
echo "   🌐 Port: ${PORT}"
echo

# Run the container
docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${PORT}:8000" \
    -e ATLASSIAN_OAUTH_ENABLE=true \
    "${IMAGE_NAME}"

echo "✅ Container started successfully!"
echo
echo "📋 Container Information:"
echo "   Container ID: $(docker ps --filter name=${CONTAINER_NAME} --format '{{.ID}}')"
echo "   Status: $(docker ps --filter name=${CONTAINER_NAME} --format '{{.Status}}')"
echo "   Port Mapping: localhost:${PORT} -> container:8000"
echo
echo "🔗 Available endpoints:"
echo "   Health Check: http://localhost:${PORT}/health"
echo "   MCP Server: http://localhost:${PORT}"
echo
echo "📊 To check logs:"
echo "   docker logs ${CONTAINER_NAME}"
echo "   docker logs -f ${CONTAINER_NAME}  # Follow logs"
echo
echo "🛑 To stop the container:"
echo "   docker stop ${CONTAINER_NAME}"
echo
echo "🔧 To enter the container:"
echo "   docker exec -it ${CONTAINER_NAME} /bin/sh"
echo
echo "🏃‍♂️ Container is now running and ready to accept MCP connections!"
