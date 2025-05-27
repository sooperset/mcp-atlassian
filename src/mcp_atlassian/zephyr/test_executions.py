"""Module for Zephyr Essential test execution operations."""

from typing import Any, Dict, List, Optional

from ..models.zephyr import TestExecution
from .client import ZephyrClient


class TestExecutionMixin(ZephyrClient):
    """Mixin for Zephyr Essential test execution operations."""
    
    def get_test_executions(
        self, 
        project_key: str, 
        test_cycle_key: Optional[str] = None,
        max_results: int = 10, 
        start_at: int = 0
    ) -> List[TestExecution]:
        """Get test executions for a project.
        
        Args:
            project_key: The project key (e.g., 'PROJ')
            test_cycle_key: Optional test cycle key to filter by
            max_results: Maximum number of results to return
            start_at: Index of the first result to return
            
        Returns:
            List of TestExecution objects
        """
        params = {
            "projectKey": project_key,
            "maxResults": str(max_results),
            "startAt": str(start_at)
        }
        
        if test_cycle_key:
            params["testCycleKey"] = test_cycle_key
            
        response = self._request("GET", "/testexecutions", params=params)
        
        executions = []
        for item in response.get("values", []):
            executions.append(TestExecution.from_api_response(item))
            
        return executions
    
    def get_test_execution(self, test_execution_id_or_key: str) -> TestExecution:
        """Get a test execution by ID or key.
        
        Args:
            test_execution_id_or_key: The test execution ID or key
            
        Returns:
            TestExecution object
            
        Raises:
            requests.exceptions.HTTPError: If the test execution doesn't exist
        """
        response = self._request("GET", f"/testexecutions/{test_execution_id_or_key}")
        return TestExecution.from_api_response(response)
    
    def create_test_execution(self, execution: TestExecution) -> str:
        """Create a new test execution.
        
        Args:
            execution: The test execution to create
            
        Returns:
            The key of the created test execution
            
        Raises:
            requests.exceptions.HTTPError: If the test execution creation fails
        """
        data = execution.to_api_dict()
        response = self._request("POST", "/testexecutions", json=data)
        return response.get("key")
    
    def update_test_execution(self, test_execution_id_or_key: str, execution: TestExecution) -> None:
        """Update an existing test execution.
        
        Args:
            test_execution_id_or_key: The key of the test execution to update
            execution: The updated test execution data
            
        Raises:
            requests.exceptions.HTTPError: If the test execution update fails
        """
        data = execution.to_api_dict()
        self._request("PUT", f"/testexecutions/{test_execution_id_or_key}", json=data)