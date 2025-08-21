"""Development information models for Jira integrations."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PullRequest:
    """Represents a pull request linked to a Jira issue."""
    
    id: str
    title: str
    url: str
    status: str  # e.g., 'OPEN', 'MERGED', 'DECLINED'
    author: str
    source_branch: str = ""
    destination_branch: str = ""
    last_update: str = ""
    commentCount: int = 0
    reviewers: List[str] = field(default_factory=list)
    
    @property
    def is_open(self) -> bool:
        """Check if the PR is still open."""
        return self.status.upper() in ['OPEN', 'PENDING']
    
    @property
    def is_merged(self) -> bool:
        """Check if the PR has been merged."""
        return self.status.upper() in ['MERGED', 'CLOSED']


@dataclass
class Branch:
    """Represents a branch linked to a Jira issue."""
    
    id: str
    name: str
    url: str
    last_commit: str = ""
    repository: str = ""
    create_time: str = ""
    
    @property
    def is_feature_branch(self) -> bool:
        """Check if this is a feature branch."""
        return self.name.startswith(('feature/', 'feat/'))
    
    @property
    def is_bugfix_branch(self) -> bool:
        """Check if this is a bugfix branch."""
        return self.name.startswith(('bugfix/', 'fix/', 'hotfix/'))


@dataclass
class Commit:
    """Represents a commit linked to a Jira issue."""
    
    id: str
    message: str
    url: str
    author: str
    author_timestamp: str
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    
    @property
    def short_id(self) -> str:
        """Get the short commit ID (first 7 characters)."""
        return self.id[:7] if len(self.id) >= 7 else self.id
    
    @property
    def first_line_message(self) -> str:
        """Get the first line of the commit message."""
        return self.message.split('\n')[0] if self.message else ""


@dataclass
class Build:
    """Represents a build/pipeline linked to a Jira issue."""
    
    id: str
    name: str
    url: str
    status: str  # e.g., 'SUCCESS', 'FAILED', 'IN_PROGRESS'
    started_time: str = ""
    finished_time: str = ""
    duration_seconds: int = 0
    
    @property
    def is_successful(self) -> bool:
        """Check if the build was successful."""
        return self.status.upper() in ['SUCCESS', 'SUCCESSFUL', 'PASSED']
    
    @property
    def is_failed(self) -> bool:
        """Check if the build failed."""
        return self.status.upper() in ['FAILED', 'FAILURE', 'ERROR']


@dataclass
class Repository:
    """Represents a repository linked to a Jira issue."""
    
    id: str
    name: str
    url: str
    avatar_url: str = ""
    description: str = ""
    
    @property
    def full_name(self) -> str:
        """Get the full repository name (usually includes namespace)."""
        # Try to extract from URL if not provided
        if '/' in self.name:
            return self.name
        if self.url:
            # Extract from URL patterns like /projects/PROJ/repos/repo-name
            parts = self.url.rstrip('/').split('/')
            if 'repos' in parts:
                idx = parts.index('repos')
                if idx > 1 and idx < len(parts) - 1:
                    project = parts[idx - 1]
                    repo = parts[idx + 1]
                    return f"{project}/{repo}"
        return self.name


@dataclass
class DevelopmentInformation:
    """Container for all development information linked to a Jira issue."""
    
    pull_requests: List[PullRequest] = field(default_factory=list)
    branches: List[Branch] = field(default_factory=list)
    commits: List[Commit] = field(default_factory=list)
    builds: List[Build] = field(default_factory=list)
    repositories: List[Repository] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def has_development_info(self) -> bool:
        """Check if any development information is linked."""
        return bool(
            self.pull_requests or 
            self.branches or 
            self.commits or 
            self.builds or
            self.repositories
        )
    
    @property
    def open_pull_requests(self) -> List[PullRequest]:
        """Get only open pull requests."""
        return [pr for pr in self.pull_requests if pr.is_open]
    
    @property
    def merged_pull_requests(self) -> List[PullRequest]:
        """Get only merged pull requests."""
        return [pr for pr in self.pull_requests if pr.is_merged]
    
    @property
    def total_commits(self) -> int:
        """Get the total number of commits."""
        return len(self.commits)
    
    @property
    def summary(self) -> str:
        """Get a summary of the development information."""
        parts = []
        
        if self.pull_requests:
            open_prs = len(self.open_pull_requests)
            merged_prs = len(self.merged_pull_requests)
            parts.append(f"PRs: {open_prs} open, {merged_prs} merged")
        
        if self.branches:
            parts.append(f"Branches: {len(self.branches)}")
        
        if self.commits:
            parts.append(f"Commits: {len(self.commits)}")
        
        if self.builds:
            successful = sum(1 for b in self.builds if b.is_successful)
            failed = sum(1 for b in self.builds if b.is_failed)
            parts.append(f"Builds: {successful} passed, {failed} failed")
        
        return " | ".join(parts) if parts else "No development information"
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "pull_requests": [
                {
                    "id": pr.id,
                    "title": pr.title,
                    "url": pr.url,
                    "status": pr.status,
                    "author": pr.author,
                    "source_branch": pr.source_branch,
                    "destination_branch": pr.destination_branch,
                }
                for pr in self.pull_requests
            ],
            "branches": [
                {
                    "id": b.id,
                    "name": b.name,
                    "url": b.url,
                    "repository": b.repository,
                }
                for b in self.branches
            ],
            "commits": [
                {
                    "id": c.short_id,
                    "message": c.first_line_message,
                    "author": c.author,
                    "url": c.url,
                }
                for c in self.commits
            ],
            "builds": [
                {
                    "id": b.id,
                    "name": b.name,
                    "status": b.status,
                    "url": b.url,
                }
                for b in self.builds
            ],
            "summary": self.summary,
            "has_development_info": self.has_development_info,
            "errors": self.errors,
        }
