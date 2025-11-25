"""AI/Gemini integration functions."""

import getpass
import os
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

try:
    import google.generativeai as genai
    from dotenv import load_dotenv
except ImportError:
    genai = None
    load_dotenv = None

from .config import get_api_key


def load_gemini_key() -> str | None:
    """Load GEMINI_KEY from config file or .env file (fallback)."""
    # First try config file
    api_key = get_api_key("gemini")
    if api_key:
        return api_key

    # Fallback to .env file for backward compatibility
    if load_dotenv is None:
        return None

    # Try to find .env file in current directory or parent directories
    current_dir = Path.cwd()
    env_file = current_dir / ".env"

    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Try loading from current directory anyway
        load_dotenv()

    return os.getenv("GEMINI_KEY")


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
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        # Use provided values or get defaults
        if current_date is None:
            current_date = datetime.now().strftime("%Y-%m-%d")
        if user_identity is None:
            user_identity = get_user_identity()

        prompt = render_prompt(data_text, current_date, user_identity)

        response = model.generate_content(prompt)
        return str(response.text) if response.text else None

    except Exception as e:
        print(f"Error calling Gemini API: {e}", file=sys.stderr)
        return None
