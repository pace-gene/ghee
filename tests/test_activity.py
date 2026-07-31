"""Tests for activity functions."""

from __future__ import annotations

import pytest


class TestResolveUserLogin:
    """Tests for resolve_user_login() function."""

    def test_valid_login_returns_canonical_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid login should return the canonical login from gh output."""
        from github_tools.github_api import resolve_user_login

        fake_calls = []

        def fake_run_gh_command(cmd: list[str], quiet: bool = False) -> str:
            fake_calls.append((cmd, quiet))
            return "pace-gene"

        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command", fake_run_gh_command
        )

        result = resolve_user_login("PACE-Gene")
        assert result == "pace-gene"
        assert len(fake_calls) == 1
        assert fake_calls[0] == (["api", "users/PACE-Gene", "--jq", ".login"], True)

    def test_unknown_login_returns_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown login (empty gh output) should return empty string."""
        from github_tools.github_api import resolve_user_login

        def fake_run_gh_command(cmd: list[str], quiet: bool = False) -> str:
            return ""

        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command", fake_run_gh_command
        )

        result = resolve_user_login("nonexistent-user-xyz")
        assert result == ""

    def test_whitespace_input_returns_empty_string_no_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Whitespace-only input should return empty string without calling gh."""
        from github_tools.github_api import resolve_user_login

        fake_calls = []

        def fake_run_gh_command(cmd: list[str], quiet: bool = False) -> str:
            fake_calls.append((cmd, quiet))
            return "should-not-be-called"

        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command", fake_run_gh_command
        )

        result = resolve_user_login("   ")
        assert result == ""
        assert len(fake_calls) == 0

    def test_empty_input_returns_empty_string_no_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty input should return empty string without calling gh."""
        from github_tools.github_api import resolve_user_login

        fake_calls = []

        def fake_run_gh_command(cmd: list[str], quiet: bool = False) -> str:
            fake_calls.append((cmd, quiet))
            return "should-not-be-called"

        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command", fake_run_gh_command
        )

        result = resolve_user_login("")
        assert result == ""
        assert len(fake_calls) == 0


class TestActivityUserValidation:
    """Tests for user login validation in activity command."""

    def test_invalid_user_exits_with_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid user should exit with code 1 and error message."""
        from click.testing import CliRunner

        from github_tools.__main__ import cli

        # Track function calls to verify they didn't run
        fake_calls = {
            "get_user_events": 0,
            "get_recent_repos": 0,
            "get_pull_requests": 0,
            "get_linear_issues": 0,
        }

        def fake_get_user_login() -> str:
            return "pace-gene"

        def fake_resolve_user_login(login: str) -> str:
            return ""  # Invalid user

        def fake_get_user_events(*args: object, **kwargs: object) -> list:
            fake_calls["get_user_events"] += 1
            raise AssertionError("get_user_events should not be called")

        def fake_get_recent_repos(*args: object, **kwargs: object) -> list:
            fake_calls["get_recent_repos"] += 1
            raise AssertionError("get_recent_repos should not be called")

        def fake_get_pull_requests(*args: object, **kwargs: object) -> list:
            fake_calls["get_pull_requests"] += 1
            raise AssertionError("get_pull_requests should not be called")

        def fake_get_linear_issues(*args: object, **kwargs: object) -> list:
            fake_calls["get_linear_issues"] += 1
            raise AssertionError("get_linear_issues should not be called")

        monkeypatch.setattr(
            "github_tools.__main__.get_user_login", fake_get_user_login
        )
        monkeypatch.setattr(
            "github_tools.__main__.resolve_user_login", fake_resolve_user_login
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_user_events", fake_get_user_events
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_recent_repos", fake_get_recent_repos
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_pull_requests", fake_get_pull_requests
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_linear_issues", fake_get_linear_issues
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["activity", "--no-ai-summary", "-u", "gene.pasquet"])

        assert result.exit_code == 1
        assert "gene.pasquet" in result.output
        # Check for error message about invalid login
        output_lower = result.output.lower()
        assert "not found" in output_lower or "github login" in output_lower
        # Verify no fetcher functions were called
        assert all(count == 0 for count in fake_calls.values())

    def test_valid_user_succeeds_with_canonical_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid user should succeed and pass canonical login to fetchers."""
        from click.testing import CliRunner

        from github_tools.__main__ import cli

        received_username: list[str] = []

        def fake_get_user_login() -> str:
            return "pace-gene"

        def fake_resolve_user_login(login: str) -> str:
            return "pace-gene"  # Valid user, return canonical

        def fake_get_user_events(username: str, *args: object, **kwargs: object) -> list:
            received_username.append(username)
            return []

        def fake_analyze_events(*args: object, **kwargs: object) -> dict:
            return {"commits": [], "pull_requests": []}

        def fake_get_recent_repos(username: str, *args: object, **kwargs: object) -> list:
            return []

        def fake_get_pull_requests(*args: object, **kwargs: object) -> list:
            return []

        def fake_get_linear_issues(*args: object, **kwargs: object) -> list:
            return []

        monkeypatch.setattr(
            "github_tools.__main__.get_user_login", fake_get_user_login
        )
        monkeypatch.setattr(
            "github_tools.__main__.resolve_user_login", fake_resolve_user_login
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_user_events", fake_get_user_events
        )
        monkeypatch.setattr(
            "github_tools.__main__.analyze_events", fake_analyze_events
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_recent_repos", fake_get_recent_repos
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_pull_requests", fake_get_pull_requests
        )
        monkeypatch.setattr(
            "github_tools.__main__.get_linear_issues", fake_get_linear_issues
        )
        def fake_print_activity_summary(*args: object, **kwargs: object) -> dict:
            return {"commits": [], "prs": [], "linear_issues": []}

        monkeypatch.setattr(
            "github_tools.__main__.print_activity_summary", fake_print_activity_summary
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["activity", "--no-ai-summary", "-u", "PACE-Gene"])

        assert result.exit_code == 0
        # Verify canonical login was passed to get_user_events
        assert "pace-gene" in received_username


class TestAnalyzeEventsPRAuthorFilter:
    """Tests for PR author filtering in analyze_events()."""

    def test_pr_authored_by_user_is_included(self) -> None:
        """PR authored by target user should be included."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 1,
                        "title": "My PR",
                        "state": "open",
                        "user": {"login": "pace-gene"},
                    }
                },
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 1
        assert result["pull_requests"][0]["number"] == 1
        assert result["pull_requests"][0]["title"] == "My PR"

    def test_pr_authored_by_user_case_insensitive(self) -> None:
        """PR authored by target user (different case) should be included."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 1,
                        "title": "My PR",
                        "state": "open",
                        "user": {"login": "PACE-Gene"},
                    }
                },
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 1
        assert result["pull_requests"][0]["number"] == 1

    def test_pr_authored_by_different_user_is_excluded(self) -> None:
        """PR authored by different user should be excluded."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 1,
                        "title": "Someone else's PR",
                        "state": "open",
                        "user": {"login": "someone-else"},
                    }
                },
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 0

    def test_pr_with_missing_pull_request_payload_is_excluded(self) -> None:
        """PR event with missing pull_request payload should be excluded."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {},
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 0

    def test_pr_with_missing_user_is_excluded(self) -> None:
        """PR event with missing user login should be excluded."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 1,
                        "title": "PR with unknown author",
                        "state": "open",
                    }
                },
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 0

    def test_pr_with_missing_number_is_excluded(self) -> None:
        """PR event with missing number should be excluded."""
        from github_tools.github_api import analyze_events

        events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "title": "PR with no number",
                        "state": "open",
                        "user": {"login": "pace-gene"},
                    }
                },
            }
        ]

        result = analyze_events(events, "pace-gene")
        assert len(result["pull_requests"]) == 0

    def test_print_activity_summary_deduplicates_prs_by_repo_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PR with same (repo, number) should be deduplicated, preferring API data."""
        from github_tools.formatters import print_activity_summary
        from github_tools.github_api import analyze_events

        # Suppress output
        monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

        # Create raw events: one duplicate and one foreign-authored
        raw_events = [
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 1,
                        "title": "Event version (no author check)",
                        "state": "open",
                        "user": {"login": "pace-gene"},
                    }
                },
            },
            {
                "type": "PullRequestEvent",
                "repo": "org/repo",
                "created_at": "2026-07-20T00:00:00Z",
                "payload": {
                    "pull_request": {
                        "number": 2,
                        "title": "Foreign authored PR",
                        "state": "open",
                        "user": {"login": "someone-else"},
                    }
                },
            },
        ]

        # Filter events by author
        events_summary = analyze_events(raw_events, "pace-gene")

        commits: list[dict] = []
        prs = [
            {
                "repo": "org/repo",
                "number": 1,
                "title": "Real title",
                "state": "open",
                "created_at": "2026-07-20T00:00:00Z",
            }
        ]

        from datetime import datetime

        result = print_activity_summary(
            commits,
            prs,
            events_summary,
            [],
            datetime(2026, 7, 20),
            datetime(2026, 7, 31),
        )

        # Should have 1 PR: the deduplicated one from API data (foreign PR filtered by author check)
        assert len(result["prs"]) == 1
        assert result["prs"][0]["number"] == 1
        assert result["prs"][0]["title"] == "Real title"
