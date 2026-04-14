# Test Coverage Improvement Recommendations

## Current Coverage Analysis

After analyzing `test_api_key_simple.py` against the `api_key.py` implementation, here are the gaps and recommendations:

---

## 🔴 Critical Missing Tests

### 1. **Error Handling & Edge Cases**

#### `load_from_config` - Corrupted TOML Files
**Gap**: Code silently catches exceptions for corrupted config files, but this isn't tested.
```python
def test_load_corrupted_toml(self, temp_config):
    """Gracefully handle corrupted TOML files."""
    temp_config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_config.CONFIG_FILE.write_text("[[[[invalid toml")
    
    result = temp_config.load_from_config("claude")
    assert result is None  # Should fail gracefully
```

#### `load_from_config` - Missing `tomllib` Module
**Gap**: Code has fallback when `tomllib` is unavailable but not tested.
```python
def test_load_without_tomllib(self, temp_config):
    """Returns None when tomllib is not available."""
    temp_config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_config.CONFIG_FILE.write_text('[claude]\napi_key = "sk-test"')
    
    original_tomllib = temp_config.tomllib
    with patch.object(temp_config, 'tomllib', None):
        result = temp_config.load_from_config("claude")
        assert result is None
```

#### `save_to_config` - Write Failures
**Gap**: Code raises exceptions on write failure, but not tested.
```python
def test_save_to_readonly_directory(self, temp_config):
    """Raises exception when directory is read-only."""
    import stat
    temp_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Make directory read-only
    original_mode = temp_config.CONFIG_DIR.stat().st_mode
    temp_config.CONFIG_DIR.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x
    
    try:
        with pytest.raises(Exception):
            temp_config.save_to_config("claude", "sk-test")
    finally:
        temp_config.CONFIG_DIR.chmod(original_mode)
```

#### `_write_config` - Atomic Write Cleanup
**Gap**: Temporary file cleanup on failure isn't tested.
```python
def test_save_atomic_write_failure_cleanup(self, temp_config):
    """Cleans up temp file if atomic write fails."""
    temp_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    with patch('os.replace', side_effect=OSError("Simulated failure")):
        with pytest.raises(Exception):
            temp_config.save_to_config("claude", "sk-test")
    
    # Verify no temp files left behind
    temp_files = list(temp_config.CONFIG_DIR.glob(".axor_cfg_*"))
    assert len(temp_files) == 0
```

---

### 2. **Environment Variable Interactions**

#### `resolve_api_key` - Setting Env Var from Config
**Gap**: Code sets environment variable when loading from config, but not verified.
```python
def test_config_sets_environment_variable(self, temp_config):
    """Loading from config sets environment variable."""
    import os
    temp_config.save_to_config("claude", "config-key")
    
    with patch.dict(os.environ, {}, clear=True):
        result = temp_config.resolve_api_key("claude")
        assert result == "config-key"
        assert os.environ.get("ANTHROPIC_API_KEY") == "config-key"
```

#### Unknown Adapter Names
**Gap**: What happens with adapters not in `_ENV_VARS`?
```python
def test_resolve_unknown_adapter(self, temp_config):
    """Unknown adapter doesn't crash but may not set env var."""
    temp_config.save_to_config("unknown_adapter", "test-key")
    
    with patch.dict(os.environ, {}, clear=True):
        result = temp_config.resolve_api_key("unknown_adapter")
        assert result == "test-key"
        # Unknown adapter shouldn't set env var (no mapping exists)
```

---

### 3. **Prompt Flow Edge Cases**

#### `prompt_and_save` - EOFError Handling
**Gap**: Code catches `EOFError`, but only `KeyboardInterrupt` is tested.
```python
@patch('getpass.getpass', side_effect=EOFError)
def test_prompt_eof_error(self, mock_getpass, temp_config):
    """User triggers EOF (Ctrl+D) during prompt."""
    result = temp_config.prompt_and_save("claude")
    assert result is None
```

#### `prompt_and_save` - Save Error During Prompt
**Gap**: What if save fails after user confirms?
```python
@patch('getpass.getpass', return_value="sk-test-key")
@patch('builtins.input', return_value="y")
def test_prompt_save_fails_gracefully(self, mock_input, mock_getpass, temp_config):
    """Save failure is caught and reported to user."""
    with patch.object(temp_config, 'save_to_config', side_effect=Exception("Disk full")):
        result = temp_config.prompt_and_save("claude")
        # Should still return the key even if save failed
        assert result == "sk-test-key"
```

#### `_prompt_to_save` - Different Response Values
**Gap**: Only "y" and "n" tested. What about "yes", "YES", "" (default)?
```python
@pytest.mark.parametrize("response,expected_save", [
    ("", True),      # Default is yes
    ("y", True),
    ("Y", True),
    ("yes", True),
    ("YES", True),
    ("n", False),
    ("N", False),
    ("no", False),
    ("NO", False),
    ("maybe", False),  # Anything else is no
])
@patch('getpass.getpass', return_value="sk-test")
def test_prompt_save_responses(self, mock_getpass, response, expected_save, temp_config):
    """Test various user responses to save prompt."""
    with patch('builtins.input', return_value=response):
        temp_config.prompt_and_save("claude")
        
        saved_key = temp_config.load_from_config("claude")
        if expected_save:
            assert saved_key == "sk-test"
        else:
            assert saved_key is None
```

#### `_prompt_to_save` - EOFError on Save Prompt
**Gap**: User might Ctrl+D at the save prompt.
```python
@patch('getpass.getpass', return_value="sk-test-key")
@patch('builtins.input', side_effect=EOFError)
def test_prompt_save_eof(self, mock_input, mock_getpass, temp_config):
    """User triggers EOF during save prompt."""
    result = temp_config.prompt_and_save("claude")
    assert result == "sk-test-key"  # Key still returned
    assert temp_config.load_from_config("claude") is None  # Not saved
```

---

### 4. **TOML Serialization Edge Cases**

#### `_serialize_to_toml` - Special Characters in Values
**Gap**: Values with quotes need escaping.
```python
def test_save_key_with_quotes(self, temp_config):
    """Keys containing quotes are properly escaped."""
    api_key_with_quotes = 'sk-test"with"quotes'
    temp_config.save_to_config("claude", api_key_with_quotes)
    
    result = temp_config.load_from_config("claude")
    assert result == api_key_with_quotes
```

#### Empty String Keys
**Gap**: What happens with empty API keys?
```python
def test_save_empty_string_key(self, temp_config):
    """Empty string keys are saved (though not useful)."""
    temp_config.save_to_config("claude", "")
    result = temp_config.load_from_config("claude")
    assert result == ""
```

---

### 5. **Config File Atomicity**

#### Concurrent Writes
**Gap**: Atomic writes should handle race conditions.
```python
def test_concurrent_save_operations(self, temp_config):
    """Multiple saves don't corrupt the file."""
    import threading
    
    def save_key(adapter, key):
        temp_config.save_to_config(adapter, key)
    
    threads = [
        threading.Thread(target=save_key, args=("claude", f"key-{i}"))
        for i in range(10)
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # File should exist and be parseable
    result = temp_config.load_from_config("claude")
    assert result is not None
    assert result.startswith("key-")
```

---

## 🟡 Medium Priority Tests

### 6. **Different Adapter Support**

#### OpenAI Adapter Tests
**Gap**: Only Claude is thoroughly tested.
```python
def test_openai_adapter_full_flow(self, temp_config):
    """Complete flow works for OpenAI adapter."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-test"}):
        result = temp_config.resolve_api_key("openai")
        assert result == "sk-openai-test"
```

---

### 7. **File System States**

#### Missing Parent Directories
**Gap**: `save_to_config` creates parent dirs - verify this works.
```python
def test_save_creates_parent_directories(self, temp_config, monkeypatch):
    """Save creates ~/.axor directory if it doesn't exist."""
    # Ensure directory doesn't exist
    if temp_config.CONFIG_DIR.exists():
        shutil.rmtree(temp_config.CONFIG_DIR)
    
    temp_config.save_to_config("claude", "sk-test")
    
    assert temp_config.CONFIG_DIR.exists()
    assert temp_config.CONFIG_FILE.exists()
```

---

### 8. **Output and User Communication**

#### Verify Print Messages
**Gap**: User-facing messages aren't verified.
```python
@patch('getpass.getpass', return_value="sk-test")
@patch('builtins.input', return_value="y")
def test_prompt_success_message(self, mock_input, mock_getpass, temp_config, capsys):
    """Success message shown when key is saved."""
    temp_config.prompt_and_save("claude")
    
    captured = capsys.readouterr()
    assert "✓ Key saved to" in captured.out
    assert "permissions: 600" in captured.out
```

```python
@patch('getpass.getpass', return_value="sk-test")
@patch('builtins.input', return_value="n")
def test_prompt_session_only_message(self, mock_input, mock_getpass, temp_config, capsys):
    """Session-only message shown when not saving."""
    temp_config.prompt_and_save("claude")
    
    captured = capsys.readouterr()
    assert "valid for this session only" in captured.out
```

---

## 🟢 Nice-to-Have Tests

### 9. **Integration Tests**

```python
def test_full_workflow_new_user(self, temp_config):
    """Simulate complete new user experience."""
    # 1. No key exists anywhere
    with patch.dict(os.environ, {}, clear=True):
        result = temp_config.resolve_api_key("claude")
        assert result is None
    
    # 2. Save a key
    temp_config.save_to_config("claude", "sk-ant-test")
    
    # 3. Key is now found
    with patch.dict(os.environ, {}, clear=True):
        result = temp_config.resolve_api_key("claude")
        assert result == "sk-ant-test"
    
    # 4. Clear the key
    assert temp_config.clear_from_config("claude") is True
    
    # 5. Key is gone
    with patch.dict(os.environ, {}, clear=True):
        result = temp_config.resolve_api_key("claude")
        assert result is None
```

---

## 📊 Summary of Gaps

| Category | Current Tests | Missing Tests | Priority |
|----------|--------------|---------------|----------|
| Error handling | 0 | 5 | 🔴 Critical |
| Environment variables | 2 | 2 | 🔴 Critical |
| Prompt edge cases | 2 | 5 | 🔴 Critical |
| TOML serialization | 0 | 2 | 🔴 Critical |
| Atomicity | 0 | 1 | 🔴 Critical |
| Multi-adapter support | 1 | 2 | 🟡 Medium |
| File system states | 0 | 1 | 🟡 Medium |
| User messages | 0 | 2 | 🟢 Nice-to-have |
| Integration tests | 0 | 1 | 🟢 Nice-to-have |

**Total Test Gap: ~21 additional test cases needed for comprehensive coverage**

---

## 🎯 Recommended Implementation Order

1. **Phase 1 (Critical)**: Error handling tests (corrupted TOML, missing tomllib, write failures)
2. **Phase 2 (Critical)**: Environment variable setting from config
3. **Phase 3 (Critical)**: Prompt flow edge cases (EOF, different responses)
4. **Phase 4 (Medium)**: TOML serialization edge cases
5. **Phase 5 (Nice-to-have)**: User message verification and integration tests

---

## 🔧 Additional Testing Infrastructure Improvements

### Add Coverage Reporting
```bash
pytest --cov=api_key --cov-report=html --cov-report=term-missing
```

### Add Property-Based Testing
Use `hypothesis` for testing with random inputs:
```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_save_arbitrary_keys(self, temp_config, api_key_value):
    """Any non-empty string can be saved and retrieved."""
    temp_config.save_to_config("claude", api_key_value)
    result = temp_config.load_from_config("claude")
    assert result == api_key_value
```

### Add Performance Tests
```python
def test_save_performance(self, temp_config):
    """Saving should be reasonably fast."""
    import time
    
    start = time.time()
    for i in range(100):
        temp_config.save_to_config("claude", f"sk-test-{i}")
    duration = time.time() - start
    
    assert duration < 1.0  # Should complete in under 1 second
```
