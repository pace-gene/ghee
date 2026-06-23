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


def get_recent_repos(username: str, viewer_login: str) -> list[str]:
    """Get list of a user's recent repositories.

    Uses ``user/repos`` when ``username`` is the authenticated user (includes
    private repos they can access). Otherwise uses ``users/{username}/repos``
    (public repositories for that account).
    """
    repos = []

    try:
        if username.casefold() == viewer_login.casefold():
            path = "user/repos"
        else:
            path = f"users/{username}/repos"

        output = run_gh_command(
            [
                "api",
                path,
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
    """Get pull requests created by the user using search API."""
    prs = []

    try:
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")

        # Use search prs command which works better than search/issues
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
                "100",
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
                            "url": None,  # Can be added if needed
                        }
                    )
            except json.JSONDecodeError:
                # Fallback to old method if search prs doesn't work
                search_query = (
                    f"author:{username} created:{from_date_str}..{to_date_str} is:pr"
                )
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


def get_pr_review_rounds(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Get submitted PR reviews ("rounds") with their inline comments.

    Returns:
        A list of round dicts, sorted ascending by ``submitted_at``. Pending
        (unsubmitted) reviews are excluded. Each round contains the review
        metadata (id, state, author, body, submission time, URL) plus the
        inline review comments left as part of that review.
    """
    graphql_query = f"""
    {{
      repository(owner: "{owner}", name: "{repo}") {{
        pullRequest(number: {pr_number}) {{
          number
          title
          url
          reviews(first: 100) {{
            totalCount
            nodes {{
              id
              databaseId
              state
              submittedAt
              body
              url
              author {{
                login
              }}
              comments(first: 100) {{
                totalCount
                nodes {{
                  id
                  databaseId
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
                  replyTo {{
                    id
                  }}
                  commit {{
                    oid
                  }}
                  originalCommit {{
                    oid
                  }}
                }}
              }}
            }}
          }}
          reviewThreads(first: 100) {{
            totalCount
            nodes {{
              id
              isResolved
              comments(first: 100) {{
                nodes {{
                  databaseId
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

    output = run_gh_command(
        ["api", "graphql", "-f", f"query={graphql_query}"],
        quiet=True,
    )
    if not output:
        print(
            "Warning: Could not fetch review rounds (gh returned no output).",
            file=sys.stderr,
        )
        return []

    try:
        data = json.loads(output)
        pull_request = data["data"]["repository"]["pullRequest"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(
            "Warning: Could not parse review rounds response from gh.",
            file=sys.stderr,
        )
        return []

    if pull_request is None:
        print(
            f"Warning: PR #{pr_number} not found in {owner}/{repo}.",
            file=sys.stderr,
        )
        return []

    pr_title = pull_request.get("title", "No title")
    pr_url = pull_request.get("url", "")

    reviews_block = pull_request.get("reviews") or {}
    reviews_total = reviews_block.get("totalCount", 0)
    if reviews_total > 100:
        print(
            f"Warning: PR has {reviews_total} reviews; only the first 100 "
            "were fetched.",
            file=sys.stderr,
        )

    threads_block = pull_request.get("reviewThreads") or {}
    threads_total = threads_block.get("totalCount", 0)
    if threads_total > 100:
        print(
            f"Warning: PR has {threads_total} review threads; only the "
            "first 100 were fetched.",
            file=sys.stderr,
        )

    thread_lookup: dict[int, tuple[str, bool]] = {}
    for thread in threads_block.get("nodes", []) or []:
        t_id = thread.get("id") or ""
        t_resolved = bool(thread.get("isResolved"))
        for tc in (thread.get("comments") or {}).get("nodes", []) or []:
            db_id = tc.get("databaseId")
            if db_id is not None:
                thread_lookup[db_id] = (t_id, t_resolved)

    unmapped_warned = False

    rounds: list[dict[str, Any]] = []
    for node in reviews_block.get("nodes", []) or []:
        state = node.get("state")
        submitted_at = node.get("submittedAt")
        if state == "PENDING" or submitted_at is None:
            continue

        author = node.get("author") or {}
        review_user = author.get("login", "unknown")

        comments_block = node.get("comments") or {}
        comments_total = comments_block.get("totalCount", 0)
        if comments_total > 100:
            print(
                f"Warning: Review {node.get('id', '?')} has {comments_total} "
                "comments; only the first 100 were fetched.",
                file=sys.stderr,
            )

        comments: list[dict[str, Any]] = []
        for c in comments_block.get("nodes", []) or []:
            c_author = c.get("author") or {}
            c_id_raw = c.get("id") or ""
            c_id_short = c_id_raw.split("_")[-1] if c_id_raw else ""

            reply_to = c.get("replyTo") or {}
            reply_to_raw = reply_to.get("id") or ""
            in_reply_to_id = reply_to_raw.split("_")[-1] if reply_to_raw else None

            commit = c.get("commit") or {}
            original_commit = c.get("originalCommit") or {}

            db_id = c.get("databaseId")
            thread_id: str | None
            if db_id is not None and db_id in thread_lookup:
                thread_id, is_resolved = thread_lookup[db_id]
            else:
                thread_id = None
                is_resolved = False
                if not unmapped_warned:
                    print(
                        f"Warning: comment databaseId={db_id} not found in "
                        "reviewThreads; thread state will be missing.",
                        file=sys.stderr,
                    )
                    unmapped_warned = True

            comments.append(
                {
                    "id": c_id_short,
                    "body": c.get("body", ""),
                    "path": c.get("path", ""),
                    "line": c.get("line"),
                    "start_line": c.get("startLine"),
                    "original_line": c.get("originalLine"),
                    "original_start_line": c.get("originalStartLine"),
                    "user": c_author.get("login", "unknown"),
                    "created_at": c.get("createdAt", ""),
                    "url": c.get("url", ""),
                    "diff_hunk": c.get("diffHunk", ""),
                    "pr_number": pr_number,
                    "pr_title": pr_title,
                    "pr_url": pr_url,
                    "thread_id": thread_id,
                    "is_resolved": is_resolved,
                    "in_reply_to_id": in_reply_to_id,
                    "commit_id": commit.get("oid"),
                    "original_commit_id": original_commit.get("oid"),
                }
            )

        rounds.append(
            {
                "review_id": node.get("id", ""),
                "database_id": node.get("databaseId"),
                "state": state,
                "submitted_at": submitted_at,
                "user": review_user,
                "body": node.get("body", ""),
                "url": node.get("url", ""),
                "pr_number": pr_number,
                "pr_title": pr_title,
                "pr_url": pr_url,
                "comments": comments,
            }
        )

    rounds.sort(key=lambda r: r["submitted_at"] or "")
    return rounds
