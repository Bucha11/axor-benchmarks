"""Concise unit tests for API key management."""

import os
import stat
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Save the original module for restoration
import sys
from importlib import reload


@pytest.fixture
def temp_config(monkeypatch):
    """Temporary config directory for isolated testing."""
    temp_dir = Path(tempfile.mkdtemp())
    
    # Dynamically import and patch the module
    import api_key
    monkeypatch.setattr(api_key, 'CONFIG_DIR', temp_dir)
    monkeypatch.setattr(api_key, 'CONFIG_FILE', temp_dir / "config.toml")
    
    yield api_key
    
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestResolveApiKey:
    """Test API key resolution priority chain."""

    def test_cli_flag_highest_priority(self, temp_config):
        """CLI flag overrides all other sources."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            result = temp_config.resolve_api_key("claude", flag_key="cli-key")
            assert result == "cli-key"

    def test_env_var_second_priority(self, temp_config):
        """Environment variable used when no CLI flag."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            result = temp_config.resolve_api_key("claude")
            assert result == "env-key"

    def test_config_file_third_priority(self, temp_config):
        """Config file used when no flag or env var."""
        temp_config.save_to_config("claude", "config-key")
        with patch.dict(os.environ, {}, clear=True):
            result = temp_config.resolve_api_key("claude")
            assert result == "config-key"

    def test_returns_none_when_not_found(self, temp_config):
        """Returns None when no API key source available."""
        with patch.dict(os.environ, {}, clear=True):
            result = temp_config.resolve_api_key("claude")
            assert result is None


class TestConfigOperations:
    """Test config file read/write operations."""

    def test_save_and_load_key(self, temp_config):
        """Save and retrieve API key from config."""
        temp_config.save_to_config("claude", "sk-ant-test123")
        result = temp_config.load_from_config("claude")
        assert result == "sk-ant-test123"

    def test_config_file_permissions(self, temp_config):
        """Config file has secure 0600 permissions."""
        temp_config.save_to_config("claude", "sk-ant-test")
        mode = temp_config.CONFIG_FILE.stat().st_mode
        assert stat.S_IMODE(mode) == (stat.S_IRUSR | stat.S_IWUSR)

    def test_multiple_adapters(self, temp_config):
        """Multiple adapters can coexist in config."""
        temp_config.save_to_config("claude", "sk-ant-key")
        temp_config.save_to_config("openai", "sk-openai-key")
        
        assert temp_config.load_from_config("claude") == "sk-ant-key"
        assert temp_config.load_from_config("openai") == "sk-openai-key"

    def test_update_existing_key(self, temp_config):
        """Updating key replaces old value."""
        temp_config.save_to_config("claude", "old-key")
        temp_config.save_to_config("claude", "new-key")
        assert temp_config.load_from_config("claude") == "new-key"

    def test_clear_existing_key(self, temp_config):
        """Clear removes key from config."""
        temp_config.save_to_config("claude", "sk-ant-test")
        result = temp_config.clear_from_config("claude")
        
        assert result is True
        assert temp_config.load_from_config("claude") is None

    def test_clear_nonexistent_key(self, temp_config):
        """Clear returns False for nonexistent key."""
        result = temp_config.clear_from_config("nonexistent")
        assert result is False


class TestPromptAndSave:
    """Test interactive prompt functionality."""

    @patch('getpass.getpass', return_value="sk-new-key")
    @patch('builtins.input', return_value="y")
    def test_prompt_and_save_accepted(self, mock_input, mock_getpass, temp_config, capsys):
        """User enters key and accepts saving."""
        with patch.dict(os.environ, {}, clear=True):
            result = temp_config.prompt_and_save("claude")
            
            assert result == "sk-new-key"
            assert temp_config.load_from_config("claude") == "sk-new-key"
            assert os.environ["ANTHROPIC_API_KEY"] == "sk-new-key"

    @patch('getpass.getpass', return_value="sk-temp-key")
    @patch('builtins.input', return_value="n")
    def test_prompt_and_save_declined(self, mock_input, mock_getpass, temp_config):
        """User enters key but declines saving."""
        with patch.dict(os.environ, {}, clear=True):
            result = temp_config.prompt_and_save("claude")
            
            assert result == "sk-temp-key"
            assert temp_config.load_from_config("claude") is None
            assert os.environ["ANTHROPIC_API_KEY"] == "sk-temp-key"

    @patch('getpass.getpass', side_effect=KeyboardInterrupt)
    def test_prompt_interrupted(self, mock_getpass, temp_config, capsys):
        """User cancels prompt with Ctrl+C."""
        result = temp_config.prompt_and_save("claude")
        assert result is None

    @patch('getpass.getpass', return_value="  ")
    def test_prompt_empty_key(self, mock_getpass, temp_config):
        """User enters empty/whitespace key."""
        result = temp_config.prompt_and_save("claude")
        assert result is None
