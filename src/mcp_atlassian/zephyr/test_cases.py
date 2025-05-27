"""Module for Zephyr Essential test case operations."""

from typing import Any, Dict, List, Optional

from ..models.zephyr import TestCase, TestStep
from .client import ZephyrClient


class TestCaseMixin(ZephyrClient):
    """Mixin for Zephyr Essential test case operations."""
    
    def get_test_cases(
        self, 
        project_key: str, 
        folder_id: Optional[int] = None,
        max_results: int = 10, 
        start_at: int = 0
    ) -> List[TestCase]:
        """Get test cases for a project.
        
        Args:
            project_key: The project key (e.g., 'PROJ')
            folder_id: Optional folder ID to filter by
            max_results: Maximum number of results to return
            start_at: Index of the first result to return
            
        Returns:
            List of TestCase objects
        """
        params = {
            "projectKey": project_key,
            "maxResults": str(max_results),
            "startAt": str(start_at)
        }
        
        if folder_id:
            params["folderId"] = str(folder_id)
            
        response = self._request("GET", "/testcases", params=params)
        
        test_cases = []
        for item in response.get("values", []):
            test_cases.append(TestCase.from_api_response(item))
            
        return test_cases
    
    def get_test_case(self, test_case_key: str) -> TestCase:
        """Get a test case by key.
        
        Args:
            test_case_key: The test case key (e.g., 'PROJ-T123')
            
        Returns:
            TestCase object
            
        Raises:
            requests.exceptions.HTTPError: If the test case doesn't exist
        """
        response = self._request("GET", f"/testcases/{test_case_key}")
        return TestCase.from_api_response(response)
    
    def create_test_case(self, test_case: TestCase) -> str:
        """Create a new test case.
        
        Args:
            test_case: The test case to create
            
        Returns:
            The key of the created test case
            
        Raises:
            requests.exceptions.HTTPError: If the test case creation fails
        """
        data = test_case.to_api_dict()
        response = self._request("POST", "/testcases", json=data)
        return response.get("key")
    
    def update_test_case(self, test_case_key: str, test_case: TestCase) -> None:
        """Update an existing test case.
        
        Args:
            test_case_key: The key of the test case to update
            test_case: The updated test case data
            
        Raises:
            requests.exceptions.HTTPError: If the test case update fails
        """
        data = test_case.to_api_dict()
        self._request("PUT", f"/testcases/{test_case_key}", json=data)
        
    def get_test_steps(self, test_case_key: str) -> List[TestStep]:
        """Get test steps for a test case.
        
        Args:
            test_case_key: The test case key (e.g., 'PROJ-T123')
            
        Returns:
            List of TestStep objects
            
        Raises:
            requests.exceptions.HTTPError: If the test case doesn't exist
        """
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
        """Add test steps to a test case.
        
        Args:
            test_case_key: The test case key (e.g., 'PROJ-T123')
            steps: List of test steps to add
            
        Raises:
            requests.exceptions.HTTPError: If adding the test steps fails
        """
        data = {
            "mode": "OVERWRITE",
            "items": [step.to_api_dict() for step in steps]
        }
        self._request("POST", f"/testcases/{test_case_key}/teststeps", json=data)