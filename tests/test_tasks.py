"""Tests for benchmarks.tasks — task definitions and file selection."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmarks.tasks import (
    BenchTask,
    SMALL_TASKS,
    LARGE_TASKS,
    CONVERSATION_TASKS,
    FEDERATION_TASKS,
    get_suite,
    find_target_file,
    _is_suitable,
)


# ── Task definitions ──────────────────────────────────────────────────────────


def test_all_tasks_have_suite():
    for task in SMALL_TASKS + LARGE_TASKS + CONVERSATION_TASKS + FEDERATION_TASKS:
        assert task.suite, f"task {task.name} has no suite"


def test_small_tasks_have_prompts():
    for task in SMALL_TASKS:
        assert task.prompt, f"small task {task.name} has no prompt"
        assert task.needs_file is True, f"small task {task.name} should need file"


def test_conversation_tasks_have_turns():
    for task in CONVERSATION_TASKS:
        assert len(task.turns) >= 5, f"conversation task {task.name} needs more turns"


def test_federation_tasks_have_child_tasks():
    for task in FEDERATION_TASKS:
        assert len(task.child_tasks) >= 2, f"federation task {task.name} needs child tasks"


# ── get_suite ─────────────────────────────────────────────────────────────────


def test_get_suite_small():
    tasks = get_suite("small")
    assert len(tasks) == len(SMALL_TASKS)
    assert all(t.suite == "small" for t in tasks)


def test_get_suite_full():
    tasks = get_suite("full")
    assert len(tasks) == len(SMALL_TASKS) + len(LARGE_TASKS) + len(CONVERSATION_TASKS) + len(FEDERATION_TASKS)


def test_get_suite_quick():
    tasks = get_suite("quick")
    assert len(tasks) == 1


def test_get_suite_unknown_raises():
    with pytest.raises(ValueError, match="Unknown suite"):
        get_suite("nonexistent")


# ── find_target_file ──────────────────────────────────────────────────────────


def test_find_target_file_in_repo(tmp_path):
    # create a suitable file
    src = tmp_path / "src"
    src.mkdir()
    auth = src / "auth.py"
    auth.write_text("# auth module\n" + "def login(): pass\n" * 50)

    found = find_target_file(tmp_path)
    assert found is not None
    assert found.name == "auth.py"


def test_find_target_file_skips_tests(tmp_path):
    test_file = tmp_path / "test_something.py"
    test_file.write_text("def test_foo(): pass\n" * 50)

    found = find_target_file(tmp_path)
    assert found is None  # only test file, nothing suitable


def test_find_target_file_empty_dir(tmp_path):
    found = find_target_file(tmp_path)
    assert found is None


# ── _is_suitable ──────────────────────────────────────────────────────────────


def test_is_suitable_normal_file(tmp_path):
    f = tmp_path / "module.py"
    f.write_text("x = 1\n" * 100)  # ~600 bytes
    assert _is_suitable(f) is True


def test_is_suitable_too_small(tmp_path):
    f = tmp_path / "tiny.py"
    f.write_text("x = 1")  # < 500 bytes
    assert _is_suitable(f) is False


def test_is_suitable_test_file(tmp_path):
    f = tmp_path / "test_foo.py"
    f.write_text("x = 1\n" * 100)
    assert _is_suitable(f) is False


def test_is_suitable_hidden_dir(tmp_path):
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    f = hidden / "module.py"
    f.write_text("x = 1\n" * 100)
    assert _is_suitable(f) is False
