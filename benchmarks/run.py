from __future__ import annotations

"""
axor-bench — benchmark governed vs raw Claude on your codebase.

Usage:
    axor-bench                         # runs in current directory, quick suite
    axor-bench --suite full            # all suites
    axor-bench --suite small           # just small tasks
    axor-bench --repo ~/my-project     # specific repo
    axor-bench --file src/auth.py      # specific file as context
    axor-bench --api-key sk-ant-...    # API key (or use ANTHROPIC_API_KEY / ~/.axor/config.toml)
    axor-bench --no-raw                # skip raw baseline (governed only)
    axor-bench --delay 30              # 30s pause between tasks (avoids rate limits)
"""

import argparse
import os
import sys
import time
from pathlib import Path

# reuse auth from axor-cli if available, else inline fallback
try:
    from axor_cli.auth import resolve_api_key as _cli_resolve
    def _resolve_api_key(flag_key: str | None) -> str | None:
        return _cli_resolve("claude", flag_key)
except ImportError:
    def _resolve_api_key(flag_key: str | None) -> str | None:
        """Priority: --api-key > ANTHROPIC_API_KEY > ~/.axor/config.toml"""
        if flag_key:
            return flag_key
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            return env_key
        config_file = Path.home() / ".axor" / "config.toml"
        if config_file.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    return None
            try:
                with open(config_file, "rb") as f:
                    cfg = tomllib.load(f)
                key = cfg.get("claude", {}).get("api_key")
                if key:
                    os.environ["ANTHROPIC_API_KEY"] = key
                    return key
            except Exception:
                pass
        return None


# Max file content size for benchmark context
MAX_CONTEXT_BYTES = 8000


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="axor-bench",
        description="Benchmark governed (axor) vs raw Claude on your codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)"
    )
    p.add_argument(
        "--repo", default=".", help="Path to repo (default: current dir)"
    )
    p.add_argument(
        "--file",
        help="Specific file to use as context (overrides auto-detection)",
    )
    p.add_argument(
        "--suite",
        default="quick",
        choices=["quick", "small", "large", "conversation", "federation", "full"],
        help="Which benchmark suite to run (default: quick)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Model ID for both runners (default: claude-sonnet-4-6)",
    )
    p.add_argument(
        "--no-raw",
        action="store_true",
        help="Skip raw Claude baseline (governed only)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Sleep between tasks to avoid rate limiting (default: 0)",
    )
    p.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    return p.parse_args()


def _find_file(repo: Path, override: str | None) -> Path | None:
    if override:
        p = Path(override)
        if not p.exists():
            print(f"  file not found: {override}", file=sys.stderr)
            return None
        return p

    from benchmarks.tasks import find_target_file

    found = find_target_file(repo)
    if found:
        print(f"  -> using file: {found.relative_to(repo)}")
    else:
        print("  (no suitable Python file found — file-based tasks will be skipped)")
    return found


def _run_suite(
    suite: str,
    api_key: str,
    repo: Path,
    target_file: Path | None,
    run_raw: bool,
    model: str | None = None,
    delay: float = 0.0,
) -> tuple[list, list]:
    from benchmarks.governed import GovernedRunner
    from benchmarks.raw import RawRunner
    from benchmarks.tasks import get_suite

    tasks = get_suite(suite)
    raw_run = RawRunner(api_key, model=model) if run_raw else None
    gov_run = GovernedRunner(api_key, model=model)

    raw_results = []
    gov_results = []

    file_content: str | None = None
    if target_file:
        try:
            file_content = target_file.read_text(encoding="utf-8")
            if len(file_content) > MAX_CONTEXT_BYTES:
                file_content = (
                    file_content[:MAX_CONTEXT_BYTES]
                    + f"\n# ... (truncated to {MAX_CONTEXT_BYTES // 1000}KB for benchmark)"
                )
        except Exception:
            file_content = None

    try:
        for i, task in enumerate(tasks):
            fc = file_content if task.needs_file else None

            if delay > 0 and i > 0:
                print(f"    (waiting {delay:.0f}s ...)", flush=True)
                time.sleep(delay)

            print(f"\n  {task.suite}/{task.name}")

            # raw baseline (skip federation — no raw equivalent)
            if run_raw and task.suite != "federation":
                print("    running raw ...", end="", flush=True)
                if task.suite == "conversation":
                    r = raw_run.run_conversation(task.name, task.turns, fc, suite=task.suite)
                else:
                    r = raw_run.run_single(task.name, task.prompt, fc, suite=task.suite)
                raw_results.append(r)
                if r.error:
                    print(f" error: {r.error[:50]}")
                else:
                    print(f" {r.total_tokens:,} tokens  {r.latency_ms:.0f}ms")

            # governed
            print("    running governed ...", end="", flush=True)
            if task.suite == "conversation":
                g = gov_run.run_conversation(task.name, task.turns, fc, suite=task.suite)
            elif task.suite == "federation":
                g = gov_run.run_federation(
                    task.name, task.prompt, task.child_tasks, fc
                )
            else:
                g = gov_run.run_single(task.name, task.prompt, fc, suite=task.suite)

            gov_results.append(g)
            if g.error:
                print(f" error: {g.error[:50]}")
            else:
                extras = f"  policy={g.policy}"
                if g.children:
                    extras += f"  children={g.children}"
                print(
                    f" {g.total_tokens:,} tokens  {g.latency_ms:.0f}ms{extras}"
                )
    finally:
        gov_run.close()

    return raw_results, gov_results


def main() -> None:
    args = _parse_args()

    print()
    print("\033[1m  axor-bench\033[0m")
    print()

    # API key
    api_key = _resolve_api_key(args.api_key)
    if not api_key:
        print("  No API key found.")
        print("    Set ANTHROPIC_API_KEY, use --api-key, or run: axor claude -> /auth")
        sys.exit(1)
    print("  -> API key loaded")

    # Repo
    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"  Repo not found: {repo}", file=sys.stderr)
        sys.exit(1)
    print(f"  -> repo: {repo}")
    print(f"  -> suite: {args.suite}")
    if args.model:
        print(f"  -> model: {args.model}")

    # Target file
    target_file = _find_file(repo, args.file)

    print()
    print("  running benchmarks ...")

    t0 = time.perf_counter()
    raw_results, gov_results = _run_suite(
        suite=args.suite,
        api_key=api_key,
        repo=repo,
        target_file=target_file,
        run_raw=not args.no_raw,
        model=args.model,
        delay=args.delay,
    )
    elapsed = time.perf_counter() - t0

    print(f"\n  completed in {elapsed:.1f}s")

    if args.output == "json":
        import json

        out = {
            "raw": [vars(r) for r in raw_results],
            "governed": [vars(r) for r in gov_results],
        }
        print(json.dumps(out, indent=2))
        return

    from benchmarks.reporter import build_rows, print_report

    rows = build_rows(raw_results, gov_results)
    print_report(
        rows=rows,
        repo_path=str(repo),
        target_file=str(target_file) if target_file else None,
    )


if __name__ == "__main__":
    main()
