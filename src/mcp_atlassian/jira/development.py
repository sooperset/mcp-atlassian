"""Development information module for Jira (Bitbucket/GitHub/GitLab integrations)."""

import logging
from typing import Any, Dict, List, Optional

from ..models.jira.development import (
    DevelopmentInformation,
    PullRequest,
    Branch,
    Commit,
    Repository,
)

logger = logging.getLogger("mcp-atlassian.jira.development")


class DevelopmentMixin:
    """Mixin for development-related operations in Jira."""

    def get_development_information(
        self, issue_key: str, application_type: Optional[str] = None
    ) -> DevelopmentInformation:
        """Get development information for a Jira issue.
        
        This retrieves information from development tools integrated with Jira,
        such as Bitbucket, GitHub, or GitLab. It includes pull requests, branches,
        commits, and build information linked to the issue.
        
        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            application_type: Optional filter by application type 
                            ('stash', 'bitbucket', 'github', 'gitlab')
        
        Returns:
            DevelopmentInformation object containing all linked development data
            
        Raises:
            ValueError: If the issue key is invalid or not found
        """
        logger.debug(f"Fetching development information for issue {issue_key}")
        
        if self.config.is_cloud:
            # Cloud API endpoint (Jira Cloud uses a different endpoint)
            # Note: This requires the issue ID, not key
            issue = self.jira.issue(issue_key, fields="id")
            issue_id = issue["id"]
            
            # Try the development information endpoint
            try:
                # Cloud endpoint: /rest/api/3/issue/{issueIdOrKey}/development
                response = self.jira.get(
                    f"/rest/api/3/issue/{issue_id}/development",
                    params={"applicationType": application_type} if application_type else None
                )
            except Exception as e:
                logger.warning(f"Cloud development API failed, trying legacy endpoint: {e}")
                # Fallback to legacy endpoint
                response = self._get_dev_status_legacy(issue_key, application_type)
        else:
            # Server/DC API endpoint
            response = self._get_dev_status_legacy(issue_key, application_type)
        
        return self._parse_development_response(response)
    
    def _get_dev_status_legacy(
        self, issue_key: str, application_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get development status using the legacy/Server endpoint.
        
        This works for both Server/DC and as a fallback for Cloud.
        
        Args:
            issue_key: The Jira issue key
            application_type: Optional application type filter
            
        Returns:
            Raw development status response
        """
        # Server/DC endpoint: /rest/dev-status/latest/issue/detail
        params = {
            "issueId": issue_key,
            "applicationType": application_type or "",
            "dataType": "pullrequest,branch,commit,repository"
        }
        
        try:
            # Try the dev-status endpoint
            response = self.jira.get(
                "/rest/dev-status/latest/issue/detail",
                params=params
            )
            logger.debug(f"Successfully fetched dev status for {issue_key}")
            return response
        except Exception as e:
            logger.error(f"Failed to fetch dev status: {e}")
            # Return empty structure if the endpoint doesn't exist
            return {
                "errors": [str(e)],
                "detail": []
            }
    
    def _parse_development_response(self, response: Dict[str, Any]) -> DevelopmentInformation:
        """Parse the development information response into structured objects.
        
        Args:
            response: Raw API response
            
        Returns:
            Structured DevelopmentInformation object
        """
        dev_info = DevelopmentInformation()
        
        # Handle Cloud API response format
        if "_links" in response:
            # This is a Cloud API response
            dev_info = self._parse_cloud_development_response(response)
        else:
            # This is a Server/DC API response
            dev_info = self._parse_server_development_response(response)
        
        return dev_info
    
    def _parse_cloud_development_response(self, response: Dict[str, Any]) -> DevelopmentInformation:
        """Parse Cloud API development response.
        
        Args:
            response: Cloud API response
            
        Returns:
            DevelopmentInformation object
        """
        dev_info = DevelopmentInformation()
        
        # Cloud response has a different structure
        # It typically has sections for different dev tools
        if "sections" in response:
            for section in response["sections"]:
                if section.get("type") == "pullrequest":
                    dev_info.pull_requests = self._parse_cloud_pull_requests(section)
                elif section.get("type") == "branch":
                    dev_info.branches = self._parse_cloud_branches(section)
                elif section.get("type") == "commit":
                    dev_info.commits = self._parse_cloud_commits(section)
        
        return dev_info
    
    def _parse_server_development_response(self, response: Dict[str, Any]) -> DevelopmentInformation:
        """Parse Server/DC API development response.
        
        Args:
            response: Server/DC API response
            
        Returns:
            DevelopmentInformation object
        """
        dev_info = DevelopmentInformation()
        
        # Server/DC response format
        detail = response.get("detail", [])
        
        for item in detail:
            instances = item.get("instances", [])
            for instance in instances:
                instance_type = instance.get("type", "")
                
                if instance_type == "Bitbucket Server":
                    # Parse Bitbucket Server data
                    dev_info = self._parse_bitbucket_server_instance(instance, dev_info)
                elif instance_type == "GitHub":
                    # Parse GitHub data
                    dev_info = self._parse_github_instance(instance, dev_info)
                # Add more providers as needed
        
        return dev_info
    
    def _parse_bitbucket_server_instance(
        self, instance: Dict[str, Any], dev_info: DevelopmentInformation
    ) -> DevelopmentInformation:
        """Parse Bitbucket Server instance data.
        
        Args:
            instance: Bitbucket Server instance data
            dev_info: DevelopmentInformation to populate
            
        Returns:
            Updated DevelopmentInformation
        """
        # Parse pull requests
        prs = instance.get("pullRequests", [])
        for pr_data in prs:
            pr = PullRequest(
                id=pr_data.get("id", ""),
                title=pr_data.get("name", ""),
                url=pr_data.get("url", ""),
                status=pr_data.get("status", ""),
                author=pr_data.get("author", {}).get("name", ""),
                source_branch=pr_data.get("source", {}).get("branch", ""),
                destination_branch=pr_data.get("destination", {}).get("branch", ""),
                last_update=pr_data.get("lastUpdate", ""),
                commentCount=pr_data.get("commentCount", 0),
            )
            dev_info.pull_requests.append(pr)
        
        # Parse branches
        branches = instance.get("branches", [])
        for branch_data in branches:
            branch = Branch(
                id=branch_data.get("id", ""),
                name=branch_data.get("name", ""),
                url=branch_data.get("url", ""),
                last_commit=branch_data.get("lastCommit", {}).get("id", ""),
                repository=branch_data.get("repository", {}).get("name", ""),
            )
            dev_info.branches.append(branch)
        
        # Parse commits
        commits = instance.get("commits", [])
        for commit_data in commits:
            commit = Commit(
                id=commit_data.get("id", ""),
                message=commit_data.get("message", ""),
                url=commit_data.get("url", ""),
                author=commit_data.get("author", {}).get("name", ""),
                author_timestamp=commit_data.get("authorTimestamp", ""),
                files_changed=commit_data.get("filesChanged", 0),
            )
            dev_info.commits.append(commit)
        
        # Parse repository info
        repos = instance.get("repositories", [])
        for repo_data in repos:
            repo = Repository(
                id=repo_data.get("id", ""),
                name=repo_data.get("name", ""),
                url=repo_data.get("url", ""),
                avatar_url=repo_data.get("avatarUrl", ""),
            )
            dev_info.repositories.append(repo)
        
        return dev_info
    
    def _parse_github_instance(
        self, instance: Dict[str, Any], dev_info: DevelopmentInformation
    ) -> DevelopmentInformation:
        """Parse GitHub instance data.
        
        Args:
            instance: GitHub instance data
            dev_info: DevelopmentInformation to populate
            
        Returns:
            Updated DevelopmentInformation
        """
        # Similar structure to Bitbucket but may have different field names
        # Implement based on actual GitHub response structure
        return dev_info
    
    def _parse_cloud_pull_requests(self, section: Dict[str, Any]) -> List[PullRequest]:
        """Parse Cloud API pull request section.
        
        Args:
            section: Pull request section from Cloud API
            
        Returns:
            List of PullRequest objects
        """
        prs = []
        for item in section.get("items", []):
            pr = PullRequest(
                id=item.get("id", ""),
                title=item.get("title", ""),
                url=item.get("url", ""),
                status=item.get("status", ""),
                author=item.get("author", {}).get("name", ""),
                source_branch=item.get("sourceBranch", ""),
                destination_branch=item.get("destinationBranch", ""),
                last_update=item.get("lastUpdate", ""),
            )
            prs.append(pr)
        return prs
    
    def _parse_cloud_branches(self, section: Dict[str, Any]) -> List[Branch]:
        """Parse Cloud API branch section.
        
        Args:
            section: Branch section from Cloud API
            
        Returns:
            List of Branch objects
        """
        branches = []
        for item in section.get("items", []):
            branch = Branch(
                id=item.get("id", ""),
                name=item.get("name", ""),
                url=item.get("url", ""),
                last_commit=item.get("lastCommit", ""),
                repository=item.get("repository", {}).get("name", ""),
            )
            branches.append(branch)
        return branches
    
    def _parse_cloud_commits(self, section: Dict[str, Any]) -> List[Commit]:
        """Parse Cloud API commit section.
        
        Args:
            section: Commit section from Cloud API
            
        Returns:
            List of Commit objects
        """
        commits = []
        for item in section.get("items", []):
            commit = Commit(
                id=item.get("id", ""),
                message=item.get("message", ""),
                url=item.get("url", ""),
                author=item.get("author", {}).get("name", ""),
                author_timestamp=item.get("authorTimestamp", ""),
                files_changed=item.get("filesChanged", 0),
            )
            commits.append(commit)
        return commits
    
    def get_linked_pull_requests(self, issue_key: str) -> List[PullRequest]:
        """Get only the pull requests linked to a Jira issue.
        
        Convenience method to get just PRs without other development info.
        
        Args:
            issue_key: The Jira issue key
            
        Returns:
            List of PullRequest objects
        """
        dev_info = self.get_development_information(issue_key)
        return dev_info.pull_requests
    
    def get_linked_branches(self, issue_key: str) -> List[Branch]:
        """Get only the branches linked to a Jira issue.
        
        Convenience method to get just branches without other development info.
        
        Args:
            issue_key: The Jira issue key
            
        Returns:
            List of Branch objects
        """
        dev_info = self.get_development_information(issue_key)
        return dev_info.branches
    
    def get_linked_commits(self, issue_key: str) -> List[Commit]:
        """Get only the commits linked to a Jira issue.
        
        Convenience method to get just commits without other development info.
        
        Args:
            issue_key: The Jira issue key
            
        Returns:
            List of Commit objects
        """
        dev_info = self.get_development_information(issue_key)
        return dev_info.commits
