"""
Refactored _write_config() with better separation of concerns.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any
from contextlib import contextmanager

try:
    from tomli_w import dump as toml_dump
    HAS_TOML_WRITER = True
except ImportError:
    HAS_TOML_WRITER = False


# =============================================================================
# Separated Concerns
# =============================================================================

def _serialize_to_toml(data: dict[str, Any]) -> str:
    """
    Convert config dict to TOML string.
    
    Separated from file I/O for easier testing.
    Uses tomli_w if available, falls back to manual generation.
    """
    if HAS_TOML_WRITER:
        return toml_dump(data)
    
    # Fallback: manual TOML generation with proper escaping
    return _manual_toml_dump(data)


def _manual_toml_dump(data: dict[str, Any]) -> str:
    """
    Fallback TOML serializer when tomli_w not available.
    
    Handles basic escaping for quotes and backslashes.
    """
    lines = []
    
    for section, values in sorted(data.items()):  # Sort for deterministic output
        lines.append(f"[{section}]")
        
        for key, val in sorted(values.items()):
            # Escape quotes and backslashes in values
            escaped_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped_val}"')
        
        lines.append("")  # Blank line between sections
    
    return "\n".join(lines)


@contextmanager
def _atomic_file_writer(target_path: Path):
    """
    Context manager for atomic file writes.
    
    Creates temp file in same directory, yields file object,
    then atomically replaces target on success.
    Cleans up temp file on error.
    
    Usage:
        with _atomic_file_writer(CONFIG_FILE) as f:
            f.write(content)
    """
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory as target (required for atomic os.replace)
    fd, tmp_path = tempfile.mkstemp(
        dir=target_dir,
        prefix=f".{target_path.name}_tmp_",
        text=True  # Text mode for better cross-platform compatibility
    )
    
    tmp_path = Path(tmp_path)
    
    try:
        # Convert fd to file object and yield
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            yield f
        
        # Success: atomically replace target
        os.replace(tmp_path, target_path)
        
    except Exception:
        # Error: clean up temp file and re-raise
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass  # Best effort cleanup
        raise


def _set_secure_permissions(path: Path) -> None:
    """
    Set file permissions to 0600 (owner read/write only).
    
    Separated for platform-specific handling.
    """
    try:
        # POSIX: owner read/write only
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        # Windows or other platforms may not support POSIX permissions
        # The file is still protected by OS-level ACLs
        pass


# =============================================================================
# Main Function - Now Simple!
# =============================================================================

def write_config(data: dict[str, Any], config_file: Path) -> None:
    """
    Write config dict to file atomically with secure permissions.
    
    Refactored with separated concerns:
    - Serialization handled by _serialize_to_toml()
    - Atomic I/O handled by _atomic_file_writer()
    - Permissions handled by _set_secure_permissions()
    
    Args:
        data: Configuration dict to write
        config_file: Path to config file
        
    Raises:
        OSError: If file cannot be written
        ValueError: If data cannot be serialized
    """
    # 1. Serialize data to TOML string
    content = _serialize_to_toml(data)
    
    # 2. Write atomically
    with _atomic_file_writer(config_file) as f:
        f.write(content)
    
    # 3. Set secure permissions
    _set_secure_permissions(config_file)


# =============================================================================
# Optional: Enhanced Version with Validation
# =============================================================================

def write_config_validated(data: dict[str, Any], config_file: Path) -> None:
    """
    Enhanced version with validation and better error messages.
    """
    # Validate structure
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a dict, got {type(data)}")
    
    for section, values in data.items():
        if not isinstance(section, str):
            raise ValueError(f"Section name must be string, got {type(section)}")
        if not isinstance(values, dict):
            raise ValueError(f"Section [{section}] must be a dict, got {type(values)}")
    
    # Serialize with better error context
    try:
        content = _serialize_to_toml(data)
    except Exception as e:
        raise ValueError(f"Failed to serialize config to TOML: {e}") from e
    
    # Write with better error context
    try:
        with _atomic_file_writer(config_file) as f:
            f.write(content)
    except OSError as e:
        raise OSError(f"Failed to write config to {config_file}: {e}") from e
    
    # Set permissions
    _set_secure_permissions(config_file)


# =============================================================================
# Tests (demonstrating testability)
# =============================================================================

def test_serialize_to_toml():
    """Test TOML serialization."""
    data = {
        "claude": {"api_key": "sk-ant-123"},
        "openai": {"api_key": "sk-456"}
    }
    result = _serialize_to_toml(data)
    assert "[claude]" in result
    assert "[openai]" in result
    assert 'api_key = "sk-ant-123"' in result or "api_key = 'sk-ant-123'" in result


def test_manual_toml_escaping():
    """Test that manual TOML generation escapes special characters."""
    data = {
        "test": {"api_key": 'key"with"quotes'}
    }
    result = _manual_toml_dump(data)
    assert 'key\\"with\\"quotes' in result
    print(result)


def test_atomic_writer_success(tmp_path):
    """Test successful atomic write."""
    target = tmp_path / "test.txt"
    
    with _atomic_file_writer(target) as f:
        f.write("test content")
    
    assert target.exists()
    assert target.read_text() == "test content"


def test_atomic_writer_cleanup_on_error(tmp_path):
    """Test that temp file is cleaned up on error."""
    target = tmp_path / "test.txt"
    
    # Remove target if it exists from previous test
    if target.exists():
        target.unlink()
    
    try:
        with _atomic_file_writer(target) as f:
            f.write("partial")
            raise ValueError("simulated error")
    except ValueError:
        pass
    
    # Target should not exist (write was aborted)
    assert not target.exists(), "Target file should not exist after error"
    
    # No temp files left behind
    temp_files = list(tmp_path.glob(".test.txt_tmp_*"))
    assert len(temp_files) == 0, f"Temp files not cleaned up: {temp_files}"


def test_secure_permissions(tmp_path):
    """Test that file permissions are set correctly."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    _set_secure_permissions(test_file)
    
    # Check permissions (POSIX only)
    import platform
    if platform.system() != "Windows":
        mode = test_file.stat().st_mode
        assert mode & stat.S_IRUSR  # Owner can read
        assert mode & stat.S_IWUSR  # Owner can write
        assert not (mode & stat.S_IRGRP)  # Group cannot read
        assert not (mode & stat.S_IROTH)  # Other cannot read


if __name__ == "__main__":
    # Run basic tests
    import sys
    from pathlib import Path
    
    print("Testing manual TOML escaping...")
    test_manual_toml_escaping()
    
    print("Testing serialization...")
    test_serialize_to_toml()
    
    print("Testing atomic writer...")
    tmp = Path("/tmp/test_refactor")
    tmp.mkdir(exist_ok=True)
    test_atomic_writer_success(tmp)
    test_atomic_writer_cleanup_on_error(tmp)
    
    print("Testing permissions...")
    test_secure_permissions(tmp)
    
    print("\n✓ All tests passed!")
