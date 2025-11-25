"""Utility functions for GitHub Activity Analyzer."""

import subprocess
import sys
from datetime import datetime, timedelta


def get_monday_two_weeks_ago() -> datetime:
    """Get the Monday from 2 weeks ago as default start date."""
    today = datetime.now()
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday)
    two_weeks_ago_monday = last_monday - timedelta(weeks=2)
    return two_weeks_ago_monday.replace(hour=0, minute=0, second=0, microsecond=0)


def run_gh_command(cmd: list[str], quiet: bool = False) -> str:
    """Run a gh CLI command and return the output.

    Args:
        cmd: Command arguments to pass to gh
        quiet: If True, suppress error output (for expected failures like 404s)
    """
    try:
        result = subprocess.run(
            ["gh"] + cmd, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not quiet:
            print(f"Error running gh command: {e}", file=sys.stderr)
            print(f"Command: {' '.join(['gh'] + cmd)}", file=sys.stderr)
            print(f"Error output: {e.stderr}", file=sys.stderr)
        return ""


def format_date(date_str: str) -> str:
    """Format ISO date string to readable format."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return date_str


def get_git_repo_info() -> tuple[str, str] | None:
    """Get repository owner and name from current git directory.

    Returns:
        Tuple of (owner, repo_name) or None if not in a git repo or can't determine.
    """
    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Get remote URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )

        remote_url = result.stdout.strip()

        # Parse the URL to get owner/repo
        # Handle both https://github.com/owner/repo.git and git@github.com:owner/repo.git
        if remote_url.startswith("https://github.com/"):
            parts = (
                remote_url.replace("https://github.com/", "")
                .replace(".git", "")
                .split("/")
            )
            if len(parts) >= 2:
                return (parts[0], parts[1])
        elif remote_url.startswith("git@github.com:"):
            parts = (
                remote_url.replace("git@github.com:", "").replace(".git", "").split("/")
            )
            if len(parts) >= 2:
                return (parts[0], parts[1])
        elif "github.com" in remote_url:
            # Try to extract from any github.com URL format
            import re

            match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
            if match:
                return (match.group(1), match.group(2))

        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
