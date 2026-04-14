# axor-benchmarks

[![CI](https://github.com/Bucha11/axor-benchmarks/actions/workflows/ci.yml/badge.svg)](https://github.com/Bucha11/axor-benchmarks/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/axor-benchmarks)](https://pypi.org/project/axor-benchmarks/)
[![Python](https://img.shields.io/pypi/pyversions/axor-benchmarks)](https://pypi.org/project/axor-benchmarks/)
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

Output:
```
  axor benchmark results
  repo: ~/my-project
  file: src/auth.py

  task                  raw tokens    governed    savings  bar               policy
  ─────────────────────────────────────────────────────────────────────────────────
  write_test                 1,842       1,203    -34.7%  ████████░░░░░░░░  focused_generative
  explain_function           1,105         891    -19.4%  ███░░░░░░░░░░░░░  focused_readonly
  find_bugs                  1,290         978    -24.2%  ████░░░░░░░░░░░░  focused_readonly
  ─────────────────────────────────────────────────────────────────────────────────
  TOTAL                      4,237       3,072    -27.5%  ████░░░░░░░░░░░░

  insights
  → Token reduction:    27.5% (4,237 → 3,072 tokens)
  → Most used policy:   focused_readonly (2 tasks)
```

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

  --api-key KEY     Anthropic API key
  --repo PATH       Repo to benchmark (default: current dir)
  --file PATH       Specific file to use as context
  --suite SUITE     quick | small | large | conversation | federation | full
  --no-raw          Skip raw Claude baseline (governed only)
  --output FORMAT   table (default) | json
```

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
