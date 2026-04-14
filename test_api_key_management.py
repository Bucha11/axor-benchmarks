"""Unit tests for API key management."""
import os
import stat
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
import tempfile
import pytest


# Mock tomllib for testing
class MockTomllib:
    @staticmethod
    def load(f):
        content = f.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        # Simple TOML parser for our test cases
        result = {}
        current_section = None
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                result[current_section] = {}
            elif '=' in line and current_section:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                result[current_section][key] = val
        return result


@pytest.fixture
def mock_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".axor"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def clean_env():
    """Clean environment variables before and after tests."""
    original_env = os.environ.copy()
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        os.environ.pop(key, None)
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def api_key_module(mock_config_dir):
    """Import module with mocked paths and tomllib."""
    import sys
    
    # Create mock module
    with patch('pathlib.Path.home', return_value=mock_config_dir.parent):
        # Mock tomllib import
        mock_tomllib = MockTomllib()
        sys.modules['tomllib'] = mock_tomllib
        
        # Import after mocking
        import importlib.util
        spec = importlib.util.spec_from_file_location("api_key_mgmt", "api_key_management.py")
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Override paths
            module.CONFIG_DIR = mock_config_dir
            module.CONFIG_FILE = mock_config_dir / "config.toml"
            module.tomllib = mock_tomllib
            
            return module
    
    return None


class TestResolveApiKey:
    """Test resolve_api_key function."""
    
    def test_priority_1_flag_key(self, api_key_module, clean_env):
        """CLI flag has highest priority."""
        result = api_key_module.resolve_api_key("claude", flag_key="flag-key-123")
        assert result == "flag-key-123"
    
    def test_priority_2_env_var(self, api_key_module, clean_env):
        """Environment variable is second priority."""
        os.environ["ANTHROPIC_API_KEY"] = "env-key-456"
        result = api_key_module.resolve_api_key("claude", flag_key=None)
        assert result == "env-key-456"
    
    def test_priority_3_config_file(self, api_key_module, clean_env):
        """Config file is third priority."""
        # Create config file
        config_file = api_key_module.CONFIG_FILE
        config_file.write_text('[claude]\napi_key = "config-key-789"\n')
        
        result = api_key_module.resolve_api_key("claude", flag_key=None)
        assert result == "config-key-789"
        # Should also set env var
        assert os.environ.get("ANTHROPIC_API_KEY") == "config-key-789"
    
    def test_flag_overrides_env(self, api_key_module, clean_env):
        """CLI flag overrides environment variable."""
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        result = api_key_module.resolve_api_key("claude", flag_key="flag-key")
        assert result == "flag-key"
    
    def test_env_overrides_config(self, api_key_module, clean_env):
        """Environment variable overrides config file."""
        config_file = api_key_module.CONFIG_FILE
        config_file.write_text('[claude]\napi_key = "config-key"\n')
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        
        result = api_key_module.resolve_api_key("claude", flag_key=None)
        assert result == "env-key"
    
    def test_no_key_found(self, api_key_module, clean_env):
        """Returns None when no key is found."""
        result = api_key_module.resolve_api_key("claude", flag_key=None)
        assert result is None
    
    def test_openai_adapter(self, api_key_module, clean_env):
        """Test with OpenAI adapter."""
        os.environ["OPENAI_API_KEY"] = "openai-key-123"
        result = api_key_module.resolve_api_key("openai", flag_key=None)
        assert result == "openai-key-123"


class TestLoadFromConfig:
    """Test load_from_config function."""
    
    def test_load_existing_key(self, api_key_module):
        """Load key from existing config file."""
        config_file = api_key_module.CONFIG_FILE
        config_file.write_text('[claude]\napi_key = "sk-ant-test123"\n')
        
        result = api_key_module.load_from_config("claude")
        assert result == "sk-ant-test123"
    
    def test_load_nonexistent_adapter(self, api_key_module):
        """Returns None for adapter not in config."""
        config_file = api_key_module.CONFIG_FILE
        config_file.write_text('[claude]\napi_key = "sk-ant-test123"\n')
        
        result = api_key_module.load_from_config("openai")
        assert result is None
    
    def test_load_missing_file(self, api_key_module):
        """Returns None when config file doesn't exist."""
        result = api_key_module.load_from_config("claude")
        assert result is None
    
    def test_load_with_no_tomllib(self, api_key_module):
        """Returns None when tomllib is not available."""
        config_file = api_key_module.CONFIG_FILE
        config_file.write_text('[claude]\napi_key = "sk-ant-test123"\n')
        
        original_tomllib = api_key_module.tomllib
        api_key_module.tomllib = None
        
        result = api_key_module.load_from_config("claude")
        assert result is None
        
        api_key_module.tomllib = original_tomllib


class TestSaveToConfig:
    """Test save_to_config function."""
    
    def test_save_new_key(self, api_key_module):
        """Save a new API key to config."""
        api_key_module.save_to_config("claude", "sk-ant-new123")
        
        config_file = api_key_module.CONFIG_FILE
        assert config_file.exists()
        
        # Check content
        content = config_file.read_text()
        assert "[claude]" in content
        assert 'api_key = "sk-ant-new123"' in content
        
        # Check permissions
        file_stat = config_file.stat()
        assert file_stat.st_mode & 0o777 == 0o600
    
    def test_save_overwrites_existing(self, api_key_module):
        """Save overwrites existing key for same adapter."""
        api_key_module.save_to_config("claude", "old-key")
        api_key_module.save_to_config("claude", "new-key")
        
        result = api_key_module.load_from_config("claude")
        assert result == "new-key"
    
    def test_save_preserves_other_adapters(self, api_key_module):
        """Save preserves keys for other adapters."""
        api_key_module.save_to_config("claude", "claude-key")
        api_key_module.save_to_config("openai", "openai-key")
        
        assert api_key_module.load_from_config("claude") == "claude-key"
        assert api_key_module.load_from_config("openai") == "openai-key"


class TestClearFromConfig:
    """Test clear_from_config function."""
    
    def test_clear_existing_key(self, api_key_module):
        """Clear an existing key returns True."""
        api_key_module.save_to_config("claude", "sk-ant-test123")
        
        result = api_key_module.clear_from_config("claude")
        assert result is True
        
        # Key should be gone
        assert api_key_module.load_from_config("claude") is None
    
    def test_clear_nonexistent_key(self, api_key_module):
        """Clear nonexistent key returns False."""
        result = api_key_module.clear_from_config("claude")
        assert result is False
    
    def test_clear_missing_file(self, api_key_module):
        """Clear from missing file returns False."""
        result = api_key_module.clear_from_config("claude")
        assert result is False
    
    def test_clear_preserves_other_adapters(self, api_key_module):
        """Clear preserves other adapter keys."""
        api_key_module.save_to_config("claude", "claude-key")
        api_key_module.save_to_config("openai", "openai-key")
        
        api_key_module.clear_from_config("claude")
        
        assert api_key_module.load_from_config("claude") is None
        assert api_key_module.load_from_config("openai") == "openai-key"


class TestPromptAndSave:
    """Test prompt_and_save function."""
    
    def test_prompt_and_save_yes(self, api_key_module, clean_env):
        """Prompt user and save key when user says yes."""
        with patch('getpass.getpass', return_value='sk-ant-prompted'), \
             patch('builtins.input', return_value='y'), \
             patch('builtins.print'):
            
            result = api_key_module.prompt_and_save("claude")
            
            assert result == "sk-ant-prompted"
            assert api_key_module.load_from_config("claude") == "sk-ant-prompted"
            assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-prompted"
    
    def test_prompt_and_save_no(self, api_key_module, clean_env):
        """Prompt user but don't save when user says no."""
        with patch('getpass.getpass', return_value='sk-ant-prompted'), \
             patch('builtins.input', return_value='n'), \
             patch('builtins.print'):
            
            result = api_key_module.prompt_and_save("claude")
            
            assert result == "sk-ant-prompted"
            assert api_key_module.load_from_config("claude") is None
            assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-prompted"
    
    def test_prompt_cancelled(self, api_key_module):
        """Returns None when user cancels prompt."""
        with patch('getpass.getpass', side_effect=KeyboardInterrupt), \
             patch('builtins.print'):
            
            result = api_key_module.prompt_and_save("claude")
            assert result is None
    
    def test_prompt_empty_key(self, api_key_module):
        """Returns None when user enters empty key."""
        with patch('getpass.getpass', return_value=''), \
             patch('builtins.print'):
            
            result = api_key_module.prompt_and_save("claude")
            assert result is None
    
    def test_prompt_save_cancelled(self, api_key_module, clean_env):
        """User cancels save prompt but key still returned."""
        with patch('getpass.getpass', return_value='sk-ant-test'), \
             patch('builtins.input', side_effect=KeyboardInterrupt), \
             patch('builtins.print'):
            
            result = api_key_module.prompt_and_save("claude")
            
            assert result == "sk-ant-test"
            assert api_key_module.load_from_config("claude") is None
