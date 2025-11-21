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
