"""Linear API interaction functions."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_api_key


def _strip_quotes_and_whitespace(value: str) -> str:
    """Strip quotes (single or double) and whitespace from a string."""
    if not value:
        return value
    value = value.strip()
    # Strip matching quotes from both ends
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1].strip()
    return value


def get_linear_api_key() -> str | None:
    """Get Linear API key from environment variables, config file, or lnr config file.

    Environment variables take precedence over config file.
    """
    # Check environment variables first (highest precedence)
    env_key = os.getenv("LINEAR_KEY")
    if env_key:
        env_key = _strip_quotes_and_whitespace(env_key)
        if env_key:
            return env_key

    # Fallback to config file
    api_key = get_api_key("linear")
    if api_key:
        api_key = _strip_quotes_and_whitespace(api_key)
        if api_key:
            return api_key

    # Fallback to lnr config file
    try:
        config_path = Path.home() / ".config" / "lnr.cfg"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                # Try to get API key from organizations
                orgs = config.get("organizations", {})
                if orgs:
                    # Get the first organization's API key
                    first_org = list(orgs.values())[0]
                    if isinstance(first_org, dict):
                        return first_org.get("api_key") or first_org.get("token")
    except Exception:
        pass
    return None


def get_linear_issues(
    from_date: datetime, to_date: datetime, user_identifier: str | None = None
) -> list[dict[str, Any]]:
    """Get Linear issues worked on in the date range using GraphQL API.

    Args:
        from_date: Start date for the query
        to_date: End date for the query
        user_identifier: Optional user email or ID. If not provided, uses authenticated user.
    """
    issues = []

    try:
        api_key = get_linear_api_key()
        if not api_key:
            # Fallback: try to use lnr to get at least some issues
            result = subprocess.run(
                ["lnr", "issue", "list", "--noteam", "--noproject"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0 and result.stdout:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("Issues") or line.startswith("-"):
                        continue

                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 2:
                        issue_id = parts[0] if parts[0] else None
                        title = parts[1] if len(parts) > 1 else "Unknown"
                        status = parts[2] if len(parts) > 2 else "Unknown"

                        if issue_id:
                            issues.append(
                                {
                                    "id": issue_id,
                                    "title": title,
                                    "status": status,
                                    "source": "linear",
                                }
                            )
            return issues

        # Query Linear GraphQL API directly
        import requests

        # Linear API uses the API key directly as Authorization header
        # Format can be either just the key or "Bearer <key>"
        if api_key.startswith("Bearer "):
            auth_header = api_key
        elif api_key.startswith("lin_api_"):
            # Linear API keys typically start with lin_api_
            auth_header = api_key
        else:
            # Try with Bearer prefix
            auth_header = f"Bearer {api_key}"

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        # Get user ID - either from provided identifier or authenticated user
        user_id = None
        if user_identifier:
            # Check if it's already a user ID (UUID format), email, or name
            import re

            # Check if it looks like a UUID (8-4-4-4-12 hex digits)
            uuid_pattern = re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                re.IGNORECASE,
            )

            if uuid_pattern.match(user_identifier):
                # It's a UUID, use it directly as user ID
                user_id = user_identifier
            elif "@" in user_identifier:
                # It's an email, search by email
                user_search_query = f"""
                query {{
                    users(filter: {{ email: {{ eq: "{user_identifier}" }} }}) {{
                        nodes {{
                            id
                        }}
                    }}
                }}
                """
                response = requests.post(
                    "https://api.linear.app/graphql",
                    json={"query": user_search_query},
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    user_data = response.json()
                    users = user_data.get("data", {}).get("users", {}).get("nodes", [])
                    if users:
                        user_id = users[0].get("id")
            else:
                # Try searching by name (displayName or name field)
                # Linear supports searching by name with contains or eq
                user_search_query = f"""
                query {{
                    users(filter: {{
                        or: [
                            {{ name: {{ containsIgnoreCase: "{user_identifier}" }} }}
                            {{ displayName: {{ containsIgnoreCase: "{user_identifier}" }} }}
                        ]
                    }}) {{
                        nodes {{
                            id
                            name
                            displayName
                        }}
                    }}
                }}
                """
                response = requests.post(
                    "https://api.linear.app/graphql",
                    json={"query": user_search_query},
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    user_data = response.json()
                    users = user_data.get("data", {}).get("users", {}).get("nodes", [])
                    if users:
                        # Try to find exact match first (by name or displayName)
                        exact_match = None
                        for user in users:
                            if (
                                user.get("name", "").lower() == user_identifier.lower()
                                or user.get("displayName", "").lower()
                                == user_identifier.lower()
                            ):
                                exact_match = user
                                break
                        if exact_match:
                            user_id = exact_match.get("id")
                        else:
                            # Use first match if no exact match
                            user_id = users[0].get("id")
        else:
            # Get authenticated user ID
            user_query = """
            query {
                viewer {
                    id
                }
            }
            """
            response = requests.post(
                "https://api.linear.app/graphql",
                json={"query": user_query},
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                user_data = response.json()
                user_id = user_data.get("data", {}).get("viewer", {}).get("id")

        if not user_id:
            return issues

        # Query issues assigned to user, updated (not created) in date range
        # Linear API expects ISO 8601 format
        from_date_iso = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_date_iso = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Use cursor-based pagination to fetch all issues
        cursor = None
        has_next_page = True

        while has_next_page:
            cursor_part = f', after: "{cursor}"' if cursor else ""
            issues_query = f"""
            query {{
                issues(
                    filter: {{
                        assignee: {{ id: {{ eq: "{user_id}" }} }}
                        updatedAt: {{ gte: "{from_date_iso}", lte: "{to_date_iso}" }}
                    }}
                    first: 100{cursor_part}
                    orderBy: updatedAt
                ) {{
                    pageInfo {{
                        hasNextPage
                        endCursor
                    }}
                    nodes {{
                        identifier
                        title
                        state {{
                            name
                        }}
                        updatedAt
                        createdAt
                    }}
                }}
            }}
            """

            response = requests.post(
                "https://api.linear.app/graphql",
                json={"query": issues_query},
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                issues_data = data.get("data", {}).get("issues", {})
                page_info = issues_data.get("pageInfo", {})
                nodes = issues_data.get("nodes", [])

                for node in nodes:
                    updated_at = node.get("updatedAt")
                    created_at = node.get("createdAt")

                    # Only include issues that were actually updated (worked on) in the timeframe
                    # Exclude issues where updatedAt == createdAt (only created, not worked on)
                    if updated_at and updated_at != created_at:
                        try:
                            updated_date = datetime.fromisoformat(
                                updated_at.replace("Z", "+00:00")
                            )

                            # Verify updated date is in range
                            from_date_tz = from_date.replace(tzinfo=updated_date.tzinfo)
                            to_date_tz = to_date.replace(tzinfo=updated_date.tzinfo)

                            if from_date_tz <= updated_date <= to_date_tz:
                                # Only include if it was actually updated (not just created) in the timeframe
                                # This means updatedAt should be different from createdAt
                                issues.append(
                                    {
                                        "id": node.get("identifier", "Unknown"),
                                        "title": node.get("title", "Unknown"),
                                        "status": node.get("state", {}).get(
                                            "name", "Unknown"
                                        ),
                                        "updated_at": updated_at,
                                        "created_at": created_at,
                                        "source": "linear",
                                    }
                                )
                        except (ValueError, AttributeError):
                            # If date parsing fails, skip this issue
                            pass

                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
            else:
                has_next_page = False

    except ImportError:
        # requests not available, fallback to lnr
        pass
    except Exception:
        # Silently fail if Linear API is not available or configured
        pass

    return issues
