from __future__ import annotations

from pathlib import Path

import api_key as _impl

CONFIG_DIR = _impl.CONFIG_DIR
CONFIG_FILE = _impl.CONFIG_FILE
tomllib = _impl.tomllib


def _sync() -> None:
	_impl.CONFIG_DIR = Path(CONFIG_DIR)
	_impl.CONFIG_FILE = Path(CONFIG_FILE)
	_impl.tomllib = tomllib


def resolve_api_key(adapter: str, flag_key: str | None = None) -> str | None:
	_sync()
	return _impl.resolve_api_key(adapter, flag_key)


def load_from_config(adapter: str) -> str | None:
	_sync()
	return _impl.load_from_config(adapter)


def save_to_config(adapter: str, api_key: str) -> None:
	_sync()
	_impl.save_to_config(adapter, api_key)


def clear_from_config(adapter: str) -> bool:
	_sync()
	return _impl.clear_from_config(adapter)


def prompt_and_save(adapter: str) -> str | None:
	_sync()
	return _impl.prompt_and_save(adapter)