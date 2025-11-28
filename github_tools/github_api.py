"""GitHub API interaction functions."""

import json
import sys
from datetime import datetime
from typing import Any

from .utils import run_gh_command


def get_user_login() -> str:
    """Get the current user's GitHub login."""
    output = run_gh_command(["api", "user", "--jq", ".login"])
    return output


def get_user_events(
    username: str, from_date: datetime, to_date: datetime
) -> list[dict[str, Any]]:
    """Get user events from GitHub API."""
    events = []

    try:
        # Get user events (limited to last 90 days by GitHub API)
        output = run_gh_command(
            [
                "api",
                f"users/{username}/events",
                "--paginate",
                "--jq",
                ".[] | {type: .type, created_at: .created_at, repo: .repo.name, payload: .payload}",
            ]
        )

        if output:
            for line in output.split("\n"):
                if line.strip():
                    try:
                        event = json.loads(line)
                        event_date = datetime.fromisoformat(
                            event["created_at"].replace("Z", "+00:00")
                        )

                        # Convert from_date and to_date to timezone-aware for comparison
                        from_date_tz = from_date.replace(tzinfo=event_date.tzinfo)
                        to_date_tz = to_date.replace(tzinfo=event_date.tzinfo)

                        # Filter events within date range
                        if from_date_tz <= event_date <= to_date_tz:
                            events.append(event)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

    except Exception as e:
        print(f"Warning: Could not fetch events: {e}", file=sys.stderr)

    return events


def get_recent_repos(username: str) -> list[str]:
    """Get list of user's recent repositories."""
    repos = []

    try:
        output = run_gh_command(
            [
                "api",
                "user/repos",
                "--jq",
                ".[].full_name",
            ]
        )

        if output:
            repos = [repo.strip() for repo in output.split("\n") if repo.strip()]

    except Exception as e:
        print(f"Warning: Could not fetch repositories: {e}", file=sys.stderr)

    return repos


def get_commits_for_repo(
    repo: str, username: str, from_date: datetime, to_date: datetime
) -> list[dict[str, Any]]:
    """Get commits for a specific repository."""
    commits = []

    try:
        since = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        until = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        output = run_gh_command(
            [
                "api",
                f"repos/{repo}/commits",
                "-f",
                f"author={username}",
                "-f",
                f"since={since}",
                "-f",
                f"until={until}",
                "--jq",
                ".[] | {sha: .sha, message: .commit.message, date: .commit.author.date, author: .commit.author.name}",
            ],
            quiet=True,  # 404s are expected for private/inaccessible repos
        )

        if output:
            for line in output.split("\n"):
                if line.strip():
                    try:
                        commit = json.loads(line)
                        commit["repo"] = repo
                        commits.append(commit)
                    except json.JSONDecodeError:
                        continue

    except Exception:
        # Silently skip repos we can't access
        pass

    return commits


def get_pull_requests(
    username: str, from_date: datetime, to_date: datetime
) -> list[dict[str, Any]]:
    """Get pull requests created by the user using search API with pagination."""
    prs = []

    try:
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")

        # Use GraphQL API for proper pagination support
        # First, get the user ID
        user_query = f"""
        query {{
            user(login: "{username}") {{
                id
            }}
        }}
        """

        user_output = run_gh_command(
            [
                "api",
                "graphql",
                "-f",
                f"query={user_query}",
            ],
            quiet=True,
        )

        user_id = None
        if user_output:
            try:
                user_data = json.loads(user_output)
                user_id = user_data.get("data", {}).get("user", {}).get("id")
            except json.JSONDecodeError:
                pass

        if user_id:
            # Use GraphQL search with pagination
            cursor = None
            has_next_page = True

            while has_next_page:
                cursor_part = f', after: "{cursor}"' if cursor else ""
                search_query = f"""
                query {{
                    search(
                        type: ISSUE,
                        query: "author:{username} created:{from_date_str}..{to_date_str} is:pr",
                        first: 100{cursor_part}
                    ) {{
                        pageInfo {{
                            hasNextPage
                            endCursor
                        }}
                        nodes {{
                            ... on PullRequest {{
                                number
                                title
                                state
                                createdAt
                                repository {{
                                    nameWithOwner
                                }}
                                url
                            }}
                        }}
                    }}
                }}
                """

                output = run_gh_command(
                    [
                        "api",
                        "graphql",
                        "-f",
                        f"query={search_query}",
                    ],
                    quiet=True,
                )

                if output:
                    try:
                        data = json.loads(output)
                        search_data = data.get("data", {}).get("search", {})
                        page_info = search_data.get("pageInfo", {})
                        nodes = search_data.get("nodes", [])

                        for pr in nodes:
                            repo = pr.get("repository", {})
                            prs.append(
                                {
                                    "number": pr.get("number"),
                                    "title": pr.get("title", "No title"),
                                    "state": pr.get("state"),
                                    "created_at": pr.get("createdAt"),
                                    "repo": repo.get("nameWithOwner", "unknown"),
                                    "url": pr.get("url"),
                                }
                            )

                        has_next_page = page_info.get("hasNextPage", False)
                        cursor = page_info.get("endCursor")
                    except json.JSONDecodeError:
                        has_next_page = False
                else:
                    has_next_page = False

        # Fallback to search prs command if GraphQL fails
        if not prs:
            output = run_gh_command(
                [
                    "search",
                    "prs",
                    "--author",
                    username,
                    "--created",
                    f"{from_date_str}..{to_date_str}",
                    "--json",
                    "number,title,state,createdAt,repository",
                    "--limit",
                    "1000",  # Increase limit, but note: gh search prs has a max of 1000
                ]
            )

            if output:
                try:
                    prs_data = json.loads(output)
                    for pr in prs_data:
                        prs.append(
                            {
                                "number": pr.get("number"),
                                "title": pr.get("title", "No title"),
                                "state": pr.get("state"),
                                "created_at": pr.get("createdAt"),
                                "repo": pr.get("repository", {}).get(
                                    "nameWithOwner", "unknown"
                                ),
                                "url": None,
                            }
                        )
                except json.JSONDecodeError:
                    # Final fallback to old method
                    search_query = f"author:{username} created:{from_date_str}..{to_date_str} is:pr"
                    output = run_gh_command(
                        [
                            "api",
                            "search/issues",
                            "-q",
                            search_query,
                            "--jq",
                            '.items[] | {number: .number, title: .title, state: .state, created_at: .created_at, repo: .repository_url | split("/") | .[-2:] | join("/"), url: .html_url}',
                        ]
                    )
                    if output:
                        for line in output.split("\n"):
                            if line.strip():
                                try:
                                    prs.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue

    except Exception as e:
        print(f"Warning: Could not fetch pull requests: {e}", file=sys.stderr)

    return prs


def analyze_events(events: list[dict], username: str) -> dict[str, list[dict]]:
    """Analyze events and categorize them."""
    categorized: dict[str, list[dict]] = {"commits": [], "pull_requests": []}

    for event in events:
        event_type = event.get("type")
        repo = event.get("repo", "unknown")
        created_at = event.get("created_at")

        if event_type == "PushEvent":
            payload = event.get("payload", {})
            commits = payload.get("commits", [])
            for commit in commits:
                if commit.get("author", {}).get("name") == username:
                    categorized["commits"].append(
                        {
                            "sha": commit.get("sha"),
                            "message": commit.get("message"),
                            "date": created_at,
                            "repo": repo,
                        }
                    )

        elif event_type == "PullRequestEvent":
            payload = event.get("payload", {})
            pr = payload.get("pull_request", {})
            categorized["pull_requests"].append(
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "created_at": created_at,
                    "repo": repo,
                }
            )

    return categorized


def get_unresolved_pr_comments(owner: str, repo: str) -> list[dict[str, Any]]:
    """Get all unresolved review comments from open pull requests.

    Args:
        owner: Repository owner
        repo: Repository name

    Returns:
        List of comment dictionaries with PR and comment information
    """
    comments: list[dict[str, Any]] = []

    try:
        # First, get all open PRs using gh pr list (more reliable than API)
        output = run_gh_command(
            [
                "pr",
                "list",
                "--repo",
                f"{owner}/{repo}",
                "--state",
                "open",
                "--json",
                "number,title,url,createdAt",
            ]
        )

        if not output:
            return comments

        # Parse PRs
        try:
            prs_data = json.loads(output)
            prs = []
            for pr in prs_data:
                prs.append(
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title", "No title"),
                        "url": pr.get("url", ""),
                        "created_at": pr.get("createdAt", ""),
                    }
                )
        except json.JSONDecodeError:
            return comments

        # For each PR, get unresolved review comments
        for pr in prs:
            pr_number = pr.get("number")
            if not pr_number:
                continue

            # Use GraphQL to get review threads with resolved status
            # This is more reliable than REST API for determining unresolved status
            graphql_query = f"""
            {{
              repository(owner: "{owner}", name: "{repo}") {{
                pullRequest(number: {pr_number}) {{
                  reviewThreads(first: 100) {{
                    nodes {{
                      isResolved
                      comments(first: 100) {{
                        nodes {{
                          id
                          body
                          author {{
                            login
                          }}
                          createdAt
                          url
                          path
                          line
                          startLine
                          originalLine
                          originalStartLine
                          diffHunk
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """

            threads_output = run_gh_command(
                [
                    "api",
                    "graphql",
                    "-f",
                    f"query={graphql_query}",
                ],
                quiet=True,
            )

            if threads_output:
                try:
                    graphql_data = json.loads(threads_output)
                    threads = (
                        graphql_data.get("data", {})
                        .get("repository", {})
                        .get("pullRequest", {})
                        .get("reviewThreads", {})
                        .get("nodes", [])
                    )

                    for thread in threads:
                        # Only include unresolved threads
                        if not thread.get("isResolved", True):
                            thread_comments = thread.get("comments", {}).get(
                                "nodes", []
                            )
                            # GitHub counts unresolved threads, not individual comments
                            # Include all comments in the thread for full context
                            for comment in thread_comments:
                                comment_data = {
                                    "id": comment.get("id", "").split("_")[-1]
                                    if comment.get("id")
                                    else "",
                                    "body": comment.get("body", ""),
                                    "path": comment.get("path", ""),
                                    "line": comment.get("line"),
                                    "start_line": comment.get("startLine"),
                                    "original_line": comment.get("originalLine"),
                                    "original_start_line": comment.get(
                                        "originalStartLine"
                                    ),
                                    "user": comment.get("author", {}).get(
                                        "login", "unknown"
                                    ),
                                    "created_at": comment.get("createdAt", ""),
                                    "url": comment.get("url", ""),
                                    "diff_hunk": comment.get("diffHunk", ""),
                                    "pr_number": pr_number,
                                    "pr_title": pr.get("title", "No title"),
                                    "pr_url": pr.get("url", ""),
                                }
                                comments.append(comment_data)
                except (json.JSONDecodeError, KeyError):
                    # Fallback to REST API if GraphQL fails
                    pass

            # Note: We're only including inline code review comments (from review threads)
            # General review comments (from /reviews endpoint) are not included as they
            # are typically not considered "unresolved" in the GitHub UI count

    except Exception as e:
        print(f"Warning: Could not fetch PR comments: {e}", file=sys.stderr)

    return comments
