# API Key Module Refactoring Summary

## Overview
Refactored `api_key.py` to improve readability, maintainability, and type safety while preserving the existing public interface.

## Key Improvements

### 1. **Enhanced Type Hints**
- Added `Final` type hints for constants to prevent accidental modification
- Added explicit return types to all functions
- Added parameter type hints where missing
- Used `dict[str, Any]` instead of generic dict

**Before:**
```python
CONFIG_DIR  = Path.home() / ".axor"
CONFIG_FILE = CONFIG_DIR / "config.toml"

_ENV_VARS = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}
```

**After:**
```python
CONFIG_DIR: Final[Path] = Path.home() / ".axor"
CONFIG_FILE: Final[Path] = CONFIG_DIR / "config.toml"

_ENV_VARS: Final[dict[str, str]] = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}
```

### 2. **Improved Code Organization**
- Moved all public functions to the top
- Grouped private helper functions at the bottom with clear section comment
- Consistent ordering: constants → public API → private helpers

### 3. **Better Separation of Concerns**
- Extracted TOML serialization logic into `_serialize_to_toml()`
- Split complex `prompt_and_save()` into smaller, focused functions:
  - `_print_prompt_header()` - Display prompt information
  - `_prompt_for_key()` - Get API key from user
  - `_prompt_to_save()` - Ask about saving to config
  - `_save_key_to_config()` - Save and display result
- Created `_load_existing_config()` to deduplicate config loading logic

### 4. **Enhanced Documentation**
- Added comprehensive docstrings to all functions (public and private)
- Included Args, Returns, and Raises sections where appropriate
- Added inline comments explaining non-obvious behavior
- Clarified the priority chain in `resolve_api_key()` docstring

### 5. **Improved Error Handling**
- Better tracking of file descriptors in `_write_config()`
- Explicit cleanup of temp files on error
- Clear separation between expected failures (return None) and exceptional failures (raise)

**Before:**
```python
def _write_config(data: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".axor_cfg_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        os.replace(tmp, CONFIG_FILE)
        CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

**After:**
```python
def _write_config(data: dict[str, Any]) -> None:
    toml_content = _serialize_to_toml(data)
    
    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".axor_cfg_")
        with os.fdopen(fd, "w") as f:
            f.write(toml_content)
        fd = -1  # Mark as closed
        
        os.replace(tmp_path, CONFIG_FILE)
        CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

### 6. **Named Constants**
- Introduced `_TOML_API_KEY_FIELD` constant for "api_key" field name
- Prevents typos and makes future changes easier

### 7. **Pathlib Consistency**
- Used `Path.open()` instead of mixing `open()` with Path objects
- More idiomatic pathlib usage throughout

**Before:**
```python
with open(CONFIG_FILE, "rb") as f:
    config = tomllib.load(f)
```

**After:**
```python
with CONFIG_FILE.open("rb") as f:
    config = tomllib.load(f)
```

### 8. **Quote Escaping in TOML**
- Added proper escaping for quotes in values to prevent TOML syntax errors
- More robust serialization

**Before:**
```python
lines.append(f'{key} = "{val}"')
```

**After:**
```python
escaped_val = str(val).replace('"', r'\"')
lines.append(f'{key} = "{escaped_val}"')
```

## Public Interface Preserved

All public functions maintain their exact signatures:
- `resolve_api_key(adapter: str, flag_key: str | None = None) -> str | None`
- `load_from_config(adapter: str) -> str | None`
- `save_to_config(adapter: str, api_key: str) -> None`
- `clear_from_config(adapter: str) -> bool`
- `prompt_and_save(adapter: str) -> str | None`

## Testing

All existing functionality verified:
- ✓ Module imports successfully
- ✓ Flag-based key resolution
- ✓ Environment variable resolution
- ✓ Config file save/load
- ✓ Key clearing

## Benefits

1. **Maintainability**: Smaller, focused functions are easier to understand and modify
2. **Testability**: Each helper function can be tested independently
3. **Type Safety**: Better IDE support and early error detection
4. **Readability**: Clear structure and comprehensive documentation
5. **Robustness**: Improved error handling and edge case coverage
