#!/bin/bash
# push-to-gar.sh
# Script to manually push mcp-atlassian Docker image to DroneDeploy's Google Artifact Registry

set -euo pipefail

IMAGE_NAME="mcp-atlassian"
GAR_REGISTRY="us-docker.pkg.dev"
GAR_PROJECT="dronedeploy-code-delivery-0"
GAR_REPOSITORY="docker-dronedeploy-us"
GAR_IMAGE="${GAR_REGISTRY}/${GAR_PROJECT}/${GAR_REPOSITORY}/${IMAGE_NAME}"

# Get current branch or use 'main' as default
BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "🚀 Pushing mcp-atlassian to Google Artifact Registry"
echo "=================================================="
echo "Registry: ${GAR_REGISTRY}"
echo "Project: ${GAR_PROJECT}"
echo "Repository: ${GAR_REPOSITORY}"
echo "Branch: ${BRANCH_NAME}"
echo "Git Hash: ${GIT_HASH}"
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ No active gcloud authentication found"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Configure Docker for GAR
echo "🔐 Configuring Docker authentication for GAR..."
gcloud auth configure-docker ${GAR_REGISTRY} --quiet

# Build the image
echo ""
echo "🔨 Building Docker image..."
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ${GAR_IMAGE}:${BRANCH_NAME} \
  -t ${GAR_IMAGE}:${GIT_HASH} \
  -t ${GAR_IMAGE}:latest \
  --push \
  .

echo ""
echo "✅ Successfully pushed to:"
echo "   - ${GAR_IMAGE}:${BRANCH_NAME}"
echo "   - ${GAR_IMAGE}:${GIT_HASH}"
echo "   - ${GAR_IMAGE}:latest"
echo ""
echo "📋 To pull the image:"
echo "   docker pull ${GAR_IMAGE}:${BRANCH_NAME}"
