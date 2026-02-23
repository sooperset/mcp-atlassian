"""Module for Jira Service Management queue read operations."""

import logging

from ..models.jira import (
    JiraQueue,
    JiraQueueIssuesResult,
    JiraServiceDesk,
    JiraServiceDeskQueuesResult,
)
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class QueuesMixin(JiraClient):
    """Mixin for Jira Service Management queue read operations."""

    def _ensure_server_mode(self) -> None:
        """Ensure queue endpoints are used only on Server/Data Center in v1."""
        if self.config.is_cloud:
            raise NotImplementedError(
                "Jira Service Desk queue read endpoints are currently implemented "
                "for Server/Data Center in v1."
            )

    def get_service_desk_for_project(self, project_key: str) -> JiraServiceDesk | None:
        """
        Get the Jira Service Desk associated with a project key.

        Args:
            project_key: The Jira project key (e.g. 'SUP')

        Returns:
            Matched JiraServiceDesk model or None if not found
        """
        if not project_key or not project_key.strip():
            raise ValueError("Project key is required")

        self._ensure_server_mode()

        normalized_project_key = project_key.strip().upper()
        start = 0
        limit = 50

        try:
            while True:
                response = self.jira.get(
                    "rest/servicedeskapi/servicedesk",
                    params={"start": start, "limit": limit},
                )
                if not isinstance(response, dict):
                    logger.error(
                        "Unexpected response type from servicedesk list endpoint: %s",
                        type(response),
                    )
                    return None

                service_desks = response.get("values", [])
                if not isinstance(service_desks, list):
                    logger.error(
                        "Unexpected service desk list payload type: %s",
                        type(service_desks),
                    )
                    return None

                for service_desk_data in service_desks:
                    if not isinstance(service_desk_data, dict):
                        continue
                    current_key = str(
                        service_desk_data.get("projectKey", "")
                    ).upper()
                    if current_key == normalized_project_key:
                        return JiraServiceDesk.from_api_response(service_desk_data)

                if response.get("isLastPage", True) or not service_desks:
                    break
                start += len(service_desks)

            return None
        except Exception as e:
            logger.error(
                "Error getting service desk for project %s: %s", project_key, str(e)
            )
            return None

    def get_service_desk_queues(
        self,
        service_desk_id: str,
        start_at: int = 0,
        limit: int = 50,
        include_count: bool = True,
    ) -> JiraServiceDeskQueuesResult:
        """
        Get queues for a specific service desk.

        Args:
            service_desk_id: The service desk ID (e.g. '4')
            start_at: Starting index for pagination
            limit: Maximum number of queues to return
            include_count: Whether to request queue issue counts from API

        Returns:
            JiraServiceDeskQueuesResult with queues and pagination metadata
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._ensure_server_mode()

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue",
                params={
                    "start": start_at,
                    "limit": limit,
                    "includeCount": str(include_count).lower(),
                },
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from queue list endpoint: %s",
                    type(response),
                )
                return JiraServiceDeskQueuesResult(service_desk_id=service_desk_id)

            return JiraServiceDeskQueuesResult.from_api_response(
                response, service_desk_id=service_desk_id
            )
        except Exception as e:
            logger.error(
                "Error getting queues for service desk %s: %s", service_desk_id, str(e)
            )
            return JiraServiceDeskQueuesResult(service_desk_id=service_desk_id)

    def get_queue_issues(
        self,
        service_desk_id: str,
        queue_id: str,
        start_at: int = 0,
        limit: int = 50,
    ) -> JiraQueueIssuesResult:
        """
        Get issues from a specific service desk queue.

        Args:
            service_desk_id: The service desk ID (e.g. '4')
            queue_id: The queue ID (e.g. '47')
            start_at: Starting index for pagination
            limit: Maximum number of issues to return

        Returns:
            JiraQueueIssuesResult containing queue metadata and queue issues
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not queue_id or not queue_id.strip():
            raise ValueError("Queue ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._ensure_server_mode()

        queue_model: JiraQueue | None = None

        try:
            queue_response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue/{queue_id}",
                params={"includeCount": "true"},
            )
            if isinstance(queue_response, dict):
                queue_model = JiraQueue.from_api_response(queue_response)
        except Exception as e:
            logger.debug(
                "Unable to fetch queue metadata for service desk %s queue %s: %s",
                service_desk_id,
                queue_id,
                str(e),
            )

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue/{queue_id}/issue",
                params={"start": start_at, "limit": limit},
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from queue issues endpoint: %s",
                    type(response),
                )
                return JiraQueueIssuesResult(
                    service_desk_id=service_desk_id,
                    queue_id=queue_id,
                    queue=queue_model,
                )

            return JiraQueueIssuesResult.from_api_response(
                response,
                service_desk_id=service_desk_id,
                queue_id=queue_id,
                queue=queue_model,
            )
        except Exception as e:
            logger.error(
                "Error getting queue issues for service desk %s queue %s: %s",
                service_desk_id,
                queue_id,
                str(e),
            )
            return JiraQueueIssuesResult(
                service_desk_id=service_desk_id,
                queue_id=queue_id,
                queue=queue_model,
            )
