"""Module for Jira labels operations."""

import logging
from typing import Any

import requests

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class LabelsMixin(JiraClient):
    """Mixin for Jira labels operations."""

    def get_all_labels(
        self,
        start_at: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """
        Get all labels from Jira.

        Args:
            start_at: Starting index for pagination
            max_results: Maximum number of labels to return

        Returns:
            Dictionary containing pagination info and list of labels:
            {
                "startAt": 0,
                "maxResults": 50,
                "total": 100,
                "isLast": false,
                "values": ["label1", "label2", ...]
            }

        Raises:
            Exception: If there is an error retrieving the labels
        """
        try:
            params = {
                "startAt": start_at,
                "maxResults": max_results,
            }
            
            response = self.jira.get("/rest/api/3/label", params=params)
            
            if not isinstance(response, dict):
                logger.error(f"Unexpected response type from labels API: {type(response)}")
                return {
                    "startAt": start_at,
                    "maxResults": max_results,
                    "total": 0,
                    "isLast": True,
                    "values": []
                }
            
            return response
            
        except requests.HTTPError as e:
            logger.error(f"Error getting all labels: {str(e.response.content)}")
            return {
                "startAt": start_at,
                "maxResults": max_results,
                "total": 0,
                "isLast": True,
                "values": []
            }
        except Exception as e:
            logger.error(f"Error getting all labels: {str(e)}")
            return {
                "startAt": start_at,
                "maxResults": max_results,
                "total": 0,
                "isLast": True,
                "values": []
            }
