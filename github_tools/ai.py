"""AI/Gemini integration functions."""

import getpass
import os
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

try:
    from google import genai
except ImportError:
    genai = None

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


def load_gemini_key() -> str | None:
    """Load GEMINI_KEY from environment variables or config file.

    Environment variables take precedence over config file.
    """
    # Check environment variables first (highest precedence)
    env_key = os.getenv("GEMINI_KEY")
    if env_key:
        env_key = _strip_quotes_and_whitespace(env_key)
        if env_key:
            return env_key

    # Fallback to config file
    api_key = get_api_key("gemini")
    if api_key:
        api_key = _strip_quotes_and_whitespace(api_key)
        if api_key:
            return api_key

    return None


def get_user_identity() -> str:
    """Get user identity from the operating system."""
    # Try to get full name from system
    try:
        import pwd

        user_info = pwd.getpwuid(os.getuid())
        # Try to get GECOS (full name) field
        gecos = user_info.pw_gecos
        if gecos and gecos.strip():
            # GECOS format: "Full Name,Room,Work Phone,Home Phone,Other"
            full_name = gecos.split(",")[0].strip()
            if full_name:
                return full_name
    except (ImportError, KeyError, AttributeError):
        pass

    # Fallback to username
    try:
        return getpass.getuser()
    except Exception:
        # Last resort: try environment variables
        return os.getenv("USER") or os.getenv("USERNAME") or "Unknown User"


def render_prompt(data_text: str, current_date: str, user_identity: str) -> str:
    """Render the LLM prompt template with data using Jinja2."""
    # Load template from the same directory as this module
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("prompt.j2")
    result = template.render(
        data_text=data_text,
        current_date=current_date,
        user_identity=user_identity,
    )
    return str(result)


def get_gemini_summary(
    data_text: str,
    api_key: str,
    current_date: str | None = None,
    user_identity: str | None = None,
) -> str | None:
    """Get AI summary from Gemini API.

    Args:
        data_text: The formatted activity data
        api_key: Gemini API key
        current_date: Current date string (defaults to now if not provided)
        user_identity: User identity string (defaults to OS user if not provided)
    """
    if genai is None:
        return None

    try:
        client = genai.Client(api_key=api_key)

        # Use provided values or get defaults
        if current_date is None:
            current_date = datetime.now().strftime("%Y-%m-%d")
        if user_identity is None:
            user_identity = get_user_identity()

        prompt = render_prompt(data_text, current_date, user_identity)

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return str(response.text) if response.text else None

    except Exception as e:
        print(f"Error calling Gemini API: {e}", file=sys.stderr)
        return None
