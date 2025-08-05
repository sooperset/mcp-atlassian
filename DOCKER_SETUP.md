# 🐳 MCP Atlassian Docker Setup

## ✅ Build Complete

The MCP Atlassian Docker container has been successfully built and is ready to use!

### 📊 Container Details
- **Image Name**: `mcp-atlassian:latest`
- **Image ID**: `1540ef2de151`
- **Size**: `123MB`
- **Base**: Python 3.10 Alpine Linux
- **Build Tool**: UV (ultra-fast Python package manager)

### 🛠️ Available Scripts

#### 1. **Run Container** (`./run-container.sh`)
Starts the MCP Atlassian server in a Docker container:
```bash
./run-container.sh
```
- Creates container named `mcp-atlassian-server`
- Exposes port `8000`
- Enables OAuth authentication
- Runs in background (detached mode)

#### 2. **Test Container** (`./test-container.sh`)
Tests if the container is running properly:
```bash
./test-container.sh
```
- Checks container status
- Tests server connectivity
- Shows recent logs
- Provides troubleshooting info

#### 3. **Stop Container** (`./stop-container.sh`)
Stops and removes the container:
```bash
./stop-container.sh
```
- Gracefully stops the running container
- Removes the stopped container
- Cleans up resources

### 🚀 Quick Start

1. **Start the container**:
   ```bash
   ./run-container.sh
   ```

2. **Verify it's working**:
   ```bash
   ./test-container.sh
   ```

3. **Access the server**:
   - Server: `http://localhost:8000`
   - Health Check: `http://localhost:8000/health`

4. **Stop when done**:
   ```bash
   ./stop-container.sh
   ```

### 🔧 Container Management

#### View Logs
```bash
# View all logs
docker logs mcp-atlassian-server

# Follow logs in real-time
docker logs -f mcp-atlassian-server

# View last 20 lines
docker logs --tail=20 mcp-atlassian-server
```

#### Enter Container
```bash
# Open shell inside container
docker exec -it mcp-atlassian-server /bin/sh

# Run commands inside container
docker exec mcp-atlassian-server mcp-atlassian --help
```

#### Container Status
```bash
# Check if container is running
docker ps --filter name=mcp-atlassian-server

# View all containers (running and stopped)
docker ps -a --filter name=mcp-atlassian-server
```

### 🔒 Authentication Setup

The container is configured with OAuth enabled. You'll need to provide authentication via:

1. **Environment Variables** (when running):
   ```bash
   docker run -e JIRA_URL="your-jira-url" \
              -e JIRA_TOKEN="your-token" \
              -e CONFLUENCE_URL="your-confluence-url" \
              -e CONFLUENCE_TOKEN="your-token" \
              mcp-atlassian
   ```

2. **HTTP Headers** (when making requests):
   ```
   Authorization: Bearer <your_oauth_token>
   X-Atlassian-Cloud-Id: <your_cloud_id>
   ```

### 🐛 Troubleshooting

#### Container Won't Start
1. Check if port 8000 is already in use:
   ```bash
   lsof -i :8000
   ```

2. View detailed logs:
   ```bash
   docker logs mcp-atlassian-server
   ```

3. Check container status:
   ```bash
   docker ps -a --filter name=mcp-atlassian-server
   ```

#### Server Not Responding
1. Wait a few seconds for startup
2. Check logs for errors
3. Verify port mapping: `localhost:8000 -> container:8000`
4. Test with curl: `curl http://localhost:8000`

#### Permission Issues
The container runs as a non-root user (`app`) for security. If you need to mount volumes, ensure proper permissions.

### 📦 Dockerfile Features

- **Multi-stage build** for smaller final image
- **UV package manager** for fast dependency installation
- **Alpine Linux** base for minimal size
- **Non-root user** for security
- **Optimized layers** with caching
- **Clean virtual environment** without cache files

### 🔄 Rebuilding

If you make changes to the code and need to rebuild:

```bash
# Rebuild the image
docker build -t mcp-atlassian .

# Stop and remove old container
./stop-container.sh

# Start new container with updated image
./run-container.sh
```

### 📋 Integration with VS Code

Once the container is running, you can configure VS Code to use it as an MCP server:

1. Update your VS Code `settings.json`:
   ```json
   {
     "mcp.servers": {
       "mcp-atlassian": {
         "command": "docker",
         "args": ["exec", "mcp-atlassian-server", "mcp-atlassian"]
       }
     }
   }
   ```

2. Or use HTTP transport:
   ```json
   {
     "mcp.servers": {
       "mcp-atlassian": {
         "transport": "http",
         "url": "http://localhost:8000"
       }
     }
   }
   ```

### 🎯 Container Benefits

✅ **Isolation**: No conflicts with system Python or dependencies  
✅ **Portability**: Runs consistently across different machines  
✅ **Security**: Non-root user and minimal attack surface  
✅ **Performance**: Optimized build with UV package manager  
✅ **Simplicity**: One-command deployment with helper scripts  
✅ **Debugging**: Easy log access and container inspection  

---

🎉 **Your MCP Atlassian server is now containerized and ready to use!**

The container includes all the attachment management tools we implemented earlier, providing a complete Confluence and Jira integration solution.
