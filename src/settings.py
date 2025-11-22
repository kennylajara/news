"""
Application settings management.
Uses python-dotenv to load environment variables from .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Store original environment values to prevent modification
_ENV_CACHE = {}


def get_setting(key: str, default=None):
    """
    Get a setting from environment variables.

    Similar to Django's settings pattern - returns a copy of the value
    to prevent accidental modification of the actual environment variable.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        The environment variable value or default

    Example:
        >>> OPENAI_API_KEY = get_setting('OPENAI_API_KEY')
        >>> DEBUG = get_setting('DEBUG', 'False') == 'True'
    """
    # Use cached value if available, otherwise get from env
    if key not in _ENV_CACHE:
        _ENV_CACHE[key] = os.getenv(key, default)

    # Return a copy to prevent modification
    value = _ENV_CACHE[key]

    # For mutable types, return a copy
    if isinstance(value, (list, dict)):
        return value.copy()

    return value


# OpenAI settings with defaults
OPENAI_API_KEY = get_setting('OPENAI_API_KEY')
OPENAI_MODEL = get_setting('OPENAI_MODEL', 'gpt-5-nano')
OPENAI_MAX_RETRIES = int(get_setting('OPENAI_MAX_RETRIES', '3'))
OPENAI_TIMEOUT = int(get_setting('OPENAI_TIMEOUT', '120'))

# Debug mode
DEBUG = get_setting('DEBUG', 'False').lower() in ('true', '1', 'yes')

# Database paths
CACHE_DB_PATH = get_setting('CACHE_DB_PATH', 'data/cache.db')
