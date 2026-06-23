"""Utility functions for GitHub Activity Analyzer."""

import re
import subprocess
import sys
from datetime import datetime, timedelta

_PR_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")


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


def parse_pr_ref(pr_ref: str, repo_override: str | None = None) -> tuple[str, str, int]:
    """Resolve a PR reference into ``(owner, repo, number)``.

    Accepts either:
      - A full PR URL: ``https://github.com/<owner>/<repo>/pull/<n>``
      - A bare PR number: ``"123"``

    For bare numbers, ``repo_override`` (format ``"owner/repo"``) is consulted
    first; otherwise falls back to :func:`get_git_repo_info`. If a URL is given
    and ``repo_override`` is also given, ``repo_override`` is ignored with a
    stderr warning.

    Raises:
        ValueError: if the ref cannot be resolved.
    """
    ref = pr_ref.strip()

    url_match = _PR_URL_RE.match(ref)
    if url_match:
        if repo_override is not None:
            print(
                "Warning: --repo is ignored when PR_REF is a full URL.",
                file=sys.stderr,
            )
        owner, repo, number_str = url_match.groups()
        return owner, repo, int(number_str)

    if ref.isdigit():
        number = int(ref)
        if repo_override is not None:
            parts = repo_override.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(
                    f"Invalid --repo value: {repo_override!r}. Expected OWNER/REPO."
                )
            return parts[0], parts[1], number

        repo_info = get_git_repo_info()
        if repo_info is None:
            raise ValueError(
                "Could not determine repository; pass --repo OWNER/REPO or "
                "run inside a git clone."
            )
        return repo_info[0], repo_info[1], number

    raise ValueError(
        f"Unrecognised PR reference: {pr_ref}. "
        "Expected a PR number or a github.com /pull/<n> URL."
    )
