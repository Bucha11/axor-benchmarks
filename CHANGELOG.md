# Changelog

## 0.2.0 — 2026-04-29

### Changed
- Default model refreshed: `claude-sonnet-4-6` (was `claude-sonnet-4-5`)
  for both governed and raw runners.

### Constraints
- Pin bumps:
  - `axor-core>=0.4.0,<0.5` (was `>=0.1.0`)
  - `axor-claude>=0.2.0,<0.3` (was `>=0.1.0`)
  - `anthropic>=0.40.0,<1.0` upper-bound formalized.

### Removed
- Internal scratch docs (`REFACTORING_SUMMARY.md`,
  `TEST_COVERAGE_IMPROVEMENTS.md`) and a stray
  `test_context_compressor.py` at the package root with broken imports.

## 0.1.1 — 2026-04-14

### Fixed
- Packaging cleanup; no behavioral changes.

## 0.1.0 — 2026-04-14

Initial release.

### Added
- `axor-bench` CLI for comparing governed vs raw Claude on a target codebase.
- Suite layouts (`small`, `quick`, `full`) and per-task runners
  (`governed.py`, `raw.py`).
- Reporter (`reporter.py`) for per-task and aggregate output.
- API key resolution that reuses `axor-cli` auth when available, with an
  inline fallback (`--api-key` → `ANTHROPIC_API_KEY` → `~/.axor/config.toml`).
- `--delay` knob to pace requests under provider rate limits.
