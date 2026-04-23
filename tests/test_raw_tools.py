"""Tests for benchmarks.raw — tool implementations (no API calls)."""
from __future__ import annotations

import os

import pytest

from benchmarks.raw import _execute_tool, _tool_read, _tool_write, _tool_bash, _tool_glob


# ── _tool_read ────────────────────────────────────────────────────────────────


def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")
    result = _tool_read({"path": str(f)})
    assert "line1" in result
    assert "line3" in result


def test_read_line_range(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\nline4\n")
    result = _tool_read({"path": str(f), "start_line": 2, "end_line": 3})
    assert "line2" in result
    assert "line3" in result
    assert "line1" not in result


def test_read_missing_file():
    result = _tool_read({"path": "/nonexistent/file.py"})
    assert "not found" in result


def test_read_no_path():
    result = _tool_read({})
    assert "required" in result


# ── _tool_write ───────────────────────────────────────────────────────────────


def test_write_creates_file(tmp_path):
    f = tmp_path / "out.txt"
    result = _tool_write({"path": str(f), "content": "hello"})
    assert "wrote" in result
    assert f.read_text() == "hello"


def test_write_append_mode(tmp_path):
    f = tmp_path / "out.txt"
    f.write_text("first")
    _tool_write({"path": str(f), "content": " second", "mode": "append"})
    assert f.read_text() == "first second"


def test_write_creates_dirs(tmp_path):
    f = tmp_path / "sub" / "dir" / "out.txt"
    _tool_write({"path": str(f), "content": "nested"})
    assert f.read_text() == "nested"


# ── _tool_bash ────────────────────────────────────────────────────────────────


def test_bash_echo():
    result = _tool_bash({"command": "echo hello"})
    assert "hello" in result


def test_bash_exit_code():
    result = _tool_bash({"command": "exit 42"})
    assert "exit code: 42" in result


def test_bash_timeout():
    result = _tool_bash({"command": "sleep 10", "timeout": 0.5})
    assert "timeout" in result.lower()


def test_bash_no_command():
    result = _tool_bash({})
    assert "required" in result


# ── _tool_glob ────────────────────────────────────────────────────────────────


def test_glob_finds_files(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("x")
    (tmp_path / "c.txt").write_text("x")
    result = _tool_glob({"pattern": "*.py", "cwd": str(tmp_path)})
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


def test_glob_no_match(tmp_path):
    result = _tool_glob({"pattern": "*.rs", "cwd": str(tmp_path)})
    assert "no matches" in result


# ── _execute_tool dispatch ────────────────────────────────────────────────────


def test_execute_tool_unknown():
    result = _execute_tool("unknown_tool", {})
    assert "unknown tool" in result


def test_execute_tool_exception(tmp_path):
    # read non-existent should return error, not crash
    result = _execute_tool("read", {"path": "/nonexistent"})
    assert "not found" in result
