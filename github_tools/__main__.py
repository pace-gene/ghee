"""Main entry point for GitHub Activity Analyzer CLI."""

import sys
from datetime import datetime

import click

from .ai import get_gemini_summary, load_gemini_key
from .formatters import (
    format_data_for_gemini,
    format_pr_comments,
    format_pr_review_rounds,
    print_activity_summary,
)
from .github_api import (
    analyze_events,
    get_commits_for_repo,
    get_pr_review_rounds,
    get_pull_requests,
    get_recent_repos,
    get_unresolved_pr_comments,
    get_user_events,
    get_user_login,
    resolve_user_login,
)
from .linear_api import get_linear_issues
from .utils import get_git_repo_info, get_monday_two_weeks_ago, parse_pr_ref

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def _run_activity(
    from_date: str | None,
    to_date: str | None,
    no_ai_summary: bool,
    github_user: str | None,
) -> None:
    """Analyze GitHub activity between dates."""
    # Parse dates
    if from_date:
        try:
            parsed_from_date = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            click.echo("Error: Invalid --from date format. Use YYYY-MM-DD", err=True)
            sys.exit(1)
    else:
        parsed_from_date = get_monday_two_weeks_ago()

    if to_date:
        try:
            parsed_to_date = datetime.strptime(to_date, "%Y-%m-%d")
            parsed_to_date = parsed_to_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            click.echo("Error: Invalid --to date format. Use YYYY-MM-DD", err=True)
            sys.exit(1)
    else:
        parsed_to_date = datetime.now()

    if parsed_from_date >= parsed_to_date:
        click.echo("Error: --from date must be before --to date", err=True)
        sys.exit(1)

    # Resolve target user (authenticated login required for gh API access)
    try:
        viewer_login = get_user_login()
        if not viewer_login:
            raise Exception("Could not get authenticated user")
    except Exception:
        click.echo(
            "Error: Could not get GitHub user info. "
            "Make sure you're logged in with 'gh auth login'",
            err=True,
        )
        sys.exit(1)

    # Default --user to the authenticated GitHub login when omitted or blank.
    if github_user and github_user.strip():
        canonical_login = resolve_user_login(github_user.strip())
        if not canonical_login:
            click.echo(
                f"Error: GitHub user '{github_user.strip()}' not found. "
                f"Pass a GitHub login (not an email address); check with 'gh api users/<login>'.",
                err=True,
            )
            sys.exit(1)
        username = canonical_login
    else:
        username = viewer_login

    click.echo(f"🔍 Analyzing GitHub activity for user: {username}")

    # Fetch activity data using multiple approaches
    click.echo("📡 Fetching activity data...")

    # Get events (most reliable for recent activity)
    events = get_user_events(username, parsed_from_date, parsed_to_date)
    events_summary = analyze_events(events, username)

    # Also try to get data directly from search APIs
    commits = []
    repos = get_recent_repos(username, viewer_login)

    # Get commits from recent repos (limit to avoid rate limiting)
    # Use quiet mode since 404s are expected for private/inaccessible repos
    for repo in repos[:10]:
        repo_commits = get_commits_for_repo(
            repo, username, parsed_from_date, parsed_to_date
        )
        commits.extend(repo_commits)

    prs = get_pull_requests(username, parsed_from_date, parsed_to_date)

    # Get Linear issues
    click.echo("📋 Fetching Linear issues...")
    linear_issues = get_linear_issues(parsed_from_date, parsed_to_date)

    # Print summary
    activity_data = print_activity_summary(
        commits, prs, events_summary, linear_issues, parsed_from_date, parsed_to_date
    )

    # Generate AI summary by default if key is available (unless disabled)
    if not no_ai_summary:
        gemini_key = load_gemini_key()
        if not gemini_key:
            if genai is None:
                click.echo(
                    "\n💡 Tip: Install 'google-generativeai' "
                    "and set the 'gemini' API key in the config file for AI-powered summaries.",
                    err=True,
                )
            else:
                from .config import get_config_path

                config_path = get_config_path()
                click.echo(
                    f"\n💡 Tip: Set the 'gemini' API key in {config_path} "
                    "for AI-powered summaries.",
                    err=True,
                )
        else:
            click.echo("\n🤖 Generating AI summary with Gemini...")
            data_text = format_data_for_gemini(
                activity_data["commits"],
                activity_data["prs"],
                activity_data["linear_issues"],
                parsed_from_date,
                parsed_to_date,
            )
            current_date = datetime.now().strftime("%Y-%m-%d")
            summary = get_gemini_summary(
                data_text, gemini_key, current_date=current_date
            )
            if summary:
                click.echo("\n" + "=" * 60)
                click.echo("🤖 AI-Powered Summary")
                click.echo("=" * 60)
                click.echo(summary)
            else:
                click.echo("⚠️  Failed to generate AI summary.", err=True)


@click.group(invoke_without_command=True)
@click.option(
    "--from",
    "from_date",
    type=str,
    help="Start date (YYYY-MM-DD format, default: Monday 2 weeks ago)",
)
@click.option(
    "--to",
    "to_date",
    type=str,
    help="End date (YYYY-MM-DD format, default: now)",
)
@click.option(
    "--no-ai-summary",
    is_flag=True,
    help="Disable AI-powered summary (by default, uses Gemini if GEMINI_KEY is available)",
)
@click.option(
    "--user",
    "-u",
    "github_user",
    type=str,
    default=None,
    show_default="logged-in user",
    help="GitHub login to analyze",
)
@click.pass_context
def cli(
    ctx: click.Context,
    from_date: str | None,
    to_date: str | None,
    no_ai_summary: bool,
    github_user: str | None,
) -> None:
    """GitHub Activity Analyzer CLI."""
    # If no command was invoked, default to 'activity'
    if ctx.invoked_subcommand is None:
        _run_activity(from_date, to_date, no_ai_summary, github_user)
    else:
        # Store the params in context for subcommands to access if needed
        ctx.ensure_object(dict)
        ctx.obj["from_date"] = from_date
        ctx.obj["to_date"] = to_date
        ctx.obj["no_ai_summary"] = no_ai_summary
        ctx.obj["github_user"] = github_user


@cli.command()  # type: ignore[misc]
@click.option(
    "--from",
    "from_date",
    type=str,
    help="Start date (YYYY-MM-DD format, default: Monday 2 weeks ago)",
)
@click.option(
    "--to",
    "to_date",
    type=str,
    help="End date (YYYY-MM-DD format, default: now)",
)
@click.option(
    "--no-ai-summary",
    is_flag=True,
    help="Disable AI-powered summary (by default, uses Gemini if GEMINI_KEY is available)",
)
@click.option(
    "--user",
    "-u",
    "github_user",
    type=str,
    default=None,
    show_default="logged-in user",
    help="GitHub login to analyze",
)
def activity(
    from_date: str | None,
    to_date: str | None,
    no_ai_summary: bool,
    github_user: str | None,
) -> None:
    """Analyze GitHub activity between dates."""
    _run_activity(from_date, to_date, no_ai_summary, github_user)


@cli.command()  # type: ignore[misc]
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def pr(json_output: bool) -> None:
    """Fetch and list all unresolved PR comments for the current repository."""
    # Get git repo info
    repo_info = get_git_repo_info()
    if not repo_info:
        click.echo(
            "Error: Not in a git repository or could not determine repository information.",
            err=True,
        )
        click.echo(
            "Make sure you're in a directory that's part of a git clone with a remote 'origin'.",
            err=True,
        )
        sys.exit(1)

    owner, repo = repo_info
    click.echo(f"🔍 Fetching PR comments for {owner}/{repo}...")

    # Fetch comments
    comments = get_unresolved_pr_comments(owner, repo)

    # Format and output
    output = format_pr_comments(comments, json_output=json_output)
    click.echo(output)


@cli.command("pr-rounds")  # type: ignore[misc]
@click.argument("pr_ref")
@click.option(
    "--repo",
    "repo_override",
    default=None,
    help=(
        "Repository in OWNER/REPO format (overrides current git repo when "
        "PR_REF is a bare number)."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def pr_rounds(pr_ref: str, repo_override: str | None, json_output: bool) -> None:
    """Fetch review rounds (submitted reviews + their inline comments) for a PR.

    PR_REF can be a PR number (e.g. 123) or a full PR URL.
    """
    try:
        owner, repo, pr_number = parse_pr_ref(pr_ref, repo_override=repo_override)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"🔍 Fetching review rounds for {owner}/{repo}#{pr_number}...")
    rounds = get_pr_review_rounds(owner, repo, pr_number)
    output = format_pr_review_rounds(rounds, json_output=json_output)
    click.echo(output)


def main() -> None:
    """Entry point for the CLI."""
    cli()  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
