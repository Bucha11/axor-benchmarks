from __future__ import annotations

"""
Governed runner — axor-core + axor-claude.

Uses GovernedSession with full governance stack:
  - dynamic policy selection
  - context compression
  - tool governance
  - budget tracking
  - federation for multi-agent tasks
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class GovernedResult:
    task_name: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    latency_ms: float
    turns: int
    output: str
    policy: str
    children: int = 0
    error: str | None = None


class GovernedRunner:
    """
    Runs tasks via axor-core GovernedSession + axor-claude.
    """

    def __init__(self, api_key: str) -> None:
        try:
            import axor_claude

            self._axor_claude = axor_claude
        except ImportError:
            raise ImportError("pip install axor-claude")
        self._api_key = api_key
        self._loop = asyncio.new_event_loop()
        from axor_core.policy.heuristic import HeuristicClassifier
        from axor_core.policy.selector import PolicySelector

        self._classifier = HeuristicClassifier()
        self._selector = PolicySelector()

    def close(self) -> None:
        if not self._loop.is_closed():
            self._loop.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _make_session(self, child_executor=None):
        import axor_claude
        from axor_core import CapabilityExecutor, GovernedSession
        from axor_core.contracts.trace import TraceConfig

        cap = CapabilityExecutor()
        cap.register(axor_claude.ReadHandler())
        cap.register(axor_claude.WriteHandler())
        cap.register(axor_claude.BashHandler())
        cap.register(axor_claude.SearchHandler())
        cap.register(axor_claude.GlobHandler())

        executor = axor_claude.ClaudeCodeExecutor(
            api_key=self._api_key, max_tokens=4096, max_retries=0
        )

        kwargs: dict[str, Any] = dict(
            executor=executor,
            capability_executor=cap,
            trace_config=TraceConfig(local_only=True, persist_inputs=False),
        )
        if child_executor is not None:
            kwargs["child_executor"] = child_executor

        return GovernedSession(**kwargs)

    async def _select_policy_from_prompt(self, prompt: str):
        signal, _confidence = await self._classifier.classify(prompt)
        return self._selector.select(signal)

    def run_single(
        self,
        task_name: str,
        prompt: str,
        file_content: str | None = None,
    ) -> GovernedResult:
        return self._run(self._run_single(task_name, prompt, file_content))

    async def _run_single(
        self,
        task_name: str,
        prompt: str,
        file_content: str | None,
    ) -> GovernedResult:
        session = self._make_session()
        policy = await self._select_policy_from_prompt(prompt)
        task = prompt
        if file_content:
            task = f"Here is the code:\n\n```python\n{file_content}\n```\n\n{prompt}"

        t0 = time.perf_counter()
        try:
            result = await session.run(task, policy=policy)
            elapsed = (time.perf_counter() - t0) * 1000
            return GovernedResult(
                task_name=task_name,
                total_tokens=result.token_usage.input_tokens
                + result.token_usage.output_tokens,
                input_tokens=result.token_usage.input_tokens,
                output_tokens=result.token_usage.output_tokens,
                latency_ms=elapsed,
                turns=1,
                output=result.output,
                policy=result.metadata.get("policy", "unknown"),
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return GovernedResult(
                task_name=task_name,
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed,
                turns=1,
                output="",
                policy="error",
                error=str(e),
            )

    def run_conversation(
        self,
        task_name: str,
        turns: list[str],
        file_content: str | None = None,
    ) -> GovernedResult:
        return self._run(self._run_conversation(task_name, turns, file_content))

    async def _run_conversation(
        self,
        task_name: str,
        turns: list[str],
        file_content: str | None,
    ) -> GovernedResult:
        session = self._make_session()
        policy = await self._select_policy_from_prompt(
            turns[0] if turns else ""
        )
        last_output = ""
        last_policy = "unknown"

        if file_content and turns:
            first = f"Here is the code:\n\n```python\n{file_content}\n```\n\n{turns[0]}"
            rest = list(turns[1:])
        else:
            first = turns[0] if turns else ""
            rest = list(turns[1:])

        all_turns = [first] + rest

        t0 = time.perf_counter()
        try:
            for turn in all_turns:
                result = await session.run(turn, policy=policy)
                last_output = result.output
                last_policy = result.metadata.get("policy", "unknown")

            elapsed = (time.perf_counter() - t0) * 1000
            total = session.total_tokens_spent()

            return GovernedResult(
                task_name=task_name,
                total_tokens=total,
                input_tokens=total,  # session-level tracking
                output_tokens=0,
                latency_ms=elapsed,
                turns=len(all_turns),
                output=last_output,
                policy=last_policy,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return GovernedResult(
                task_name=task_name,
                total_tokens=session.total_tokens_spent(),
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed,
                turns=len(all_turns),
                output="",
                policy="error",
                error=str(e),
            )

    def run_federation(
        self,
        task_name: str,
        prompt: str,
        child_tasks: list[str],
        file_content: str | None = None,
    ) -> GovernedResult:
        return self._run(
            self._run_federation(task_name, prompt, child_tasks, file_content)
        )

    async def _run_federation(
        self,
        task_name: str,
        prompt: str,
        child_tasks: list[str],
        file_content: str | None,
    ) -> GovernedResult:
        import axor_claude
        from axor_core import presets

        # child executor — plain Claude, no spawning
        child_exec = axor_claude.ClaudeCodeExecutor(api_key=self._api_key)
        session = self._make_session(child_executor=child_exec)

        task = prompt
        if file_content:
            task = f"Here is the code:\n\n```python\n{file_content}\n```\n\n{prompt}"

        t0 = time.perf_counter()
        try:
            result = await session.run(task, policy=presets.get("federated"))
            elapsed = (time.perf_counter() - t0) * 1000

            # count child events in trace
            traces = session.all_traces()
            all_events = [e for t in traces for e in t.events]
            children = sum(
                1 for e in all_events if e.kind.value == "child_spawned"
            )

            return GovernedResult(
                task_name=task_name,
                total_tokens=session.total_tokens_spent(),
                input_tokens=result.token_usage.input_tokens,
                output_tokens=result.token_usage.output_tokens,
                latency_ms=elapsed,
                turns=1,
                output=result.output,
                policy=result.metadata.get("policy", "federated"),
                children=children,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return GovernedResult(
                task_name=task_name,
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed,
                turns=1,
                output="",
                policy="error",
                error=str(e),
            )
