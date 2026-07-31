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
