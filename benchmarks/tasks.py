from __future__ import annotations

"""
Benchmark task definitions.

Each task is a dict with:
    name:        display name
    prompt:      what we ask Claude to do
    needs_file:  whether task uses a file from the repo as context
    suite:       which suite this belongs to (small/large/conversation/federation)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchTask:
    name:        str
    suite:       str
    prompt:      str = ""
    needs_file:  bool = False
    turns:       list[str] = field(default_factory=list)
    child_tasks: list[str] = field(default_factory=list)


# ── Small tasks ────────────────────────────────────────────────────────────────
# Quick, focused, single-turn. Measures basic token overhead.

SMALL_TASKS = [
    BenchTask(
        name="write_test",
        suite="small",
        needs_file=True,
        prompt="Write a concise unit test for the main function in this file. Use pytest.",
    ),
    BenchTask(
        name="explain_function",
        suite="small",
        needs_file=True,
        prompt="Explain what this code does in 3-4 sentences. Be concise.",
    ),
    BenchTask(
        name="find_bugs",
        suite="small",
        needs_file=True,
        prompt="List any potential bugs or issues in this code. Be brief.",
    ),
]

# ── Large tasks ────────────────────────────────────────────────────────────────
# Multi-tool, multi-step. Measures context management under load.

LARGE_TASKS = [
    BenchTask(
        name="refactor_module",
        suite="large",
        needs_file=True,
        prompt=(
            "Refactor this module to improve readability and maintainability. "
            "Add type hints where missing. Keep the same public interface. "
            "Read the file first, then make targeted improvements."
        ),
    ),
    BenchTask(
        name="add_error_handling",
        suite="large",
        needs_file=True,
        prompt=(
            "Add comprehensive error handling to this module. "
            "Use specific exception types, add meaningful error messages. "
            "Read the file first, then apply changes systematically."
        ),
    ),
]

# ── Conversation tasks ─────────────────────────────────────────────────────────
# Multi-turn. Measures context growth and compression over time.

CONVERSATION_TASKS = [
    BenchTask(
        name="iterative_review",
        suite="conversation",
        needs_file=True,
        turns=[
            "Read this file and give me a brief overview of what it does.",
            "What are the main functions or classes? List them.",
            "Which part is most complex? Why?",
            "How would you improve the test coverage?",
            "What dependencies does this module have?",
            "Are there any performance concerns?",
            "How would you refactor the most complex part?",
            "What documentation is missing?",
            "Suggest a better name for the main function/class if applicable.",
            "Summarize all your findings in 5 bullet points.",
        ],
    ),
]

# ── Federation tasks ───────────────────────────────────────────────────────────
# Tests child spawning, context isolation, lineage.

FEDERATION_TASKS = [
    BenchTask(
        name="parallel_analysis",
        suite="federation",
        needs_file=False,
        prompt=(
            "Analyze the codebase structure. "
            "For each major concern (security, performance, maintainability), "
            "spawn a child agent to analyze that specific aspect independently, "
            "then synthesize the findings into a final report."
        ),
        child_tasks=[
            "Analyze security: look for common vulnerabilities, hardcoded secrets, injection risks.",
            "Analyze performance: look for inefficient loops, unnecessary I/O, memory issues.",
            "Analyze maintainability: look for code duplication, missing docs, complex functions.",
        ],
    ),
]


def get_suite(suite: str) -> list[BenchTask]:
    """Get all tasks for a given suite name."""
    suites = {
        "small":        SMALL_TASKS,
        "large":        LARGE_TASKS,
        "conversation": CONVERSATION_TASKS,
        "federation":   FEDERATION_TASKS,
        "full":         SMALL_TASKS + LARGE_TASKS + CONVERSATION_TASKS + FEDERATION_TASKS,
        "quick":        SMALL_TASKS[:1],   # just one small task for testing
    }
    tasks = suites.get(suite)
    if tasks is None:
        available = ", ".join(suites.keys())
        raise ValueError(f"Unknown suite '{suite}'. Available: {available}")
    return tasks


def find_target_file(repo_path: Path) -> Path | None:
    """
    Find a suitable Python file in the repo to use as benchmark context.
    Prefers files that are meaningful but not too large.
    """
    candidates = []

    # look for well-named files first
    priority_names = [
        "auth.py", "authentication.py", "models.py", "views.py",
        "api.py", "routes.py", "utils.py", "core.py", "main.py",
        "app.py", "service.py", "handlers.py",
    ]

    for name in priority_names:
        for match in repo_path.rglob(name):
            if _is_suitable(match):
                return match

    # fallback: any Python file of reasonable size
    for py_file in sorted(repo_path.rglob("*.py")):
        if _is_suitable(py_file):
            candidates.append(py_file)

    if candidates:
        # prefer files with moderate size (not too small, not too large)
        def score(p: Path) -> int:
            size = p.stat().st_size
            return abs(size - 3000)   # closest to 3KB

        return sorted(candidates, key=score)[0]

    return None


def _is_suitable(path: Path) -> bool:
    """Check if a file is suitable as benchmark context."""
    # skip test files, migrations, generated code
    skip_patterns = ["test_", "_test", "migration", "generated", "__pycache__",
                     "setup.py", "conf.py", "conftest"]
    name = path.name
    if any(p in name for p in skip_patterns):
        return False

    # skip hidden dirs
    if any(part.startswith(".") for part in path.parts):
        return False

    # must be readable and reasonable size (500B – 50KB)
    try:
        size = path.stat().st_size
        return 500 <= size <= 50_000
    except OSError:
        return False
