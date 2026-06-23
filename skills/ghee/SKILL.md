---
name: ghee
description: >
  Use when the user asks about GitHub activity, PR review comments, or PR
  review rounds, and the `ghee` CLI is available. Prefer `ghee` over raw
  `gh` CLI calls for: summarising what was worked on over a date range,
  listing unresolved review comments in a repo, or fetching the full review
  history of a PR.
user-invocable: true
---

# ghee — Buttery Tools for GitHub

`ghee` is a Python CLI that wraps GitHub and Linear APIs to produce
human-readable (or JSON) summaries of activity, PR review comments, and
review rounds. It is installed as the `ghee` binary.

## When to reach for it

| Task | Use |
|------|-----|
| "What did I / someone work on this sprint?" | `ghee activity` |
| "What PR comments are still open in this repo?" | `ghee pr` |
| "Show me the full review history of PR #42" | `ghee pr-rounds 42` |
| Raw one-off GitHub API calls | `gh api …` (not ghee) |

## Commands

### `ghee activity` (also the default when no subcommand is given)

Summarises commits, PRs, and Linear issues for a user over a date range.
Optionally generates an AI (Gemini) narrative summary.

```bash
ghee activity [OPTIONS]
ghee          [OPTIONS]        # same thing
```

| Flag | Default | Description |
|------|---------|-------------|
| `--from DATE` | Monday 2 weeks ago | Start of range (YYYY-MM-DD) |
| `--to DATE` | now | End of range (YYYY-MM-DD) |
| `--user, -u USERNAME` | authenticated GitHub user | GitHub login to analyse |
| `--no-ai-summary` | AI on if GEMINI_KEY set | Skip the Gemini narrative |

Output: human-readable text grouped by repository. Includes commit
messages, PR states (✅ merged / 🟡 open / ❌ draft), Linear issue
states, and counts. If Gemini is configured, a narrative paragraph
follows the raw activity.

**Common patterns:**

```bash
# Last 2 weeks (default)
ghee

# Specific sprint
ghee --from 2024-06-01 --to 2024-06-14

# Another team member
ghee -u octocat --from 2024-06-01

# Skip AI narrative (faster, no API call)
ghee --no-ai-summary
```

---

### `ghee pr`

Lists **unresolved** PR review threads for every open PR in the current
repository. Must be run inside a git repo that has a GitHub `origin`.

```bash
ghee pr [--json]
```

| Flag | Description |
|------|-------------|
| `--json` | Output as a JSON array instead of human-readable text |

Output (human): grouped by PR number — file:line, reviewer, date, comment
body, URL. Useful for a quick "what review feedback is still pending?" scan.

Output (JSON): array of comment objects; useful for piping into further
processing.

---

### `ghee pr-rounds PR_REF`

Fetches all **submitted** review rounds (not pending/draft) for a PR, with
their inline comments. Shows the full review conversation in order.

```bash
ghee pr-rounds 42
ghee pr-rounds https://github.com/owner/repo/pull/42
ghee pr-rounds 42 --repo owner/repo
ghee pr-rounds 42 --json
```

| Argument/Flag | Description |
|---------------|-------------|
| `PR_REF` | PR number (e.g. `123`) or full GitHub PR URL |
| `--repo OWNER/REPO` | Override repo when using a bare number outside the git repo |
| `--json` | Output as JSON |

Output (human): one block per review round — state icon (✅ APPROVED /
❌ CHANGES_REQUESTED / 💬 COMMENTED / 🗑️ DISMISSED), reviewer, date, and
inline comments with file:line location. Resolved threads are prefixed ✅.

Output (JSON): array of round objects. Each comment includes:
- `thread_id` — GraphQL node ID of the parent thread
- `is_resolved` — boolean
- `in_reply_to_id` — short ID or null (to reconstruct reply chains)
- `commit_id` / `original_commit_id` — commit SHAs the comment was on
- `file`, `line`/`original_line`, `body`, `url`, `user`, `submitted_at`

The JSON format is ideal as input for automated PR-review or
comment-triage workflows.

---

## Configuration

**Config file:** `~/.config/ghee/config.ini`

```ini
[api_keys]
gemini = <google-gemini-api-key>     # enables AI summaries in `ghee activity`
linear = <linear-api-key>            # enables Linear issue fetching
```

**Environment variable overrides** (take precedence over config):
- `GEMINI_KEY` — Google Gemini API key
- `LINEAR_KEY` — Linear API key

**GitHub auth:** uses the `gh` CLI — run `gh auth login` once, no extra
config needed.

**Check setup:**
```bash
ghee --help           # confirms binary is installed
gh auth status        # confirms GitHub auth
```

---

## Output format guidance

- Default output is **human-readable with emoji** — good for reading,
  not for parsing.
- `--json` outputs structured data — use this when you need to process
  results programmatically or pass them to another tool/skill.
- For AI-assisted PR review workflows, use `ghee pr-rounds <PR> --json`
  and feed the result into your comment-processing tooling.

---

## Notes & gotchas

- `ghee pr` and `ghee pr-rounds` both require the `gh` CLI to be
  authenticated and available on PATH.
- `ghee pr` must be run inside a git repository; `ghee pr-rounds` can
  take a full URL to work anywhere.
- Reviews are capped at 100 per PR and comments at 100 per review; ghee
  warns if either limit is hit.
- Linear issues require a Linear API key; without one, ghee skips the
  Linear section silently (or falls back to the `lnr` CLI if installed).
- The default date range ("Monday 2 weeks ago → now") is designed for
  sprint retrospectives and standup prep.
