"""GitHub Activity Analyzer - Analyze your GitHub activity between specified dates."""

# Export main functions for backward compatibility and testing
# Export main for script entry point
from .__main__ import main
from .github_api import (
    analyze_events,
    get_commits_for_repo,
    get_pr_review_rounds,
    get_pull_requests,
    get_recent_repos,
    get_user_events,
    get_user_login,
)
from .linear_api import get_linear_issues
from .utils import format_date, get_monday_two_weeks_ago, run_gh_command

__all__ = [
    "analyze_events",
    "format_date",
    "get_commits_for_repo",
    "get_linear_issues",
    "get_monday_two_weeks_ago",
    "get_pr_review_rounds",
    "get_pull_requests",
    "get_recent_repos",
    "get_user_events",
    "get_user_login",
    "main",
    "run_gh_command",
]
