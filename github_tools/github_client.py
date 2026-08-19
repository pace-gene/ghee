"""GitHub API client bootstrap (PyGithub) shared across github_api.py."""

import os
import subprocess
from functools import lru_cache

from github import Auth, Github


@lru_cache(maxsize=1)
def get_github_token() -> str:
    """Get a GitHub auth token: gh CLI token, else GH_TOKEN/GITHUB_TOKEN env vars.

    Cached for the lifetime of the process — ghee is a short-lived CLI
    invocation and the token can't change mid-run.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        token = result.stdout.strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        env_token = os.getenv(var)
        if env_token:
            return env_token.strip()

    raise RuntimeError(
        "No GitHub token found. Run `gh auth login` or set GH_TOKEN/GITHUB_TOKEN."
    )


@lru_cache(maxsize=1)
def get_github_client() -> Github:
    """Build a shared PyGithub client, respecting GH_HOST for GitHub Enterprise.

    Cached as a singleton so repeated calls (e.g. once per repo when fetching
    commits) reuse the same HTTP connection pool instead of paying a fresh
    TLS handshake and `gh auth token` subprocess spawn each time.
    """
    auth = Auth.Token(get_github_token())
    host = os.getenv("GH_HOST", "").strip()
    kwargs = {"auth": auth, "per_page": 100}
    if host and host != "github.com":
        return Github(base_url=f"https://{host}/api/v3", **kwargs)
    return Github(**kwargs)
