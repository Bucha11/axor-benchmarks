"""Unit tests for API key management."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock


# Import the module - adjust import path as needed
import sys
sys.path.insert(0, str(Path(__file__).parent))

try:
    from api_key import (
        resolve_api_key,
        load_from_config,
        save_to_config,
        clear_from_config,
        prompt_and_save,
        CONFIG_FILE,
        CONFIG_DIR,
    )
except ImportError:
    # If the file has a different name, adjust accordingly
    pytest.skip("Could not import api_key module", allow_module_level=True)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove API key env vars for clean test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield


@pytest.fixture
def mock_config_file(tmp_path, monkeypatch):
    """Mock CONFIG_FILE to use temp directory."""
    test_config_dir = tmp_path / ".axor"
    test_config_file = test_config_dir / "config.toml"
    
    monkeypatch.setattr("api_key.CONFIG_DIR", test_config_dir)
    monkeypatch.setattr("api_key.CONFIG_FILE", test_config_file)
    
    return test_config_file


class TestResolveApiKey:
    """Test resolve_api_key priority chain."""
    
    def test_cli_flag_highest_priority(self, clean_env, mock_config_file):
        """CLI flag should override everything."""
        flag_key = "flag-key-123"
        os.environ["ANTHROPIC_API_KEY"] = "env-key-456"
        
        result = resolve_api_key("claude", flag_key=flag_key)
        assert result == flag_key
    
    def test_env_var_second_priority(self, clean_env, mock_config_file):
        """Env var should be used if no CLI flag."""
        env_key = "env-key-789"
        os.environ["ANTHROPIC_API_KEY"] = env_key
        
        result = resolve_api_key("claude", flag_key=None)
        assert result == env_key
    
    def test_config_file_third_priority(self, clean_env, mock_config_file):
        """Config file should be used if no CLI flag or env var."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[claude]\napi_key = "config-key-abc"\n')
        
        result = resolve_api_key("claude", flag_key=None)
        assert result == "config-key-abc"
    
    def test_none_when_not_found(self, clean_env, mock_config_file):
        """Should return None when key not found anywhere."""
        result = resolve_api_key("claude", flag_key=None)
        assert result is None


class TestLoadFromConfig:
    """Test load_from_config."""
    
    def test_load_existing_key(self, mock_config_file):
        """Load key from existing config file."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[openai]\napi_key = "sk-test-123"\n')
        
        result = load_from_config("openai")
        assert result == "sk-test-123"
    
    def test_missing_file(self, mock_config_file):
        """Return None if config file doesn't exist."""
        result = load_from_config("claude")
        assert result is None
    
    def test_missing_adapter(self, mock_config_file):
        """Return None if adapter not in config."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[claude]\napi_key = "sk-ant-123"\n')
        
        result = load_from_config("openai")
        assert result is None


class TestSaveToConfig:
    """Test save_to_config."""
    
    def test_save_new_key(self, mock_config_file):
        """Save a new API key to config."""
        save_to_config("claude", "sk-ant-new-key")
        
        assert mock_config_file.exists()
        content = mock_config_file.read_text()
        assert "[claude]" in content
        assert 'api_key = "sk-ant-new-key"' in content
        
        # Check permissions (Unix-like systems)
        if hasattr(os, 'stat'):
            mode = mock_config_file.stat().st_mode & 0o777
            assert mode == 0o600
    
    def test_update_existing_key(self, mock_config_file):
        """Update an existing adapter's key."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[claude]\napi_key = "old-key"\n')
        
        save_to_config("claude", "new-key")
        
        content = mock_config_file.read_text()
        assert 'api_key = "new-key"' in content
        assert "old-key" not in content
    
    def test_preserve_other_adapters(self, mock_config_file):
        """Preserve other adapters when saving."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[openai]\napi_key = "sk-openai-123"\n')
        
        save_to_config("claude", "sk-ant-456")
        
        content = mock_config_file.read_text()
        assert "[openai]" in content
        assert "[claude]" in content
        assert "sk-openai-123" in content
        assert "sk-ant-456" in content


class TestClearFromConfig:
    """Test clear_from_config."""
    
    def test_clear_existing_key(self, mock_config_file):
        """Clear an existing adapter key."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[claude]\napi_key = "sk-ant-123"\n')
        
        result = clear_from_config("claude")
        assert result is True
        
        content = mock_config_file.read_text()
        assert "[claude]" not in content
    
    def test_clear_nonexistent_key(self, mock_config_file):
        """Return False when clearing non-existent key."""
        mock_config_file.parent.mkdir(parents=True, exist_ok=True)
        mock_config_file.write_text('[openai]\napi_key = "sk-123"\n')
        
        result = clear_from_config("claude")
        assert result is False


class TestPromptAndSave:
    """Test prompt_and_save interactive function."""
    
    @patch("builtins.input", return_value="y")
    @patch("getpass.getpass", return_value="sk-test-prompt")
    def test_prompt_and_save_yes(self, mock_getpass, mock_input, clean_env, mock_config_file):
        """Test prompting and saving with user saying yes."""
        result = prompt_and_save("claude")
        
        assert result == "sk-test-prompt"
        assert mock_config_file.exists()
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-test-prompt"
    
    @patch("builtins.input", return_value="n")
    @patch("getpass.getpass", return_value="sk-test-no-save")
    def test_prompt_no_save(self, mock_getpass, mock_input, clean_env, mock_config_file):
        """Test prompting without saving."""
        result = prompt_and_save("claude")
        
        assert result == "sk-test-no-save"
        assert not mock_config_file.exists()
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-test-no-save"
    
    @patch("getpass.getpass", return_value="")
    def test_prompt_empty_key(self, mock_getpass, clean_env):
        """Test prompting with empty key."""
        result = prompt_and_save("claude")
        assert result is None
    
    @patch("getpass.getpass", side_effect=KeyboardInterrupt)
    def test_prompt_cancelled(self, mock_getpass, clean_env):
        """Test cancelling the prompt."""
        result = prompt_and_save("claude")
        assert result is None
