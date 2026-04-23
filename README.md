# axor-benchmarks

[![CI](https://github.com/Bucha11/axor-benchmarks/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Bucha11/axor-benchmarks/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/axor-benchmarks?cacheSeconds=300)](https://pypi.org/project/axor-benchmarks/)
[![Python](https://img.shields.io/pypi/pyversions/axor-benchmarks?cacheSeconds=300)](https://pypi.org/project/axor-benchmarks/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Benchmark governed (axor) vs raw Claude on your codebase.**

Measures real token savings, latency, and federation across 4 benchmark suites on any Python project.

---

## Installation

```bash
pip install axor-benchmarks
```

---

## Quick Start

```bash
cd ~/my-project
axor-bench
```

Runs `quick` suite (1 small task, ~30s). Use `--suite full` for complete benchmark.

---

## Authentication

Priority order (highest to lowest):

1. `--api-key sk-ant-...` flag
2. `ANTHROPIC_API_KEY` env var
3. `~/.axor/config.toml` (set via `axor claude → /auth`)

```bash
# Use env var
ANTHROPIC_API_KEY=sk-ant-... axor-bench

# Use flag (not saved)
axor-bench --api-key sk-ant-...

# Use saved key from axor-cli
axor claude    # → /auth  →  saves to ~/.axor/config.toml
axor-bench     # reads automatically
```

---

## Suites

| Suite | Tasks | What it measures |
|-------|-------|-----------------|
| `quick` | 1 task | Fast sanity check (~30s) |
| `small` | 3 tasks | Single-turn focused tasks |
| `large` | 2 tasks | Multi-tool, multi-step tasks |
| `conversation` | 1 × 10 turns | Context growth over long sessions |
| `federation` | 1 task | Child agent spawning + isolation |
| `full` | all | Complete benchmark (~5-10 min) |

```bash
axor-bench --suite small          # fast
axor-bench --suite full           # complete
axor-bench --suite conversation   # test context compression
axor-bench --suite federation     # test child agents
```

---

## Options

```
axor-bench [options]

  --api-key KEY       Anthropic API key
  --repo PATH         Repo to benchmark (default: current dir)
  --file PATH         Specific file to use as context
  --suite SUITE       quick | small | large | conversation | federation | full
  --model MODEL       Model ID for both runners (default: claude-sonnet-4-5)
  --no-raw            Skip raw Claude baseline (governed only)
  --delay SECONDS     Pause between tasks to avoid rate limits (default: 0)
  --output FORMAT     table (default) | json
```

---

## Results (claude-sonnet-4-5, full suite)

Benchmark ran against `axor-cli/axor_cli/auth.py` (~340 LOC) from the axor monorepo.

| Task | Suite | Raw tokens | Governed | Savings | Policy |
|------|-------|-----------|----------|---------|--------|
| write_test | small | 8,693 | 10,855 | -24.9% | focused_generative |
| explain_function | small | 3,022 | 2,901 | **+4.0%** | focused_readonly |
| find_bugs | small | 3,265 | 3,251 | +0.4% | focused_generative |
| refactor_module | large | 97,370 | 66,005 | **+32.2%** | moderate_mutative |
| add_error_handling | large | 19,663 | 19,391 | +1.4% | focused_generative |
| iterative_review | conversation (10 turns) | 117,465 | 70,298 | **+40.2%** | focused_generative |
| parallel_analysis | federation | — | 17,698 | — | preset:federated |
| **TOTAL** | | **249,478** | **172,701** | **+30.8%** | |

**Key insights:**
- **30.8% total token reduction** (249K → 173K tokens)
- **40.2% savings on multi-turn conversation** — context compression effect grows with session length
- **32.2% savings on large refactoring** — caching and dedup reduce repeated file reads
- Small single-turn tasks show near-zero or negative savings — governance overhead > compression benefit on short tasks
- Federation task (17.7K tokens) ran with `federated` policy preset

> Small tasks (write_test, explain, find_bugs) show minimal savings because the context is not yet large enough
> for compression to outweigh governance overhead. Savings become significant at 10K+ tokens (large/conversation tasks).

---

## What is measured

**Raw Claude** — direct Anthropic API call with no governance:
- Full conversation history passed every turn
- No context compression
- No policy selection
- No tool governance

**Governed (axor)** — same task via GovernedSession:
- Dynamic policy based on task (focused_readonly, moderate_mutative, etc.)
- Context shaped and compressed per turn
- Waste elimination (dedup, error collapse, prose summarization)
- Session-scoped cache (no re-reading same file twice)

**Token savings** = `(raw - governed) / raw × 100%`

Positive = governed uses fewer tokens (expected for most tasks).
Negative = governed uses more (possible for very simple tasks where overhead > savings).

---

## Requirements

- Python 3.11+
- `axor-core >= 0.1.0`
- `axor-claude >= 0.1.0`
- `anthropic >= 0.40.0`

---

## License

MIT
