"""Formatting functions for GitHub Activity Analyzer."""

from datetime import datetime
from typing import Any

from .utils import format_date


def print_activity_summary(
    commits: list[dict],
    prs: list[dict],
    events_summary: dict,
    linear_issues: list[dict],
    from_date: datetime,
    to_date: datetime,
) -> dict[str, Any]:
    """Print a formatted summary of GitHub activity and return the data."""
    print("\n🔍 GitHub Activity Summary")
    print(
        f"📅 Period: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}"
    )
    print("=" * 60)

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
        print(f"\n📝 Commits ({len(unique_commits)} total)")
        print("-" * 30)
        for repo, repo_commits in sorted(commits_by_repo.items()):
            print(f"\n📦 {repo} ({len(repo_commits)} commits)")
            for commit in sorted(
                repo_commits, key=lambda x: x.get("date", ""), reverse=True
            ):
                date = format_date(commit.get("date", ""))
                message = commit.get("message", "").split("\n")[0][:60]
                print(f"  • {date} - {message}")

    if all_prs:
        print(f"\n🔀 Pull Requests ({len(all_prs)} total)")
        print("-" * 30)
        for pr in sorted(
            all_prs, key=lambda x: x.get("created_at") or "", reverse=True
        ):
            state = pr.get("state") or "unknown"
            state_emoji = (
                "✅"
                if state == "closed" or state == "merged"
                else "🟡"
                if state == "open"
                else "❌"
            )
            date = format_date(pr.get("created_at", ""))
            repo = pr.get("repo", "unknown")
            number = pr.get("number", "?")
            title = pr.get("title") or "No title"
            print(f"  {state_emoji} {repo}#{number} - {title}")
            print(f"     Created: {date}")

    if linear_issues:
        print(f"\n📋 Linear Issues ({len(linear_issues)} total)")
        print("-" * 30)
        for issue in sorted(
            linear_issues,
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
            reverse=True,
        ):
            status = issue.get("status", "Unknown")
            issue_id = issue.get("id", "?")
            title = issue.get("title", "No title")
            updated = issue.get("updated_at")
            if updated:
                date = format_date(updated)
            else:
                date = "Unknown date"
            print(f"  • {issue_id} - {title}")
            print(f"    Status: {status} | Updated: {date}")

    if not unique_commits and not all_prs and not linear_issues:
        print("\n❌ No activity found in the specified date range.")
        print("Note: GitHub events API only shows the last 90 days of activity.")

    print(
        f"\n📊 Summary: {len(unique_commits)} commits, {len(all_prs)} PRs, {len(linear_issues)} Linear issues"
    )

    return {
        "commits": unique_commits,
        "prs": all_prs,
        "linear_issues": linear_issues,
        "commits_by_repo": commits_by_repo,
    }


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

    return "\n".join(lines)
