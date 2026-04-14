"""
API key management for axor-cli.

Priority order (highest to lowest):
    1. --api-key CLI flag          (one-off, never saved)
    2. ADAPTER_API_KEY env var     (e.g. ANTHROPIC_API_KEY)
    3. ~/.axor/config.toml         (persistent, 0600 permissions)
    4. None → prompt via /auth

~/.axor/config.toml format:
    [claude]
    api_key = "sk-ant-..."

    [openai]
    api_key = "sk-..."
"""

from __future__ import annotations

import getpass
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Final

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # fallback for Python <3.11
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# Constants
CONFIG_DIR: Final[Path] = Path.home() / ".axor"
CONFIG_FILE: Final[Path] = CONFIG_DIR / "config.toml"

# Environment variable names per adapter
_ENV_VARS: Final[dict[str, str]] = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# TOML section keys
_TOML_API_KEY_FIELD: Final[str] = "api_key"


def resolve_api_key(adapter: str, flag_key: str | None = None) -> str | None:
    """
    Resolve API key using priority chain.

    Priority:
        1. CLI flag (--api-key)
        2. Environment variable (e.g., ANTHROPIC_API_KEY)
        3. Config file (~/.axor/config.toml)

    Args:
        adapter: Name of the adapter (e.g., "claude", "openai")
        flag_key: API key from CLI flag, if provided

    Returns:
        API key string if found, None otherwise
    """
    # Priority 1: CLI flag
    if flag_key:
        return flag_key

    # Priority 2: Environment variable
    env_var_name = _ENV_VARS.get(adapter)
    if env_var_name:
        env_key = os.environ.get(env_var_name)
        if env_key:
            return env_key

    # Priority 3: Config file
    config_key = load_from_config(adapter)
    if config_key:
        # Set in environment so downstream tools can access it
        if env_var_name:
            os.environ[env_var_name] = config_key
        return config_key

    return None


def load_from_config(adapter: str) -> str | None:
    """
    Load API key from ~/.axor/config.toml.

    Args:
        adapter: Name of the adapter section to read from

    Returns:
        API key string if found, None otherwise
    """
    if not CONFIG_FILE.exists():
        return None

    if tomllib is None:
        return None

    try:
        with CONFIG_FILE.open("rb") as f:
            config: dict[str, Any] = tomllib.load(f)
        adapter_config = config.get(adapter, {})
        return adapter_config.get(_TOML_API_KEY_FIELD)
    except Exception:
        # Silently fail for corrupted config files
        return None


def save_to_config(adapter: str, api_key: str) -> None:
    """
    Save API key to ~/.axor/config.toml with 0600 permissions.

    Args:
        adapter: Name of the adapter section to save to
        api_key: The API key to save

    Raises:
        Exception: If the file cannot be written
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing config or start fresh
    existing_config = _load_existing_config()

    # Update or create adapter section
    if adapter not in existing_config:
        existing_config[adapter] = {}
    existing_config[adapter][_TOML_API_KEY_FIELD] = api_key

    _write_config(existing_config)


def clear_from_config(adapter: str) -> bool:
    """
    Remove adapter key from config.

    Args:
        adapter: Name of the adapter section to remove

    Returns:
        True if the key existed and was removed, False otherwise
    """
    if not CONFIG_FILE.exists() or tomllib is None:
        return False

    existing_config = _load_existing_config()

    if adapter not in existing_config:
        return False

    del existing_config[adapter]
    _write_config(existing_config)
    return True


def prompt_and_save(adapter: str) -> str | None:
    """
    Interactively prompt for API key and optionally save to config.

    Args:
        adapter: Name of the adapter to configure

    Returns:
        The entered API key, or None if user cancelled or entered nothing
    """
    env_var_name = _ENV_VARS.get(adapter, f"{adapter.upper()}_API_KEY")

    _print_prompt_header(adapter, env_var_name)

    # Get API key from user
    api_key = _prompt_for_key(adapter)
    if not api_key:
        return None

    # Ask if user wants to save
    should_save = _prompt_to_save()
    if should_save:
        _save_key_to_config(adapter, api_key)
    else:
        print("  Key not saved — valid for this session only.")

    # Set in environment for current session
    if env_var_name:
        os.environ[env_var_name] = api_key

    return api_key


# Private helper functions


def _load_existing_config() -> dict[str, Any]:
    """
    Load existing config file or return empty dict.

    Returns:
        Existing config as dictionary, or empty dict if unavailable
    """
    if not CONFIG_FILE.exists() or tomllib is None:
        return {}

    try:
        with CONFIG_FILE.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        # If config is corrupted, start fresh
        return {}


def _write_config(data: dict[str, Any]) -> None:
    """
    Write config dict to file atomically with 0600 permissions.

    Uses atomic write via temporary file to prevent corruption.

    Args:
        data: Configuration dictionary to write

    Raises:
        Exception: If the file cannot be written
    """
    toml_content = _serialize_to_toml(data)

    # Atomic write via temp file
    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".axor_cfg_")
        with os.fdopen(fd, "w") as f:
            f.write(toml_content)
        # Mark fd as closed so we don't try to close it again
        fd = -1

        # Replace old config with new one atomically
        os.replace(tmp_path, CONFIG_FILE)
        CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except Exception:
        # Clean up temp file if something went wrong
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _serialize_to_toml(data: dict[str, Any]) -> str:
    """
    Serialize config dictionary to TOML format.

    Args:
        data: Configuration dictionary

    Returns:
        TOML-formatted string
    """
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, val in values.items():
            # Escape quotes in values
            escaped_val = str(val).replace('"', r'\"')
            lines.append(f'{key} = "{escaped_val}"')
        lines.append("")  # Blank line between sections
    return "\n".join(lines)


def _print_prompt_header(adapter: str, env_var_name: str) -> None:
    """Print header information for interactive prompt."""
    print(f"\n  No API key found for '{adapter}'.")
    print(f"  (checked: --api-key flag, {env_var_name} env var, {CONFIG_FILE})\n")


def _prompt_for_key(adapter: str) -> str | None:
    """
    Prompt user for API key with hidden input.

    Args:
        adapter: Name of the adapter

    Returns:
        API key string, or None if cancelled/empty
    """
    try:
        key = getpass.getpass(f"  {adapter.capitalize()} API key (hidden): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if not key:
        print("  No key entered.")
        return None

    return key


def _prompt_to_save() -> bool:
    """
    Prompt user whether to save the key to config.

    Returns:
        True if user wants to save, False otherwise
    """
    try:
        response = input(
            "  Save to ~/.axor/config.toml for future sessions? [Y/n]: "
        ).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False

    return response in ("", "y", "yes")


def _save_key_to_config(adapter: str, api_key: str) -> None:
    """
    Save API key to config and print status message.

    Args:
        adapter: Name of the adapter
        api_key: API key to save
    """
    try:
        save_to_config(adapter, api_key)
        print(f"  ✓ Key saved to {CONFIG_FILE} (permissions: 600)")
    except Exception as e:
        print(f"  ✗ Could not save: {e}")
