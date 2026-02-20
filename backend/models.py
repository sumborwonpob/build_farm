"""
Data models for the build farm system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Repository:
    """Represents a Git repository configuration."""
    id: Optional[int]
    name: str
    git_url: str
    branch: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __repr__(self):
        return f"Repository(id={self.id}, name='{self.name}')"


@dataclass
class Build:
    """Represents a build execution result."""
    id: Optional[int]
    repo_id: int
    status: str  # 'pending', 'running', 'success', 'failed', 'error'
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    commit_hash: Optional[str]
    commit_message: Optional[str]
    logs: Optional[str]
    exit_code: Optional[int]
    test_duration: Optional[float] = None  # Duration of test execution in seconds
    test_results: Optional[str] = None  # JSON string of individual test results
    
    def __repr__(self):
        return f"Build(id={self.id}, repo_id={self.repo_id}, status='{self.status}')"
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate build duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
