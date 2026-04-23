from __future__ import annotations

"""
Raw Claude runner — direct Anthropic SDK, no governance.

This is the baseline for comparison.
Simulates what a developer would write without Axor:
  - full conversation history passed every turn
  - no context compression
  - no policy selection
  - no tool governance
  - full tool set always available (read, write, bash, search, glob)
  - naive tool execution loop — no intent mediation
"""

import os
import time
from dataclasses import dataclass
from typing import Any

_DEFAULT_SYSTEM_PROMPT = """You are an expert software engineer assistant.
You have access to tools to read, write, and execute code.
Use tools to complete the task. Be precise and efficient."""


@dataclass
class RawResult:
    task_name: str
    suite: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    latency_ms: float
    turns: int
    output: str
    tool_calls: int = 0
    error: str | None = None


# Full tool definitions — same schema as axor-claude,
# but ALL tools always present regardless of task nature.
# This is the honest baseline — no capability filtering.
_ALL_TOOLS = [
    {
        "name": "read",
        "description": "Read the contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-indexed).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (1-indexed).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write",
        "description": "Write content to a file atomically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write to."},
                "content": {
                    "type": "string",
                    "description": "Content to write.",
                },
                "mode": {"type": "string", "enum": ["write", "append"]},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a bash command. Returns stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
                "cwd": {"type": "string", "description": "Working directory."},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds. Default: 30.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "search",
        "description": "Search for a pattern in files using regex.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search.",
                },
                "glob": {
                    "type": "string",
                    "description": "File filter pattern. e.g. '*.py'",
                },
                "case_sensitive": {"type": "boolean"},
                "context_lines": {"type": "integer"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern. e.g. '**/*.py'",
                },
                "cwd": {
                    "type": "string",
                    "description": "Search root directory.",
                },
            },
            "required": ["pattern"],
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────
# Naive — no governance, no caching, no intent mediation.
# Every call goes through unconditionally.


def _execute_tool(name: str, args: dict[str, Any]) -> str:
    try:
        if name == "read":
            return _tool_read(args)
        if name == "write":
            return _tool_write(args)
        if name == "bash":
            return _tool_bash(args)
        if name == "search":
            return _tool_search(args)
        if name == "glob":
            return _tool_glob(args)
        return f"[unknown tool: {name}]"
    except Exception as e:
        return f"[tool error: {name}: {e}]"


def _tool_read(args: dict) -> str:
    path = args.get("path", "")
    if not path:
        return "[read: path required]"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(1024 * 1024)
        start = args.get("start_line")
        end = args.get("end_line")
        if start or end:
            lines = content.splitlines(keepends=True)
            s = (start - 1) if start else 0
            e = end if end else len(lines)
            content = "".join(lines[s:e])
        return content
    except FileNotFoundError:
        return f"[read: file not found: {path}]"


def _tool_write(args: dict) -> str:
    path = args.get("path", "")
    content = args.get("content", "")
    mode = args.get("mode", "write")
    if not path:
        return "[write: path required]"
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    open_mode = "a" if mode == "append" else "w"
    with open(path, open_mode, encoding="utf-8") as f:
        f.write(content)
    return f"wrote {len(content.encode())} bytes to {path}"


def _tool_bash(args: dict) -> str:
    import subprocess

    command = args.get("command", "")
    cwd = args.get("cwd", os.getcwd())
    timeout = float(args.get("timeout", 30))
    if not command:
        return "[bash: command required]"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        out = result.stdout
        if result.stderr:
            out += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            out += f"\n[exit code: {result.returncode}]"
        return out or f"[no output, exit code: {result.returncode}]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"


def _tool_search(args: dict) -> str:
    import glob as glob_mod
    import re

    pattern = args.get("pattern", "")
    path = args.get("path", os.getcwd())
    case_sensitive = args.get("case_sensitive", False)
    max_results = 100
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return f"[search: invalid pattern: {e}]"
    results = []
    search_root = path if os.path.isdir(path) else os.path.dirname(path)
    for fpath in glob_mod.glob(
        os.path.join(search_root, "**", "*"), recursive=True
    ):
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if compiled.search(line):
                        results.append(f"{fpath}:{i + 1}:{line.rstrip()}")
                        if len(results) >= max_results:
                            return (
                                "\n".join(results) + "\n[max results reached]"
                            )
        except OSError:
            continue
    return "\n".join(results) if results else "[no matches]"


def _tool_glob(args: dict) -> str:
    import glob as glob_mod

    pattern = args.get("pattern", "")
    cwd = args.get("cwd", os.getcwd())
    if not pattern:
        return "[glob: pattern required]"
    matches = glob_mod.glob(os.path.join(cwd, pattern), recursive=True)
    skip = {".git", "__pycache__", "node_modules", ".venv"}
    matches = [
        m for m in matches if not any(p in m.split(os.sep) for p in skip)
    ]
    return "\n".join(matches) if matches else "[no matches]"


# ── Runner ─────────────────────────────────────────────────────────────────────


class RawRunner:
    """
    Direct Anthropic API — no Axor governance.

    Full tool loop, all tools always available, full history every turn.
    Honest baseline: same tools as governed runner, no governance.
    """

    DEFAULT_MODEL = "claude-sonnet-4-5"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._model = model or self.DEFAULT_MODEL
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        except ImportError:
            raise ImportError("pip install anthropic")

    def _run_tool_loop(
        self,
        messages: list[dict],
        max_tool_rounds: int = 10,
    ) -> tuple[str, int, int, int]:
        """
        Run one Claude turn with full tool loop.
        Returns (final_text, total_input_tokens, total_output_tokens, tool_call_count).
        """
        total_input = 0
        total_output = 0
        tool_call_count = 0
        final_text = ""

        for _ in range(max_tool_rounds):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=messages,
                tools=_ALL_TOOLS,
                system=_DEFAULT_SYSTEM_PROMPT,
            )
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            text_parts = []
            tool_uses = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if text_parts:
                final_text = "".join(text_parts)

            # full assistant turn stays in history (text + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            if not tool_uses or response.stop_reason != "tool_use":
                break

            # execute all tools naively — no governance, no mediation, no caching
            tool_results = []
            for tu in tool_uses:
                tool_call_count += 1
                result = _execute_tool(tu.name, dict(tu.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result,
                    }
                )

            # tool results also accumulate in history — no compression
            messages.append({"role": "user", "content": tool_results})

        return final_text, total_input, total_output, tool_call_count

    def run_single(
        self,
        task_name: str,
        prompt: str,
        file_content: str | None = None,
        suite: str = "small",
    ) -> RawResult:
        messages = []
        if file_content:
            messages.append(
                {
                    "role": "user",
                    "content": f"Here is the code:\n\n```python\n{file_content}\n```\n\n{prompt}",
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        t0 = time.perf_counter()
        try:
            text, inp, out, calls = self._run_tool_loop(messages)
            elapsed = (time.perf_counter() - t0) * 1000
            return RawResult(
                task_name=task_name,
                suite=suite,
                total_tokens=inp + out,
                input_tokens=inp,
                output_tokens=out,
                latency_ms=elapsed,
                turns=1,
                output=text,
                tool_calls=calls,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return RawResult(
                task_name=task_name,
                suite=suite,
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed,
                turns=1,
                output="",
                error=str(e),
            )

    def run_conversation(
        self,
        task_name: str,
        turns: list[str],
        file_content: str | None = None,
        suite: str = "conversation",
    ) -> RawResult:
        """
        Multi-turn: full history (including all tool calls and results)
        accumulates naively. No compression at any point.
        """
        messages: list[dict] = []
        total_input = 0
        total_output = 0
        total_tool_calls = 0
        last_text = ""

        if file_content and turns:
            first = f"Here is the code:\n\n```python\n{file_content}\n```\n\n{turns[0]}"
            rest = list(turns[1:])
        else:
            first = turns[0] if turns else ""
            rest = list(turns[1:])

        all_turns = [first] + rest

        t0 = time.perf_counter()
        try:
            for turn_prompt in all_turns:
                messages.append({"role": "user", "content": turn_prompt})
                text, inp, out, calls = self._run_tool_loop(messages)
                total_input += inp
                total_output += out
                total_tool_calls += calls
                last_text = text

            elapsed = (time.perf_counter() - t0) * 1000
            return RawResult(
                task_name=task_name,
                suite=suite,
                total_tokens=total_input + total_output,
                input_tokens=total_input,
                output_tokens=total_output,
                latency_ms=elapsed,
                turns=len(all_turns),
                output=last_text,
                tool_calls=total_tool_calls,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return RawResult(
                task_name=task_name,
                suite=suite,
                total_tokens=total_input + total_output,
                input_tokens=total_input,
                output_tokens=total_output,
                latency_ms=elapsed,
                turns=len(all_turns),
                output=last_text,
                error=str(e),
            )
