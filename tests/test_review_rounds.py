"""Tests for the pr-rounds feature: parse_pr_ref, get_pr_review_rounds,
format_pr_review_rounds, and the CLI command."""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

import github_tools
from github_tools.__main__ import cli
from github_tools.formatters import format_pr_review_rounds
from github_tools.github_api import get_pr_review_rounds
from github_tools.utils import parse_pr_ref


def _build_graphql_response(
    *,
    pr_number: int = 7,
    pr_title: str = "Add feature X",
    pr_url: str = "https://github.com/o/r/pull/7",
    reviews: list[dict[str, Any]] | None = None,
    reviews_total: int | None = None,
    review_threads: list[dict[str, Any]] | None = None,
    review_threads_total: int | None = None,
    auto_threads: bool = True,
    pr: dict[str, Any] | None = None,
) -> str:
    """Build a JSON string mimicking the GraphQL response."""
    if reviews is None:
        reviews = []
    if reviews_total is None:
        reviews_total = len(reviews)
    if review_threads is None:
        if auto_threads:
            review_threads = []
            for r in reviews:
                comments_block = r.get("comments") or {}
                for c in comments_block.get("nodes", []) or []:
                    db_id = c.get("databaseId")
                    if db_id is None:
                        continue
                    review_threads.append(
                        {
                            "id": f"PRRT_kw{db_id}",
                            "isResolved": False,
                            "comments": {"nodes": [{"databaseId": db_id}]},
                        }
                    )
        else:
            review_threads = []
    if review_threads_total is None:
        review_threads_total = len(review_threads)
    if pr is None:
        pr = {
            "number": pr_number,
            "title": pr_title,
            "url": pr_url,
            "reviews": {"totalCount": reviews_total, "nodes": reviews},
            "reviewThreads": {
                "totalCount": review_threads_total,
                "nodes": review_threads,
            },
        }
    return json.dumps({"data": {"repository": {"pullRequest": pr}}})


def _make_review(
    *,
    review_id: str = "PRR_kwDO1",
    database_id: int | None = 1,
    state: str = "APPROVED",
    submitted_at: str | None = "2026-05-01T10:00:00Z",
    body: str = "LGTM",
    url: str = "https://github.com/o/r/pull/7#pullrequestreview-1",
    author_login: str | None = "alice",
    comments: list[dict[str, Any]] | None = None,
    comments_total: int | None = None,
) -> dict[str, Any]:
    if comments is None:
        comments = []
    if comments_total is None:
        comments_total = len(comments)
    return {
        "id": review_id,
        "databaseId": database_id,
        "state": state,
        "submittedAt": submitted_at,
        "body": body,
        "url": url,
        "author": ({"login": author_login} if author_login is not None else None),
        "comments": {"totalCount": comments_total, "nodes": comments},
    }


def _make_comment(
    *,
    cid: str = "PRRC_kwDO_long_1",
    body: str = "nit",
    path: str = "src/main.py",
    line: int | None = 42,
    start_line: int | None = None,
    original_line: int | None = None,
    original_start_line: int | None = None,
    author_login: str | None = "alice",
    created_at: str = "2026-05-01T09:58:00Z",
    url: str = "https://github.com/o/r/pull/7#discussion_r1",
    diff_hunk: str = "@@ ... @@",
    database_id: int | None = 1001,
    reply_to_id: str | None = None,
    commit_oid: str | None = "deadbeef1",
    original_commit_oid: str | None = "deadbeef0",
) -> dict[str, Any]:
    return {
        "id": cid,
        "databaseId": database_id,
        "body": body,
        "path": path,
        "line": line,
        "startLine": start_line,
        "originalLine": original_line,
        "originalStartLine": original_start_line,
        "author": ({"login": author_login} if author_login is not None else None),
        "createdAt": created_at,
        "url": url,
        "diffHunk": diff_hunk,
        "replyTo": ({"id": reply_to_id} if reply_to_id is not None else None),
        "commit": ({"oid": commit_oid} if commit_oid is not None else None),
        "originalCommit": (
            {"oid": original_commit_oid} if original_commit_oid is not None else None
        ),
    }


class TestParsePrRef:
    def test_parse_pr_ref_full_url(self) -> None:
        assert parse_pr_ref("https://github.com/foo/bar/pull/7") == ("foo", "bar", 7)

    def test_parse_pr_ref_url_with_trailing_slash(self) -> None:
        assert parse_pr_ref("https://github.com/foo/bar/pull/7/") == ("foo", "bar", 7)

    def test_parse_pr_ref_url_ignores_repo_override(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = parse_pr_ref(
            "https://github.com/foo/bar/pull/7", repo_override="other/thing"
        )
        assert result == ("foo", "bar", 7)
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()

    def test_parse_pr_ref_number_with_repo_override(self) -> None:
        assert parse_pr_ref("123", repo_override="foo/bar") == ("foo", "bar", 123)

    def test_parse_pr_ref_number_uses_git_repo_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "github_tools.utils.get_git_repo_info", lambda: ("acme", "widgets")
        )
        assert parse_pr_ref("42") == ("acme", "widgets", 42)

    def test_parse_pr_ref_number_no_repo_anywhere_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("github_tools.utils.get_git_repo_info", lambda: None)
        with pytest.raises(ValueError, match="Could not determine repository"):
            parse_pr_ref("42")

    def test_parse_pr_ref_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Unrecognised PR reference"):
            parse_pr_ref("https://example.com/foo/bar/pull/7")

    def test_parse_pr_ref_invalid_repo_override_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_pr_ref("123", repo_override="not-a-slash-pair")


class TestGetPrReviewRounds:
    def test_get_pr_review_rounds_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        comment = _make_comment()
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert len(rounds) == 1
        rd = rounds[0]
        assert rd["review_id"] == "PRR_kwDO1"
        assert rd["database_id"] == 1
        assert rd["state"] == "APPROVED"
        assert rd["submitted_at"] == "2026-05-01T10:00:00Z"
        assert rd["user"] == "alice"
        assert rd["body"] == "LGTM"
        assert rd["url"] == "https://github.com/o/r/pull/7#pullrequestreview-1"
        assert rd["pr_number"] == 7
        assert rd["pr_title"] == "Add feature X"
        assert rd["pr_url"] == "https://github.com/o/r/pull/7"
        assert len(rd["comments"]) == 1
        c = rd["comments"][0]
        assert c["body"] == "nit"
        assert c["path"] == "src/main.py"
        assert c["line"] == 42
        assert c["user"] == "alice"
        assert c["pr_number"] == 7
        assert c["pr_title"] == "Add feature X"
        assert c["pr_url"] == "https://github.com/o/r/pull/7"

    def test_get_pr_review_rounds_excludes_pending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        approved = _make_review(
            review_id="A",
            database_id=1,
            state="APPROVED",
            submitted_at="2026-05-01T10:00:00Z",
        )
        pending = _make_review(
            review_id="B",
            database_id=2,
            state="PENDING",
            submitted_at=None,
        )
        response = _build_graphql_response(reviews=[approved, pending])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert len(rounds) == 1
        assert rounds[0]["review_id"] == "A"

    def test_get_pr_review_rounds_review_with_no_comments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = _make_review(comments=[])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert len(rounds) == 1
        assert rounds[0]["comments"] == []

    def test_get_pr_review_rounds_pr_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        response = json.dumps({"data": {"repository": {"pullRequest": None}}})
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 99)

        assert rounds == []
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_get_pr_review_rounds_gh_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: "",
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert rounds == []
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()

    def test_get_pr_review_rounds_malformed_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: "not-json",
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert rounds == []
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()

    def test_get_pr_review_rounds_truncation_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        review = _make_review(comments=[], comments_total=250)
        response = _build_graphql_response(reviews=[review], reviews_total=200)
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert len(rounds) == 1
        captured = capsys.readouterr()
        # Two warnings expected (reviews + comments truncation).
        assert captured.err.lower().count("warning") >= 2

    def test_get_pr_review_rounds_null_author(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = _make_review(author_login=None)
        # Force the review's author to be None at the top level.
        review["author"] = None
        comment = _make_comment(author_login=None)
        comment["author"] = None
        review["comments"]["nodes"] = [comment]
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert rounds[0]["user"] == "unknown"
        assert rounds[0]["comments"][0]["user"] == "unknown"

    def test_get_pr_review_rounds_comment_id_short_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(cid="PRRC_kwDOAAAA_99999")
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert rounds[0]["comments"][0]["id"] == "99999"

    def test_get_pr_review_rounds_sorted_ascending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        late = _make_review(review_id="late", submitted_at="2026-05-02T10:00:00Z")
        early = _make_review(review_id="early", submitted_at="2026-05-01T10:00:00Z")
        response = _build_graphql_response(reviews=[late, early])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert [r["review_id"] for r in rounds] == ["early", "late"]

    def test_get_pr_review_rounds_includes_thread_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(database_id=1001)
        review = _make_review(comments=[comment])
        threads = [
            {
                "id": "PRRT_kwDOXYZ",
                "isResolved": False,
                "comments": {"nodes": [{"databaseId": 1001}]},
            }
        ]
        response = _build_graphql_response(reviews=[review], review_threads=threads)
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["thread_id"] == "PRRT_kwDOXYZ"
        assert c["is_resolved"] is False

    def test_get_pr_review_rounds_resolved_thread(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(database_id=1001)
        review = _make_review(comments=[comment])
        threads = [
            {
                "id": "PRRT_kwDOXYZ",
                "isResolved": True,
                "comments": {"nodes": [{"databaseId": 1001}]},
            }
        ]
        response = _build_graphql_response(reviews=[review], review_threads=threads)
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["thread_id"] == "PRRT_kwDOXYZ"
        assert c["is_resolved"] is True

    def test_get_pr_review_rounds_in_reply_to_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment()
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["in_reply_to_id"] is None

    def test_get_pr_review_rounds_in_reply_to_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(reply_to_id="PRRC_kwDOAAAA_55555")
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["in_reply_to_id"] == "55555"

    def test_get_pr_review_rounds_commit_oids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(commit_oid="abc123", original_commit_oid="def456")
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["commit_id"] == "abc123"
        assert c["original_commit_id"] == "def456"

    def test_get_pr_review_rounds_null_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        comment = _make_comment(commit_oid=None, original_commit_oid=None)
        review = _make_review(comments=[comment])
        response = _build_graphql_response(reviews=[review])
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)
        c = rounds[0]["comments"][0]

        assert c["commit_id"] is None
        assert c["original_commit_id"] is None

    def test_get_pr_review_rounds_unmapped_comment_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        c1 = _make_comment(cid="PRRC_kwDOAAAA_1", database_id=9999)
        c2 = _make_comment(cid="PRRC_kwDOAAAA_2", database_id=8888)
        review = _make_review(comments=[c1, c2])
        response = _build_graphql_response(
            reviews=[review], auto_threads=False, review_threads=[]
        )
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert rounds[0]["comments"][0]["thread_id"] is None
        assert rounds[0]["comments"][0]["is_resolved"] is False
        assert rounds[0]["comments"][1]["thread_id"] is None
        assert rounds[0]["comments"][1]["is_resolved"] is False
        captured = capsys.readouterr()
        assert captured.err.lower().count("not found in reviewthreads") == 1

    def test_get_pr_review_rounds_review_threads_truncation_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        review = _make_review(comments=[])
        response = _build_graphql_response(
            reviews=[review],
            auto_threads=False,
            review_threads=[],
            review_threads_total=200,
        )
        monkeypatch.setattr(
            "github_tools.github_api.run_gh_command",
            lambda cmd, quiet=False: response,
        )

        rounds = get_pr_review_rounds("o", "r", 7)

        assert len(rounds) == 1
        captured = capsys.readouterr()
        assert "review threads" in captured.err.lower()


def _make_round(
    *,
    review_id: str = "PRR_kwDO1",
    state: str = "APPROVED",
    submitted_at: str = "2026-05-01T10:00:00Z",
    user: str = "alice",
    body: str = "LGTM",
    url: str = "https://github.com/o/r/pull/7#pullrequestreview-1",
    pr_number: int = 7,
    pr_title: str = "Add feature X",
    pr_url: str = "https://github.com/o/r/pull/7",
    comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "database_id": 1,
        "state": state,
        "submitted_at": submitted_at,
        "user": user,
        "body": body,
        "url": url,
        "pr_number": pr_number,
        "pr_title": pr_title,
        "pr_url": pr_url,
        "comments": comments if comments is not None else [],
    }


def _make_inline_comment(
    *,
    body: str = "nit",
    path: str = "src/main.py",
    line: int | None = 42,
    user: str = "alice",
    created_at: str = "2026-05-01T09:58:00Z",
    url: str = "https://github.com/o/r/pull/7#discussion_r1",
    is_resolved: bool = False,
) -> dict[str, Any]:
    return {
        "id": "1",
        "body": body,
        "path": path,
        "line": line,
        "start_line": None,
        "original_line": None,
        "original_start_line": None,
        "user": user,
        "created_at": created_at,
        "url": url,
        "diff_hunk": "",
        "pr_number": 7,
        "pr_title": "Add feature X",
        "pr_url": "https://github.com/o/r/pull/7",
        "thread_id": None,
        "is_resolved": is_resolved,
        "in_reply_to_id": None,
        "commit_id": None,
        "original_commit_id": None,
    }


class TestFormatPrReviewRounds:
    def test_format_rounds_empty_human(self) -> None:
        assert format_pr_review_rounds([]) == "No review rounds found."

    def test_format_rounds_empty_json(self) -> None:
        out = format_pr_review_rounds([], json_output=True)
        assert json.loads(out) == []

    def test_format_rounds_json_roundtrip(self) -> None:
        rounds = [_make_round(comments=[_make_inline_comment()])]
        out = format_pr_review_rounds(rounds, json_output=True)
        assert json.loads(out) == rounds

    def test_format_rounds_human_smoke(self) -> None:
        rounds = [_make_round(comments=[_make_inline_comment()])]
        out = format_pr_review_rounds(rounds)
        assert "📝 Review Rounds for PR #7" in out
        assert "Add feature X" in out
        assert "1 rounds" in out
        assert "1 comments" in out
        assert "URL: https://github.com/o/r/pull/7" in out
        assert "✅" in out
        assert "Round 1" in out
        assert "APPROVED" in out
        assert "alice" in out
        assert "💬 LGTM" in out
        assert "src/main.py:42" in out
        assert "🔗 https://github.com/o/r/pull/7#pullrequestreview-1" in out
        assert "🔗 https://github.com/o/r/pull/7#discussion_r1" in out

    def test_format_rounds_human_omits_empty_review_body(self) -> None:
        rounds = [_make_round(body="   ", comments=[_make_inline_comment()])]
        out = format_pr_review_rounds(rounds)
        # Inline comment body still rendered, but the round-level body line
        # (the one immediately after the round header URL) is omitted.
        review_url_idx = out.index("#pullrequestreview-1")
        separator_idx = out.index("-" * 30)
        between = out[review_url_idx:separator_idx]
        assert "💬" not in between

    def test_format_rounds_human_zero_comments(self) -> None:
        rounds = [_make_round(comments=[])]
        out = format_pr_review_rounds(rounds)
        assert "Round 1" in out
        # No inline-comment separator when there are no comments.
        assert "-" * 30 not in out

    @pytest.mark.parametrize(
        "state,icon",
        [
            ("APPROVED", "✅"),
            ("CHANGES_REQUESTED", "❌"),
            ("COMMENTED", "💬"),
            ("DISMISSED", "🗑️"),
        ],
    )
    def test_format_rounds_human_state_icons(self, state: str, icon: str) -> None:
        rounds = [_make_round(state=state)]
        out = format_pr_review_rounds(rounds)
        assert icon in out
        assert state in out

    def test_format_rounds_human_unknown_state(self) -> None:
        rounds = [_make_round(state="MYSTERY")]
        out = format_pr_review_rounds(rounds)
        # Fallback round icon.
        assert "📝 Round 1" in out
        assert "MYSTERY" in out

    def test_format_rounds_human_resolved_indicator(self) -> None:
        rounds = [_make_round(comments=[_make_inline_comment(is_resolved=True)])]
        out = format_pr_review_rounds(rounds)
        assert "✅ src/main.py:42" in out

    def test_format_rounds_human_unresolved_no_indicator(self) -> None:
        rounds = [_make_round(comments=[_make_inline_comment()])]
        out = format_pr_review_rounds(rounds)
        assert "src/main.py:42" in out
        assert "✅ src/main.py" not in out


class TestCliPrRounds:
    def test_cli_pr_rounds_invokes_fetcher_and_formatter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_args: dict[str, Any] = {}

        def fake_fetcher(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
            captured_args["owner"] = owner
            captured_args["repo"] = repo
            captured_args["pr_number"] = pr_number
            return [{"sentinel": True}]

        def fake_formatter(rounds: list[dict], json_output: bool = False) -> str:
            captured_args["rounds"] = rounds
            captured_args["json_output"] = json_output
            return "FORMATTED"

        monkeypatch.setattr("github_tools.__main__.get_pr_review_rounds", fake_fetcher)
        monkeypatch.setattr(
            "github_tools.__main__.format_pr_review_rounds", fake_formatter
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["pr-rounds", "https://github.com/foo/bar/pull/7"])

        assert result.exit_code == 0, result.output
        assert "FORMATTED" in result.output
        assert captured_args["owner"] == "foo"
        assert captured_args["repo"] == "bar"
        assert captured_args["pr_number"] == 7
        assert captured_args["json_output"] is False

    def test_cli_pr_rounds_bad_ref_exits_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("github_tools.utils.get_git_repo_info", lambda: None)

        runner = CliRunner()
        result = runner.invoke(cli, ["pr-rounds", "not-a-ref"])

        assert result.exit_code == 1
        # Click 8.2+ separates stdout/stderr; the error goes to stderr.
        assert "Error:" in result.stderr

    def test_cli_pr_rounds_json_flag_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_args: dict[str, Any] = {}

        def fake_fetcher(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
            return []

        def fake_formatter(rounds: list[dict], json_output: bool = False) -> str:
            captured_args["json_output"] = json_output
            return "[]"

        monkeypatch.setattr("github_tools.__main__.get_pr_review_rounds", fake_fetcher)
        monkeypatch.setattr(
            "github_tools.__main__.format_pr_review_rounds", fake_formatter
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["pr-rounds", "7", "--repo", "foo/bar", "--json"])

        assert result.exit_code == 0, result.output
        assert captured_args["json_output"] is True


def test_init_reexports_get_pr_review_rounds() -> None:
    assert (
        github_tools.get_pr_review_rounds
        is github_tools.github_api.get_pr_review_rounds
    )
    assert "get_pr_review_rounds" in github_tools.__all__
