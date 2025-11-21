"""Main entry point for GitHub Activity Analyzer CLI."""

import argparse
import sys
from datetime import datetime

from .ai import get_gemini_summary, load_gemini_key
from .formatters import format_data_for_gemini, print_activity_summary
from .github_api import (
    analyze_events,
    get_commits_for_repo,
    get_pull_requests,
    get_recent_repos,
    get_user_events,
    get_user_login,
)
from .linear_api import get_linear_issues
from .utils import get_monday_two_weeks_ago

try:
    import google.generativeai as genai
    from dotenv import load_dotenv
except ImportError:
    genai = None
    load_dotenv = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze GitHub activity between dates"
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        help="Start date (YYYY-MM-DD format, default: Monday 2 weeks ago)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        help="End date (YYYY-MM-DD format, default: now)",
    )
    parser.add_argument(
        "--no-ai-summary",
        action="store_true",
        help="Disable AI-powered summary (by default, uses Gemini if GEMINI_KEY is available)",
    )

    args = parser.parse_args()

    # Parse dates
    if args.from_date:
        try:
            from_date = datetime.strptime(args.from_date, "%Y-%m-%d")
        except ValueError:
            print("Error: Invalid --from date format. Use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        from_date = get_monday_two_weeks_ago()

    if args.to_date:
        try:
            to_date = datetime.strptime(args.to_date, "%Y-%m-%d")
            to_date = to_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            print("Error: Invalid --to date format. Use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        to_date = datetime.now()

    if from_date >= to_date:
        print("Error: --from date must be before --to date", file=sys.stderr)
        sys.exit(1)

    # Get username
    try:
        username = get_user_login()
        if not username:
            raise Exception("Could not get username")
        print(f"🔍 Analyzing GitHub activity for user: {username}")
    except Exception:
        print(
            "Error: Could not get GitHub user info. "
            "Make sure you're logged in with 'gh auth login'",
            file=sys.stderr,
        )
        sys.exit(1)

    # Fetch activity data using multiple approaches
    print("📡 Fetching activity data...")

    # Get events (most reliable for recent activity)
    events = get_user_events(username, from_date, to_date)
    events_summary = analyze_events(events, username)

    # Also try to get data directly from search APIs
    commits = []
    repos = get_recent_repos(username)

    # Get commits from recent repos (limit to avoid rate limiting)
    # Use quiet mode since 404s are expected for private/inaccessible repos
    for repo in repos[:10]:
        repo_commits = get_commits_for_repo(repo, username, from_date, to_date)
        commits.extend(repo_commits)

    prs = get_pull_requests(username, from_date, to_date)

    # Get Linear issues
    print("📋 Fetching Linear issues...")
    linear_issues = get_linear_issues(from_date, to_date)

    # Print summary
    activity_data = print_activity_summary(
        commits, prs, events_summary, linear_issues, from_date, to_date
    )

    # Generate AI summary by default if key is available (unless disabled)
    if not args.no_ai_summary:
        gemini_key = load_gemini_key()
        if not gemini_key:
            if genai is None or load_dotenv is None:
                print(
                    "\n💡 Tip: Install 'google-generativeai' and 'python-dotenv' "
                    "and set GEMINI_KEY in .env for AI-powered summaries.",
                    file=sys.stderr,
                )
        else:
            print("\n🤖 Generating AI summary with Gemini...")
            data_text = format_data_for_gemini(
                activity_data["commits"],
                activity_data["prs"],
                activity_data["linear_issues"],
                from_date,
                to_date,
            )
            current_date = datetime.now().strftime("%Y-%m-%d")
            summary = get_gemini_summary(
                data_text, gemini_key, current_date=current_date
            )
            if summary:
                print("\n" + "=" * 60)
                print("🤖 AI-Powered Summary")
                print("=" * 60)
                print(summary)
            else:
                print("⚠️  Failed to generate AI summary.", file=sys.stderr)


if __name__ == "__main__":
    main()
