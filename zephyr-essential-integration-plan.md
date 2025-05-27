# Zephyr Essential Integration Plan

## 1. Overview

Based on the OpenAPI specification, I'll design a Python client for the Zephyr Essential API that integrates with the existing MCP-Atlassian project. This client will allow creating and updating test cases, adding test cases to existing test cycles, and executing test cases.

## 2. Project Structure

We'll add the following files to the project:

```
src/mcp_atlassian/
├── zephyr/
│   ├── __init__.py
│   ├── client.py         # Base client for Zephyr Essential API
│   ├── config.py         # Configuration for Zephyr Essential
│   ├── test_cases.py     # Test case operations
│   ├── test_cycles.py    # Test cycle operations
│   ├── test_executions.py # Test execution operations
│   └── test_steps.py     # Test step operations
├── models/
│   └── zephyr.py         # Data models for Zephyr Essential
```

## 3. Implementation Components

### 3.1. Authentication

Based on the TypeScript authentication code, we'll implement JWT-based authentication for Zephyr Essential using the PyJWT library:

```python
# src/mcp_atlassian/zephyr/auth.py
import hashlib
import time
from typing import Dict, Optional

import jwt  # PyJWT library

def generate_zephyr_jwt(
    method: str,
    api_path: str,
    query_params: Optional[Dict[str, str]] = None,
    access_key: str = "",
    secret_key: str = "",
    expiration_sec: int = 3600
) -> str:
    """
    Generate a JWT token for Zephyr API authentication.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        api_path: API path without base URL
        query_params: Query parameters as a dictionary
        access_key: Zephyr Access Key
        secret_key: Zephyr Secret Key
        expiration_sec: Token expiration time in seconds
        
    Returns:
        JWT token string
    """
    if query_params is None:
        query_params = {}
    
    # Sort query parameters alphabetically
    canonical_query = "&".join(
        f"{key}={query_params[key]}" 
        for key in sorted(query_params.keys())
    )
    
    # Build the canonical string: METHOD&<path>&<query>
    canonical = f"{method.upper()}&{api_path}&{canonical_query}"
    
    # Create SHA-256 hex hash of canonical string
    qsh = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    
    # Timestamps
    now = int(time.time())
    exp = now + expiration_sec
    
    # JWT claims
    payload = {
        "sub": account_id,  # Atlassian account ID
        "iss": access_key,  # Zephyr Access Key
        "qsh": qsh,         # query-string hash
        "iat": now,
        "exp": exp,
    }
    
    # Sign with HMAC-SHA256 using Zephyr Secret Key
    return jwt.encode(payload, secret_key, algorithm="HS256")
```

### 3.2. Configuration

Update the configuration class for Zephyr Essential to include JWT authentication parameters:

```python
# src/mcp_atlassian/zephyr/config.py
import os
from dataclasses import dataclass

@dataclass
class ZephyrConfig:
    """Configuration for Zephyr Essential API."""
    
    base_url: str
    account_id: str
    access_key: str
    secret_key: str
    
    @classmethod
    def from_env(cls) -> "ZephyrConfig":
        """Create configuration from environment variables."""
        base_url = os.getenv("ZAPI_BASE_URL", "https://prod-api.zephyr4jiracloud.com/connect")
        account_id = os.getenv("ZAPI_ACCOUNT_ID")
        access_key = os.getenv("ZAPI_ACCESS_KEY")
        secret_key = os.getenv("ZAPI_SECRET_KEY")
        
        if not all([account_id, access_key, secret_key]):
            raise ValueError("ZAPI_ACCOUNT_ID, ZAPI_ACCESS_KEY, and ZAPI_SECRET_KEY environment variables are required")
            
        return cls(
            base_url=base_url.rstrip('/'),
            account_id=account_id,
            access_key=access_key,
            secret_key=secret_key
        )
```

### 3.3. Base Client

Update the base client to use JWT authentication:

```python
# src/mcp_atlassian/zephyr/client.py
import logging
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .auth import generate_zephyr_jwt
from .config import ZephyrConfig

logger = logging.getLogger("mcp-zephyr")

class ZephyrClient:
    """Base client for Zephyr Essential API."""
    
    def __init__(self, config: ZephyrConfig = None):
        """Initialize the Zephyr client with configuration."""
        self.config = config or ZephyrConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
    def _request(self, method: str, endpoint: str, params: Dict[str, str] = None, **kwargs) -> Any:
        """Make a request to the Zephyr API with JWT authentication."""
        if params is None:
            params = {}
            
        url = f"{self.config.base_url}{endpoint}"
        
        # Parse the endpoint to get the path for JWT generation
        parsed_url = urlparse(url)
        api_path = parsed_url.path
        
        # Generate JWT token
        jwt_token = generate_zephyr_jwt(
            method=method,
            api_path=api_path,
            query_params=params,
            account_id=self.config.account_id,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key
        )
        
        # Add JWT token to Authorization header
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"JWT {jwt_token}"
        
        # Make the request
        response = self.session.request(
            method, 
            url, 
            params=params, 
            headers=headers, 
            **kwargs
        )
        
        try:
            response.raise_for_status()
            if response.content:
                return response.json()
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"Zephyr API error: {e}")
            if response.content:
                try:
                    error_data = response.json()
                    logger.error(f"Error details: {error_data}")
                except ValueError:
                    logger.error(f"Error response: {response.text}")
            raise
```
## 3. Implementation Components

### 3.1. Configuration

Create a configuration class for Zephyr Essential:

```python
# src/mcp_atlassian/zephyr/config.py
import os
from dataclasses import dataclass

@dataclass
class ZephyrConfig:
    """Configuration for Zephyr Essential API."""
    
    url: str
    access_token: str
    
    @classmethod
    def from_env(cls) -> "ZephyrConfig":
        """Create configuration from environment variables."""
        url = os.getenv("ZEPHYR_URL", "https://prod-api.zephyr4jiracloud.com/v2")
        access_token = os.getenv("ZEPHYR_ACCESS_TOKEN")
        
        if not access_token:
            raise ValueError("ZEPHYR_ACCESS_TOKEN environment variable is required")
            
        return cls(url=url, access_token=access_token)
```

### 3.2. Base Client

Create a base client for Zephyr Essential API:

```python
# src/mcp_atlassian/zephyr/client.py
import logging
import requests
from typing import Any, Dict, List, Optional

from .config import ZephyrConfig

logger = logging.getLogger("mcp-zephyr")

class ZephyrClient:
    """Base client for Zephyr Essential API."""
    
    def __init__(self, config: ZephyrConfig = None):
        """Initialize the Zephyr client with configuration."""
        self.config = config or ZephyrConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json"
        })
        
    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make a request to the Zephyr API."""
        url = f"{self.config.url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        
        try:
            response.raise_for_status()
            if response.content:
                return response.json()
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"Zephyr API error: {e}")
            if response.content:
                error_data = response.json()
                logger.error(f"Error details: {error_data}")
            raise
### 3.3. Data Models

Create data models for Zephyr Essential:

```python
# src/mcp_atlassian/models/zephyr.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class TestStep:
    """Model for a test step in Zephyr Essential."""
    
    description: str
    expected_result: str
    test_data: Optional[str] = None
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format."""
        return {
            "inline": {
                "description": self.description,
                "expectedResult": self.expected_result,
                "testData": self.test_data or ""
            }
        }

@dataclass
class TestCase:
    """Model for a Zephyr Essential test case."""
    
    key: Optional[str] = None
    name: Optional[str] = None
    project_key: Optional[str] = None
    priority_name: str = "Normal"
    status_name: str = "Draft"
    folder_id: Optional[int] = None
    steps: List[TestStep] = field(default_factory=list)
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "TestCase":
        """Create a TestCase from API response."""
        return cls(
            key=data.get("key"),
            name=data.get("name"),
            project_key=data.get("projectKey"),
            priority_name=data.get("priorityName"),
            status_name=data.get("statusName"),
            folder_id=data.get("folderId")
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format for creation."""
        result = {
            "projectKey": self.project_key,
            "name": self.name,
            "priorityName": self.priority_name,
            "statusName": self.status_name
        }
        
        if self.folder_id:
            result["folderId"] = self.folder_id
            
        return result

@dataclass
class TestExecution:
    """Model for a Zephyr Essential test execution."""
    
    key: Optional[str] = None
    project_key: Optional[str] = None
    test_case_key: Optional[str] = None
    test_cycle_key: Optional[str] = None
    status: str = "UNEXECUTED"
    environment_name: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "TestExecution":
        """Create a TestExecution from API response."""
        return cls(
            key=data.get("key"),
            project_key=data.get("projectKey"),
            test_case_key=data.get("testCaseKey"),
            test_cycle_key=data.get("testCycleKey"),
            status=data.get("status"),
            environment_name=data.get("environmentName")
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format for creation."""
        result = {
            "projectKey": self.project_key,
            "testCaseKey": self.test_case_key,
            "status": self.status
        }
        
        if self.test_cycle_key:
            result["testCycleKey"] = self.test_cycle_key
            
        if self.environment_name:
            result["environmentName"] = self.environment_name
## 3.8. Dependencies

Add the following dependencies to the project:

```
PyJWT>=2.6.0
```

This is required for JWT token generation and signing for Zephyr Essential authentication.
            
        return result
```

### 3.4. Test Case Operations

Implement test case operations:

```python
# src/mcp_atlassian/zephyr/test_cases.py
from typing import Any, Dict, List, Optional

from ..models.zephyr import TestCase, TestStep
from .client import ZephyrClient

class TestCaseMixin(ZephyrClient):
    """Mixin for Zephyr Essential test case operations."""
    
    def get_test_cases(self, project_key: str, folder_id: Optional[int] = None, 
                      max_results: int = 10, start_at: int = 0) -> List[TestCase]:
def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables."""
    
    # Existing code for Confluence and Jira...
    
    # Check for Zephyr Essential credentials
    zephyr_base_url = os.getenv("ZAPI_BASE_URL")
    zephyr_account_id = os.getenv("ZAPI_ACCOUNT_ID")
    zephyr_access_key = os.getenv("ZAPI_ACCESS_KEY")
    zephyr_secret_key = os.getenv("ZAPI_SECRET_KEY")
    zephyr_is_setup = all([zephyr_account_id, zephyr_access_key, zephyr_secret_key])
    
    return {
        "confluence": confluence_is_setup, 
        "jira": jira_is_setup,
        "zephyr": zephyr_is_setup
    }
        """Get test cases for a project."""
        params = {
            "projectKey": project_key,
            "maxResults": max_results,
            "startAt": start_at
        }
        
        if folder_id:
            params["folderId"] = folder_id
            
        response = self._request("GET", "/testcases", params=params)
        
        test_cases = []
        for item in response.get("values", []):
            test_cases.append(TestCase.from_api_response(item))
            
        return test_cases
    
    def get_test_case(self, test_case_key: str) -> TestCase:
        """Get a test case by key."""
        response = self._request("GET", f"/testcases/{test_case_key}")
        return TestCase.from_api_response(response)
    
    def create_test_case(self, test_case: TestCase) -> str:
        """Create a new test case."""
        data = test_case.to_api_dict()
        response = self._request("POST", "/testcases", json=data)
        return response.get("key")
    
    def update_test_case(self, test_case_key: str, test_case: TestCase) -> None:
        """Update an existing test case."""
        data = test_case.to_api_dict()
        self._request("PUT", f"/testcases/{test_case_key}", json=data)
        
    def get_test_steps(self, test_case_key: str) -> List[TestStep]:
        """Get test steps for a test case."""
        response = self._request("GET", f"/testcases/{test_case_key}/teststeps")
        
        steps = []
        for item in response.get("values", []):
            inline = item.get("inline", {})
            steps.append(TestStep(
                description=inline.get("description", ""),
                expected_result=inline.get("expectedResult", ""),
                test_data=inline.get("testData")
            ))
            
        return steps
    
    def add_test_steps(self, test_case_key: str, steps: List[TestStep]) -> None:
        """Add test steps to a test case."""
        data = {
            "mode": "OVERWRITE",
            "items": [step.to_api_dict() for step in steps]
        }
        self._request("POST", f"/testcases/{test_case_key}/teststeps", json=data)
```
### 3.5. Test Cycle Operations

Implement test cycle operations:

```python
# src/mcp_atlassian/zephyr/test_cycles.py
from typing import Any, Dict, List, Optional

from .client import ZephyrClient

class TestCycleMixin(ZephyrClient):
    """Mixin for Zephyr Essential test cycle operations."""
    
    def get_test_cycles(self, project_key: str, max_results: int = 10, start_at: int = 0) -> List[Dict[str, Any]]:
        """Get test cycles for a project."""
        params = {
            "projectKey": project_key,
            "maxResults": max_results,
            "startAt": start_at
        }
        
        response = self._request("GET", "/testcycles", params=params)
        return response.get("values", [])
    
    def get_test_cycle(self, test_cycle_id_or_key: str) -> Dict[str, Any]:
        """Get a test cycle by ID or key."""
        return self._request("GET", f"/testcycles/{test_cycle_id_or_key}")
    
    def add_test_case_to_cycle(self, test_cycle_id_or_key: str, test_case_key: str) -> None:
        """Add a test case to a test cycle."""
        # This is a simplified approach - in reality, we might need to create a test execution
        # to add a test case to a cycle
        data = {
            "projectKey": test_case_key.split("-")[0],
            "testCaseKey": test_case_key,
            "testCycleKey": test_cycle_id_or_key
        }
        self._request("POST", "/testexecutions", json=data)
```

### 3.6. Test Execution Operations

Implement test execution operations:

```python
# src/mcp_atlassian/zephyr/test_executions.py
from typing import Any, Dict, List, Optional

from ..models.zephyr import TestExecution
from .client import ZephyrClient

class TestExecutionMixin(ZephyrClient):
    """Mixin for Zephyr Essential test execution operations."""
    
    def get_test_executions(self, project_key: str, test_cycle_key: Optional[str] = None,
                           max_results: int = 10, start_at: int = 0) -> List[TestExecution]:
        """Get test executions for a project."""
        params = {
            "projectKey": project_key,
            "maxResults": max_results,
            "startAt": start_at
        }
        
        if test_cycle_key:
            params["testCycleKey"] = test_cycle_key
            
        response = self._request("GET", "/testexecutions", params=params)
        
        executions = []
        for item in response.get("values", []):
            executions.append(TestExecution.from_api_response(item))
            
        return executions
    
    def get_test_execution(self, test_execution_id_or_key: str) -> TestExecution:
        """Get a test execution by ID or key."""
        response = self._request("GET", f"/testexecutions/{test_execution_id_or_key}")
        return TestExecution.from_api_response(response)
    
    def create_test_execution(self, execution: TestExecution) -> str:
        """Create a new test execution."""
        data = execution.to_api_dict()
        response = self._request("POST", "/testexecutions", json=data)
        return response.get("key")
    
    def update_test_execution(self, test_execution_id_or_key: str, execution: TestExecution) -> None:
        """Update an existing test execution."""
        data = execution.to_api_dict()
        self._request("PUT", f"/testexecutions/{test_execution_id_or_key}", json=data)
```

### 3.7. Main Zephyr Fetcher Class

Create the main Zephyr fetcher class:

```python
# src/mcp_atlassian/zephyr/__init__.py
from .client import ZephyrClient
from .config import ZephyrConfig
from .test_cases import TestCaseMixin
from .test_cycles import TestCycleMixin
from .test_executions import TestExecutionMixin

class ZephyrFetcher(TestCaseMixin, TestCycleMixin, TestExecutionMixin):
    """Main class for Zephyr Essential operations."""
    pass
```
## 4. Server Integration

### 4.1. Update AppContext

Update the AppContext class in server.py to include Zephyr:

```python
@dataclass
class AppContext:
    """Application context for MCP Atlassian."""
    
    confluence: ConfluenceFetcher | None = None
    jira: JiraFetcher | None = None
    zephyr: ZephyrFetcher | None = None
```

### 4.2. Update get_available_services

Update the get_available_services function to check for Zephyr credentials:

```python
def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables."""
    
    # Existing code for Confluence and Jira...
    
    # Check for Zephyr Essential credentials
    zephyr_url = os.getenv("ZEPHYR_URL")
    zephyr_access_token = os.getenv("ZEPHYR_ACCESS_TOKEN")
    zephyr_is_setup = all([zephyr_url, zephyr_access_token])
    
    return {
        "confluence": confluence_is_setup, 
        "jira": jira_is_setup,
        "zephyr": zephyr_is_setup
    }
```

### 4.3. Update Server Lifespan

Update the server_lifespan function to initialize Zephyr:

```python
@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources."""
    # Get available services
    services = get_available_services()
    
    try:
        # Initialize services
        confluence = ConfluenceFetcher() if services["confluence"] else None
        jira = JiraFetcher() if services["jira"] else None
        zephyr = ZephyrFetcher() if services.get("zephyr") else None
        
        # Log the startup information
        logger.info("Starting MCP Atlassian server")
        
        # Log read-only mode status
        read_only = is_read_only_mode()
zephyr_url = zephyr.config.base_url
        logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")
        
        if confluence:
            confluence_url = confluence.config.url
            logger.info(f"Confluence URL: {confluence_url}")
        if jira:
            jira_url = jira.config.url
            logger.info(f"Jira URL: {jira_url}")
        if zephyr:
            zephyr_url = zephyr.config.url
            logger.info(f"Zephyr URL: {zephyr_url}")
        
        # Provide context to the application
        yield AppContext(confluence=confluence, jira=jira, zephyr=zephyr)
    finally:
        # Cleanup resources if needed
        pass
```

### 4.4. Add Zephyr Tools

Add new tools for Zephyr operations in the list_tools function:

```python
# Add Zephyr tools if Zephyr is configured
if ctx and ctx.zephyr:
    tools.extend([
        Tool(
            name="zephyr_create_test_case",
            description="Create a new Zephyr Essential test case",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "The project key (e.g., 'PROJ')"
                    },
                    "name": {
                        "type": "string",
                        "description": "Test case name/summary"
                    },
                    "priority_name": {
                        "type": "string",
                        "description": "Priority name (e.g., 'High', 'Normal', 'Low')",
                        "default": "Normal"
                    },
                    "status_name": {
                        "type": "string",
                        "description": "Status name (e.g., 'Draft', 'Approved')",
                        "default": "Draft"
                    },
                    "folder_id": {
                        "type": "integer",
                        "description": "Folder ID to place the test case in",
                        "default": None
                    },
                    "steps": {
                        "type": "string",
                        "description": "JSON array of test steps. Each step should have 'description', 'expected_result', and optional 'test_data' fields.",
                        "default": "[]"
                    }
                },
                "required": ["project_key", "name"]
            }
        ),
        Tool(
            name="zephyr_add_test_case_to_cycle",
            description="Add a test case to an existing test cycle",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_case_key": {
                        "type": "string",
                        "description": "The test case key (e.g., 'PROJ-T123')"
                    },
                    "test_cycle_key": {
                        "type": "string",
                        "description": "The test cycle key"
                    }
                },
                "required": ["test_case_key", "test_cycle_key"]
            }
        ),
        Tool(
            name="zephyr_create_test_execution",
            description="Create a new test execution for a test case",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "The project key (e.g., 'PROJ')"
                    },
                    "test_case_key": {
                        "type": "string",
                        "description": "The test case key (e.g., 'PROJ-T123')"
                    },
                    "test_cycle_key": {
                        "type": "string",
                        "description": "The test cycle key (optional)"
                    },
                    "status": {
                        "type": "string",
                        "description": "Execution status (e.g., 'PASS', 'FAIL', 'UNEXECUTED')",
                        "default": "UNEXECUTED"
                    },
                    "environment_name": {
                        "type": "string",
                        "description": "Environment name (optional)"
                    }
                },
                "required": ["project_key", "test_case_key"]
            }
        )
    ])
```

### 4.5. Implement Tool Handlers

Add handlers for the new tools in the call_tool function:

```python
# Zephyr operations
elif name == "zephyr_create_test_case" and ctx and ctx.zephyr:
    if not ctx or not ctx.zephyr:
        raise ValueError("Zephyr is not configured.")
    
    # Write operation - check read-only mode
    if read_only:
        return [TextContent("Operation 'zephyr_create_test_case' is not available in read-only mode.")]
    
    # Extract arguments
    project_key = arguments.get("project_key")
    name = arguments.get("name")
    priority_name = arguments.get("priority_name", "Normal")
    status_name = arguments.get("status_name", "Draft")
    folder_id = arguments.get("folder_id")
    steps_json = arguments.get("steps", "[]")
    
    # Parse steps JSON
    try:
        steps_data = json.loads(steps_json)
        steps = []
        for step_data in steps_data:
            steps.append(TestStep(
                description=step_data.get("description", ""),
                expected_result=step_data.get("expected_result", ""),
                test_data=step_data.get("test_data")
            ))
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format for steps")
    
    # Create the test case
    test_case = TestCase(
        project_key=project_key,
        name=name,
        priority_name=priority_name,
        status_name=status_name,
        folder_id=folder_id,
        steps=steps
    )
    
    test_case_key = ctx.zephyr.create_test_case(test_case)
    
    # Add steps if provided
    if steps:
        ctx.zephyr.add_test_steps(test_case_key, steps)
    
    return [
        TextContent(
            type="text",
            text=f"Test case created successfully with key: {test_case_key}"
        )
    ]

elif name == "zephyr_add_test_case_to_cycle" and ctx and ctx.zephyr:
    if not ctx or not ctx.zephyr:
        raise ValueError("Zephyr is not configured.")
    
    # Write operation - check read-only mode
    if read_only:
        return [TextContent("Operation 'zephyr_add_test_case_to_cycle' is not available in read-only mode.")]
    
    # Extract arguments
    test_case_key = arguments.get("test_case_key")
    test_cycle_key = arguments.get("test_cycle_key")
    
    # Add test case to cycle
    ctx.zephyr.add_test_case_to_cycle(test_cycle_key, test_case_key)
    
    return [
        TextContent(
            type="text",
            text=f"Test case {test_case_key} added to test cycle {test_cycle_key} successfully"
        )
    ]

elif name == "zephyr_create_test_execution" and ctx and ctx.zephyr:
    if not ctx or not ctx.zephyr:
        raise ValueError("Zephyr is not configured.")
    
    # Write operation - check read-only mode
    if read_only:
        return [TextContent("Operation 'zephyr_create_test_execution' is not available in read-only mode.")]
    
    # Extract arguments
    project_key = arguments.get("project_key")
    test_case_key = arguments.get("test_case_key")
    test_cycle_key = arguments.get("test_cycle_key")
    status = arguments.get("status", "UNEXECUTED")
    environment_name = arguments.get("environment_name")
    
    # Create the test execution
    execution = TestExecution(
        project_key=project_key,
        test_case_key=test_case_key,
        test_cycle_key=test_cycle_key,
        status=status,
        environment_name=environment_name
    )
    
    execution_key = ctx.zephyr.create_test_execution(execution)
    
    return [
        TextContent(
            type="text",
            text=f"Test execution created successfully with key: {execution_key}"
        )
    ]
```

## 5. Implementation Steps

1. Create the directory structure for the Zephyr module
2. Implement the configuration class
3. Implement the base client
4. Implement the data models
5. Implement the test case operations
6. Implement the test cycle operations
7. Implement the test execution operations
8. Update the server.py file to integrate Zephyr
9. Add unit tests for the Zephyr functionality
10. Update documentation

## 6. Testing

We should create unit tests for each component of the Zephyr integration:

1. Test the configuration class
2. Test the base client with mocked responses
3. Test the data models
4. Test the test case operations with mocked responses
5. Test the test cycle operations with mocked responses
6. Test the test execution operations with mocked responses
7. Test the server integration

## 7. Documentation

Update the project documentation to include information about the Zephyr Essential integration:

1. Add information about the required environment variables
2. Document the available tools and their parameters
3. Provide examples of how to use the tools