"""Formatting functions for GitHub Activity Analyzer."""

from datetime import datetime
from typing import Any

from .utils import format_date, sanitize_body

_BOT_SUFFIX = "[bot]"
_KNOWN_BOTS = {"coderabbitai", "dependabot", "renovate"}


def _is_bot(user: str) -> bool:
    """Best-effort bot-account detection for --exclude-bot-comments/--only-human."""
    u = (user or "").lower()
    return u.endswith(_BOT_SUFFIX) or u in _KNOWN_BOTS


def _filter_by_author(
    items: list[dict], *, exclude_bots: bool, only_human: bool
) -> list[dict]:
    """Apply --exclude-bot-comments / --only-human. Noise control, not security."""
    if not exclude_bots and not only_human:
        return items
    return [item for item in items if not _is_bot(item.get("user", ""))]


def _fenced_body(
    body: str, user: str, *, strict: bool = False, expand_details: bool = False
) -> tuple[str, list[str]]:
    """Sanitize and fence an untrusted body for human-readable output."""
    clean, warnings = sanitize_body(body, strict=strict, expand_details=expand_details)
    # Strip any occurrence of our own delimiter first so it cannot be closed early.
    clean = clean.replace("<<<end comment>>>", "").replace("<<<comment", "")
    fenced = (
        f"<<<comment by {user} (untrusted) >>>\n{clean}\n<<<end comment>>>"
        if clean
        else clean
    )
    return fenced, warnings


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
    """Format GitHub activity data as text for Gemini prompt.

    Note: this currently only surfaces titles/commit messages, not comment
    bodies. If comment bodies are ever added here, run them through
    ``sanitize_body`` first — this text goes straight into an LLM prompt
    (see PROMPT-INJECTION-2026-09-14.md).
    """
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


def format_pr_comments(
    comments: list[dict],
    json_output: bool = False,
    *,
    exclude_bots: bool = False,
    only_human: bool = False,
    strict: bool = False,
    expand_details: bool = False,
) -> str:
    """Format PR comments for output.

    Args:
        comments: List of comment dictionaries
        json_output: If True, return JSON; otherwise return human-readable format
        exclude_bots: Drop comments from known bot accounts (noise control only).
        only_human: Alias for exclude_bots.
        strict: Redact directive-shaped regions in bodies instead of just flagging.
        expand_details: Leave <details> blocks intact instead of collapsing them.

    Returns:
        Formatted string output
    """
    import json as json_module

    comments = _filter_by_author(
        comments, exclude_bots=exclude_bots, only_human=only_human
    )

    if json_output:
        enriched = []
        for comment in comments:
            sanitized, warnings = sanitize_body(
                comment.get("body", ""), strict=strict, expand_details=expand_details
            )
            enriched.append(
                {**comment, "body_sanitized": sanitized, "warnings": warnings}
            )
        return json_module.dumps(enriched, indent=2)

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
            body, warnings = _fenced_body(
                comment.get("body", ""),
                user,
                strict=strict,
                expand_details=expand_details,
            )
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
            if warnings:
                lines.append(
                    f"  ⚠️  body contains agent-directed text (matched: {', '.join(warnings)})"
                )
            lines.append(f"  💬 {body}")

            # Add URL if available
            comment_url = comment.get("url", "")
            if comment_url:
                lines.append(f"  🔗 {comment_url}")

            lines.append("")

    return "\n".join(lines)


_REVIEW_STATE_ICONS = {
    "APPROVED": "✅",
    "CHANGES_REQUESTED": "❌",
    "COMMENTED": "💬",
    "DISMISSED": "🗑️",
}


def _enrich_round_json(rd: dict, *, strict: bool, expand_details: bool) -> dict:
    body_sanitized, warnings = sanitize_body(
        rd.get("body") or "", strict=strict, expand_details=expand_details
    )
    out: dict[str, Any] = {**rd, "body_sanitized": body_sanitized, "warnings": warnings}
    comments = rd.get("comments") or []
    if comments:
        enriched_comments: list[dict[str, Any]] = []
        for c in comments:
            c_sanitized, c_warnings = sanitize_body(
                c.get("body") or "", strict=strict, expand_details=expand_details
            )
            enriched_comments.append(
                {**c, "body_sanitized": c_sanitized, "warnings": c_warnings}
            )
        out["comments"] = enriched_comments
    return out


def format_pr_review_rounds(
    rounds: list[dict],
    json_output: bool = False,
    *,
    exclude_bots: bool = False,
    only_human: bool = False,
    strict: bool = False,
    expand_details: bool = False,
) -> str:
    """Format PR review rounds for output.

    Args:
        rounds: List of round dicts as produced by ``get_pr_review_rounds``.
        json_output: If True, return JSON; otherwise human-readable format.
        exclude_bots: Drop reviews/comments from known bot accounts (noise control only).
        only_human: Alias for exclude_bots.
        strict: Redact directive-shaped regions in bodies instead of just flagging.
        expand_details: Leave <details> blocks intact instead of collapsing them.

    Returns:
        Formatted string output.
    """
    import json as json_module

    rounds = _filter_by_author(rounds, exclude_bots=exclude_bots, only_human=only_human)
    for rd in rounds:
        if rd.get("comments"):
            rd["comments"] = _filter_by_author(
                rd["comments"], exclude_bots=exclude_bots, only_human=only_human
            )

    if json_output:
        enriched = [
            _enrich_round_json(rd, strict=strict, expand_details=expand_details)
            for rd in rounds
        ]
        return json_module.dumps(enriched, indent=2)

    if not rounds:
        return "No review rounds found."

    first = rounds[0]
    pr_number = first.get("pr_number", "?")
    pr_title = first.get("pr_title", "unknown")
    pr_url = first.get("pr_url", "")
    total_comments = sum(len(r.get("comments", [])) for r in rounds)

    lines = [
        f"📝 Review Rounds for PR #{pr_number}: {pr_title} "
        f"({len(rounds)} rounds, {total_comments} comments)",
        "=" * 60,
        f"URL: {pr_url}",
        "",
    ]

    for idx, rd in enumerate(rounds, start=1):
        state = rd.get("state", "")
        icon = _REVIEW_STATE_ICONS.get(state, "📝")
        user = rd.get("user", "unknown")
        submitted_at = rd.get("submitted_at") or ""
        date = format_date(submitted_at) if submitted_at else "Unknown date"
        review_url = rd.get("url", "")
        body, warnings = _fenced_body(
            rd.get("body") or "", user, strict=strict, expand_details=expand_details
        )

        lines.append(f"{icon} Round {idx} — {state} — {user} ({date})")
        if review_url:
            lines.append(f"  🔗 {review_url}")
        if body:
            if warnings:
                lines.append(
                    f"  ⚠️  body contains agent-directed text (matched: {', '.join(warnings)})"
                )
            lines.append(f"  💬 {body}")

        comments = rd.get("comments", []) or []
        if comments:
            lines.append("  " + "-" * 30)
            for c_idx, comment in enumerate(comments):
                c_user = comment.get("user", "unknown")
                c_body, c_warnings = _fenced_body(
                    comment.get("body") or "",
                    c_user,
                    strict=strict,
                    expand_details=expand_details,
                )
                c_created = comment.get("created_at") or ""
                c_date = format_date(c_created) if c_created else "Unknown date"

                path = comment.get("path", "")
                line = comment.get("line")
                start_line = comment.get("start_line")
                original_line = comment.get("original_line")
                original_start_line = comment.get("original_start_line")
                prefix = "✅ " if comment.get("is_resolved") else ""

                if path:
                    if start_line and line and start_line != line:
                        lines.append(f"  {prefix}{path}:{start_line}-{line}")
                    elif (
                        original_start_line
                        and original_line
                        and original_start_line != original_line
                    ):
                        lines.append(
                            f"  {prefix}{path}:{original_start_line}-{original_line}"
                        )
                    elif line:
                        lines.append(f"  {prefix}{path}:{line}")
                    elif original_line:
                        lines.append(f"  {prefix}{path}:{original_line}")
                    else:
                        lines.append(f"  {prefix}{path}")
                else:
                    lines.append(f"  {prefix}(general review comment)")

                lines.append(f"    👤 {c_user} ({c_date})")
                if c_warnings:
                    lines.append(
                        f"    ⚠️  body contains agent-directed text (matched: {', '.join(c_warnings)})"
                    )
                lines.append(f"    💬 {c_body}")
                comment_url = comment.get("url", "")
                if comment_url:
                    lines.append(f"    🔗 {comment_url}")
                if c_idx < len(comments) - 1:
                    lines.append("")

        lines.append("")

    return "\n".join(lines)
