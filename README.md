# GitHub Activity Analyzer

A Python package that analyzes your GitHub activity between specified dates and shows what you've worked on, with optional AI-powered summaries.

## Features

- 📝 Shows commits made in the date range
- 🔀 Lists pull requests created
- 📋 Integrates with Linear issues (optional)
- 🤖 AI-powered summary using Google Gemini (optional)
- 📊 Groups activity by repository
- 🗓️ Flexible date range selection

## Prerequisites

- Python 3.9 or higher
- GitHub CLI (`gh`) installed and authenticated
- UV package manager (recommended)

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   uv sync
   ```

## Authentication

### GitHub

Make sure you're authenticated with GitHub CLI:
```bash
gh auth login
```

### Optional: Linear Integration

To include Linear issues in your activity summary, set your Linear API key in a `.env` file:
```bash
LINEAR_KEY=your_linear_api_key
```

### Optional: AI Summaries

To enable AI-powered summaries, set your Google Gemini API key in a `.env` file:
```bash
GEMINI_KEY=your_gemini_api_key
```

## Usage

### Using the installed script

After installation, you can run the tool using the `gh-activity` command:

```bash
# Basic usage (last 2 weeks from Monday)
uv run --env-file .env gh-activity

# Specify date range
uv run --env-file .env gh-activity --from 2024-01-01 --to 2024-01-15

# Disable AI summary
uv run --env-file .env gh-activity --no-ai-summary
```

### Using Python module

Alternatively, you can run it as a Python module:

```bash
# Basic usage
uv run --env-file .env python -m github_activity

# Specify date range
uv run --env-file .env python -m github_activity --from 2024-01-01 --to 2024-01-15
```

### Arguments

- `--from DATE`: Start date in YYYY-MM-DD format (default: Monday 2 weeks ago)
- `--to DATE`: End date in YYYY-MM-DD format (default: now)
- `--no-ai-summary`: Disable AI-powered summary (enabled by default if GEMINI_KEY is set)

## Output

The script provides:
- Summary of commits grouped by repository
- Pull requests with their status
- Linear issues (if configured)
- AI-powered work area analysis (if configured)
- Total counts of each activity type

## Project Structure

The project is organized as a Python package:

```
github_activity/
├── __init__.py          # Package exports
├── __main__.py          # CLI entry point
├── ai.py                # AI/Gemini integration
├── formatters.py        # Output formatting
├── github_api.py        # GitHub API interactions
├── linear_api.py        # Linear API interactions
├── prompt.j2            # Jinja2 template for LLM prompt
└── utils.py             # Utility functions
```

## Development

### Running tests
```bash
uv run pytest tests
```

### Linting
```bash
uv run pre-commit run -a
```

## License

MIT
