"""Configuration management using INI files in standard config directories."""

import configparser
from pathlib import Path

from platformdirs import user_config_dir


def get_config_path() -> Path:
    """Get the path to the configuration file.

    Returns:
        Path to the config file in the user's standard config directory.
    """
    config_dir = Path(user_config_dir("ghee"))
    config_file = config_dir / "config.ini"
    return config_file


def ensure_config_dir() -> Path:
    """Ensure the config directory exists, creating it if necessary.

    Returns:
        Path to the config directory.
    """
    config_file = get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    return config_file


def load_config() -> configparser.ConfigParser:
    """Load configuration from INI file, creating it if it doesn't exist.

    Returns:
        ConfigParser instance with loaded configuration.
    """
    config = configparser.ConfigParser()
    config_file = ensure_config_dir()

    # If config file doesn't exist, create a helpful default one
    if not config_file.exists():
        # Create default sections with all available keys
        config.add_section("api_keys")
        config.set("api_keys", "gemini", "")
        config.set("api_keys", "linear", "")

        config.add_section("settings")
        # Add any future settings here with defaults or empty strings

        # Write the config file
        with open(config_file, "w") as f:
            config.write(f)

    # Read the config file
    config.read(config_file)
    return config


def get_api_key(key_name: str) -> str | None:
    """Get an API key from the config file.

    Args:
        key_name: Name of the API key (e.g., 'gemini', 'linear').

    Returns:
        The API key value if found, None otherwise.
    """
    config = load_config()
    try:
        return config.get("api_keys", key_name, fallback=None)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None


def set_api_key(key_name: str, value: str) -> None:
    """Set an API key in the config file.

    Args:
        key_name: Name of the API key (e.g., 'gemini', 'linear').
        value: The API key value to store.
    """
    config = load_config()
    config_file = ensure_config_dir()

    # Ensure the api_keys section exists
    if not config.has_section("api_keys"):
        config.add_section("api_keys")

    config.set("api_keys", key_name, value)

    # Write the config back to file
    with open(config_file, "w") as f:
        config.write(f)


def get_setting(section: str, key: str, fallback: str | None = None) -> str | None:
    """Get a setting from the config file.

    Args:
        section: The config section name.
        key: The setting key name.
        fallback: Default value if not found.

    Returns:
        The setting value if found, fallback otherwise.
    """
    config = load_config()
    try:
        return config.get(section, key, fallback=fallback)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return fallback
