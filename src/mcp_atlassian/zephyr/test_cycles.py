"""Module for Zephyr Essential test cycle operations."""

from typing import Any, Dict, List, Optional

from .client import ZephyrClient


class TestCycleMixin(ZephyrClient):
    """Mixin for Zephyr Essential test cycle operations."""
    
    def get_test_cycles(
        self, 
        project_key: str, 
        max_results: int = 10, 
        start_at: int = 0
    ) -> List[Dict[str, Any]]:
        """Get test cycles for a project.
        
        Args:
            project_key: The project key (e.g., 'PROJ')
            max_results: Maximum number of results to return
            start_at: Index of the first result to return
            
        Returns:
            List of test cycle dictionaries
        """
        params = {
            "projectKey": project_key,
            "maxResults": str(max_results),
            "startAt": str(start_at)
        }
        
        response = self._request("GET", "/testcycles", params=params)
        return response.get("values", [])
    
    def get_test_cycle(self, test_cycle_id_or_key: str) -> Dict[str, Any]:
        """Get a test cycle by ID or key.
        
        Args:
            test_cycle_id_or_key: The test cycle ID or key
            
        Returns:
            Test cycle dictionary
            
        Raises:
            requests.exceptions.HTTPError: If the test cycle doesn't exist
        """
        return self._request("GET", f"/testcycles/{test_cycle_id_or_key}")
    
    def add_test_case_to_cycle(self, test_cycle_id_or_key: str, test_case_key: str) -> None:
        """Add a test case to a test cycle.
        
        This creates a test execution for the test case in the specified cycle.
        
        Args:
            test_cycle_id_or_key: The test cycle ID or key
            test_case_key: The test case key (e.g., 'PROJ-T123')
            
        Raises:
            requests.exceptions.HTTPError: If adding the test case fails
        """
        # Extract project key from test case key (e.g., 'PROJ-T123' -> 'PROJ')
        project_key = test_case_key.split("-")[0]
        
        data = {
            "projectKey": project_key,
            "testCaseKey": test_case_key,
            "testCycleKey": test_cycle_id_or_key
        }
        self._request("POST", "/testexecutions", json=data)