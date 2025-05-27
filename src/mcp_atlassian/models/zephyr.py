"""Data models for Zephyr Essential API."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestStep:
    """Model for a test step in Zephyr Essential."""
    
    description: str
    expected_result: str
    test_data: Optional[str] = None
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format.
        
        Returns:
            Dictionary representation of the test step for API requests
        """
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
        """Create a TestCase from API response.
        
        Args:
            data: API response data
            
        Returns:
            TestCase object populated with data from the API response
        """
        return cls(
            key=data.get("key"),
            name=data.get("name"),
            project_key=data.get("projectKey"),
            priority_name=data.get("priorityName"),
            status_name=data.get("statusName"),
            folder_id=data.get("folderId")
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format for creation.
        
        Returns:
            Dictionary representation of the test case for API requests
        """
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
        """Create a TestExecution from API response.
        
        Args:
            data: API response data
            
        Returns:
            TestExecution object populated with data from the API response
        """
        return cls(
            key=data.get("key"),
            project_key=data.get("projectKey"),
            test_case_key=data.get("testCaseKey"),
            test_cycle_key=data.get("testCycleKey"),
            status=data.get("status"),
            environment_name=data.get("environmentName")
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API dictionary format for creation.
        
        Returns:
            Dictionary representation of the test execution for API requests
        """
        result = {
            "projectKey": self.project_key,
            "testCaseKey": self.test_case_key,
            "status": self.status
        }
        
        if self.test_cycle_key:
            result["testCycleKey"] = self.test_cycle_key
            
        if self.environment_name:
            result["environmentName"] = self.environment_name
            
        return result