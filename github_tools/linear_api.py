"""Linear API interaction functions."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from .config import get_api_key


def get_linear_api_key() -> str | None:
    """Get Linear API key from config file, .env file, or lnr config file (fallback)."""
    # First try config file
    api_key = get_api_key("linear")
    if api_key:
        return api_key

    # Fallback to .env file for backward compatibility
    if load_dotenv is not None:
        current_dir = Path.cwd()
        env_file = current_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        else:
            load_dotenv()

        api_key = os.getenv("LINEAR_KEY")
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


def get_linear_issues(from_date: datetime, to_date: datetime) -> list[dict[str, Any]]:
    """Get Linear issues worked on in the date range using GraphQL API."""
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

        # Get user ID first
        user_query = """
        query {
            viewer {
                id
            }
        }
        """

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

        response = requests.post(
            "https://api.linear.app/graphql",
            json={"query": user_query},
            headers=headers,
            timeout=10,
        )

        if response.status_code != 200:
            return issues

        user_data = response.json()
        user_id = user_data.get("data", {}).get("viewer", {}).get("id")
        if not user_id:
            return issues

        # Query issues assigned to user, updated (not created) in date range
        # Linear API expects ISO 8601 format
        from_date_iso = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_date_iso = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        issues_query = f"""
        query {{
            issues(
                filter: {{
                    assignee: {{ id: {{ eq: "{user_id}" }} }}
                    updatedAt: {{ gte: "{from_date_iso}", lte: "{to_date_iso}" }}
                }}
                first: 100
                orderBy: updatedAt
            ) {{
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
            nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
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

    except ImportError:
        # requests not available, fallback to lnr
        pass
    except Exception:
        # Silently fail if Linear API is not available or configured
        pass

    return issues
