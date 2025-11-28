"""Formatting functions for GitHub Activity Analyzer."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .utils import format_date


@dataclass
class WorkItem:
    """Unified representation of a GitHub PR or Linear issue."""

    identifier: str  # repo#number for PRs, issue_id for Linear
    title: str
    state_emoji: str  # ✅, 🟡, or ❌
    date: str  # Formatted date string
    date_label: str  # "Created" or "Updated"
    sort_key: str  # For sorting (ISO date string)
    parent_title: str | None = None  # Parent issue title (Linear only)
    project: str | None = None  # Project name (Linear only)

    @staticmethod
    def _get_state_emoji_from_github_state(state: str) -> str:
        """Convert GitHub PR state to emoji."""
        state_lower = (state or "unknown").lower()
        if state_lower == "closed" or state_lower == "merged":
            return "✅"
        elif state_lower == "open":
            return "🟡"
        else:
            return "❌"

    @staticmethod
    def _get_state_emoji_from_linear_status(status: str) -> str:
        """Convert Linear issue status to emoji."""
        status_lower = (status or "Unknown").lower()
        if "done" in status_lower or "completed" in status_lower:
            return "✅"
        elif "review" in status_lower or "progress" in status_lower:
            return "🟡"
        elif "cancel" in status_lower:
            return "❌"
        else:
            return "🟡"  # Default to in-progress for unknown states

    @classmethod
    def from_pr(cls, pr: dict[str, Any]) -> "WorkItem":
        """Create a WorkItem from a GitHub PR dict."""
        state = pr.get("state") or "unknown"
        repo = pr.get("repo", "unknown")
        number = pr.get("number", "?")
        title = pr.get("title") or "No title"
        created_at = pr.get("created_at", "")
        date_str = format_date(created_at) if created_at else "Unknown date"

        return cls(
            identifier=f"{repo}#{number}",
            title=title,
            state_emoji=cls._get_state_emoji_from_github_state(state),
            date=date_str,
            date_label="Created",
            sort_key=created_at or "",
        )

    @classmethod
    def from_linear_issue(cls, issue: dict[str, Any]) -> "WorkItem":
        """Create a WorkItem from a Linear issue dict."""
        status = issue.get("status", "Unknown")
        issue_id = issue.get("id", "?")
        title = issue.get("title") or "No title"
        updated_at = issue.get("updated_at")
        created_at = issue.get("created_at")

        # Prefer updated_at, fallback to created_at
        date_iso = updated_at or created_at or ""
        date_str = format_date(date_iso) if date_iso else "Unknown date"
        date_label = "Updated" if updated_at else "Created"

        # Extract parent and project information
        parent_title = issue.get("parent_title")
        project = issue.get("project")

        return cls(
            identifier=issue_id,
            title=title,
            state_emoji=cls._get_state_emoji_from_linear_status(status),
            date=date_str,
            date_label=date_label,
            sort_key=date_iso,
            parent_title=parent_title,
            project=project,
        )

    def format_line(self) -> str:
        """Format this work item as a single line."""
        return f"  {self.state_emoji} {self.identifier} - {self.title}"

    def format_date_line(self) -> str:
        """Format the date line for this work item."""
        return f"     {self.date_label}: {self.date}"


def _format_work_items(
    items: list[WorkItem], section_title: str, section_emoji: str
) -> list[str]:
    """Format a list of work items as markdown lines."""
    if not items:
        return []

    lines = [
        f"\n## {section_emoji} {section_title} ({len(items)} total)",
        "",
    ]
    for item in sorted(items, key=lambda x: x.sort_key, reverse=True):
        # Format as markdown list item
        lines.append(f"- {item.state_emoji} **{item.identifier}** - {item.title}")
        lines.append(f"  - {item.date_label}: {item.date}")
        # Add parent information if available
        if item.parent_title:
            lines.append(f"  - Parent: {item.parent_title}")
        # Add project information if available
        if item.project:
            lines.append(f"  - Project: {item.project}")

    return lines


def format_activity_summary(
    commits: list[dict],
    prs: list[dict],
    events_summary: dict,
    linear_issues: list[dict],
    from_date: datetime,
    to_date: datetime,
) -> str:
    """Format GitHub activity summary as markdown."""
    lines = [
        "# 🔍 GitHub Activity Summary",
        "",
        f"**Period:** {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
    ]

    # Combine commits from API calls and events
    all_commits = commits + events_summary.get("commits", [])
    all_prs = prs + events_summary.get("pull_requests", [])

    # Remove duplicates by sha/number
    seen_commits = set()
    unique_commits = []
    for commit in all_commits:
        sha = commit.get("sha")
        if sha and sha not in seen_commits:
            seen_commits.add(sha)
            unique_commits.append(commit)

    # Remove duplicate PRs by repo and number
    seen_prs = set()
    unique_prs = []
    for pr in all_prs:
        repo = pr.get("repo", "unknown")
        number = pr.get("number")
        if number:
            key = (repo, number)
            if key not in seen_prs:
                seen_prs.add(key)
                unique_prs.append(pr)
    all_prs = unique_prs

    # Group commits by repository
    commits_by_repo: dict[str, list[dict]] = {}
    for commit in unique_commits:
        repo = commit.get("repo", "unknown")
        if repo not in commits_by_repo:
            commits_by_repo[repo] = []
        commits_by_repo[repo].append(commit)

    if commits_by_repo:
        lines.append(f"## 📝 Commits ({len(unique_commits)} total)")
        lines.append("")
        for repo, repo_commits in sorted(commits_by_repo.items()):
            lines.append(f"### 📦 {repo} ({len(repo_commits)} commits)")
            lines.append("")
            for commit in sorted(
                repo_commits, key=lambda x: x.get("date", ""), reverse=True
            ):
                date = format_date(commit.get("date", ""))
                message = commit.get("message", "").split("\n")[0]
                lines.append(f"- {date} - {message}")
            lines.append("")

    # Convert PRs and Linear issues to WorkItems
    pr_items = [WorkItem.from_pr(pr) for pr in all_prs]
    linear_items = [WorkItem.from_linear_issue(issue) for issue in linear_issues]

    lines.extend(_format_work_items(pr_items, "Pull Requests", "🔀"))
    lines.extend(_format_work_items(linear_items, "Linear Issues", "📋"))

    if not unique_commits and not all_prs and not linear_issues:
        lines.append("\n❌ No activity found in the specified date range.")
        lines.append(
            "\n> Note: GitHub events API only shows the last 90 days of activity."
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"**Summary:** {len(unique_commits)} commits, {len(all_prs)} PRs, {len(linear_issues)} Linear issues"
    )

    return "\n".join(lines)


def format_data_for_gemini(
    commits: list[dict],
    prs: list[dict],
    linear_issues: list[dict],
    from_date: datetime,
    to_date: datetime,
) -> str:
    """Format GitHub activity data as text for Gemini prompt."""
    lines = [
        "GitHub Activity Data",
        f"Period: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}",
        "",
    ]

    if commits:
        lines.append(f"COMMITS ({len(commits)} total):")
        lines.append("-" * 50)
        # Group by repo
        commits_by_repo: dict[str, list[dict]] = {}
        for commit in commits:
            repo = commit.get("repo", "unknown")
            if repo not in commits_by_repo:
                commits_by_repo[repo] = []
            commits_by_repo[repo].append(commit)

        for repo, repo_commits in sorted(commits_by_repo.items()):
            lines.append(f"\nRepository: {repo} ({len(repo_commits)} commits)")
            for commit in sorted(
                repo_commits, key=lambda x: x.get("date", ""), reverse=True
            ):
                date = format_date(commit.get("date", ""))
                message = commit.get("message", "").split("\n")[0]
                lines.append(f"  - {date}: {message}")

    if prs:
        # Deduplicate PRs by repo and number
        seen_prs = set()
        unique_prs = []
        for pr in prs:
            repo = pr.get("repo", "unknown")
            number = pr.get("number")
            if number:
                key = (repo, number)
                if key not in seen_prs:
                    seen_prs.add(key)
                    unique_prs.append(pr)

        lines.append(f"\n\nPULL REQUESTS ({len(unique_prs)} total):")
        lines.append("-" * 50)
        for pr in sorted(
            unique_prs, key=lambda x: x.get("created_at", ""), reverse=True
        ):
            state = pr.get("state") or "unknown"
            date = format_date(pr.get("created_at", ""))
            repo = pr.get("repo", "unknown")
            number = pr.get("number", "?")
            title = pr.get("title") or "No title"
            lines.append(f"  - {repo}#{number} [{state.upper()}]: {title}")
            lines.append(f"    Created: {date}")

    if linear_issues:
        lines.append(f"\n\nLINEAR ISSUES ({len(linear_issues)} total):")
        lines.append("-" * 50)
        for issue in sorted(
            linear_issues,
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
            reverse=True,
        ):
            status = issue.get("status", "Unknown")
            issue_id = issue.get("id", "?")
            title = issue.get("title", "No title")
            updated = issue.get("updated_at")
            created = issue.get("created_at")
            if updated:
                date = format_date(updated)
            elif created:
                date = format_date(created)
            else:
                date = "Unknown date"
            lines.append(f"  - {issue_id} [{status}]: {title}")
            lines.append(f"    Updated: {date}")
            parent_title = issue.get("parent_title")
            if parent_title:
                lines.append(f"    Parent: {parent_title}")
            project = issue.get("project")
            if project:
                lines.append(f"    Project: {project}")

    return "\n".join(lines)


def format_pr_comments(comments: list[dict], json_output: bool = False) -> str:
    """Format PR comments for output.

    Args:
        comments: List of comment dictionaries
        json_output: If True, return JSON; otherwise return human-readable format

    Returns:
        Formatted string output
    """
    import json as json_module

    if json_output:
        return json_module.dumps(comments, indent=2)

    if not comments:
        return "No unresolved PR comments found."

    lines = [
        f"📝 Unresolved PR Comments ({len(comments)} total)",
        "=" * 60,
        "",
    ]

    # Group comments by PR
    comments_by_pr: dict[int, list[dict]] = {}
    for comment in comments:
        pr_number = comment.get("pr_number")
        if pr_number:
            if pr_number not in comments_by_pr:
                comments_by_pr[pr_number] = []
            comments_by_pr[pr_number].append(comment)

    # Sort PRs by number
    for pr_number in sorted(comments_by_pr.keys()):
        pr_comments = comments_by_pr[pr_number]
        first_comment = pr_comments[0]
        pr_title = first_comment.get("pr_title", "No title")
        pr_url = first_comment.get("pr_url", "")

        lines.append(f"PR #{pr_number}: {pr_title}")
        if pr_url:
            lines.append(f"  URL: {pr_url}")
        lines.append(f"  Comments: {len(pr_comments)}")
        lines.append("")

        for comment in pr_comments:
            user = comment.get("user", "unknown")
            body = comment.get("body", "").strip()
            created_at = comment.get("created_at") or comment.get("submitted_at", "")

            if created_at:
                date = format_date(created_at)
            else:
                date = "Unknown date"

            # Show file and line information in standard notation: <path>:<line> or <path>:<start>-<end>
            path = comment.get("path", "")
            line = comment.get("line")
            start_line = comment.get("start_line")
            original_line = comment.get("original_line")
            original_start_line = comment.get("original_start_line")

            if path:
                # Check if this is a range (has start_line)
                if start_line and line and start_line != line:
                    # Range in the new file
                    lines.append(f"  {path}:{start_line}-{line}")
                elif (
                    original_start_line
                    and original_line
                    and original_start_line != original_line
                ):
                    # Range in the original file (deleted lines)
                    lines.append(f"  {path}:{original_start_line}-{original_line}")
                elif line:
                    # Single line in new file
                    lines.append(f"  {path}:{line}")
                elif original_line:
                    # Single line in original file (deleted)
                    lines.append(f"  {path}:{original_line}")
                else:
                    # File-level comment
                    lines.append(f"  {path}")
            else:
                # General review comment without specific file/line
                lines.append("  (general review comment)")

            # Output full comment body
            lines.append(f"  👤 {user} ({date})")
            lines.append(f"  💬 {body}")

            # Add URL if available
            comment_url = comment.get("url", "")
            if comment_url:
                lines.append(f"  🔗 {comment_url}")

            lines.append("")

    return "\n".join(lines)
