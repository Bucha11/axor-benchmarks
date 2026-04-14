from __future__ import annotations

"""
Benchmark results reporter.

Prints a clean comparison table:
    raw Claude vs governed (axor)
"""

from dataclasses import dataclass
from typing import Any

from benchmarks.raw      import RawResult
from benchmarks.governed import GovernedResult


@dataclass
class ComparisonRow:
    task_name:      str
    suite:          str
    raw_tokens:     int
    gov_tokens:     int
    token_savings:  float      # percent
    raw_latency:    float
    gov_latency:    float
    policy:         str
    turns:          int
    children:       int
    raw_error:      str | None
    gov_error:      str | None
    raw_tool_calls: int = 0
    gov_tool_calls: int = 0


def _pct(raw: int, gov: int) -> float:
    if raw == 0:
        return 0.0
    return (raw - gov) / raw * 100


def _bar(pct: float, width: int = 15) -> str:
    if pct <= 0:
        return " " * width
    filled = int(min(pct / 100 * width, width))
    return "█" * filled + "░" * (width - filled)


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def green(t: str)  -> str: return _color(t, "32")
def yellow(t: str) -> str: return _color(t, "33")
def red(t: str)    -> str: return _color(t, "31")
def dim(t: str)    -> str: return _color(t, "2")
def bold(t: str)   -> str: return _color(t, "1")
def cyan(t: str)   -> str: return _color(t, "36")


def build_rows(
    raw_results: list[RawResult],
    gov_results: list[GovernedResult],
) -> list[ComparisonRow]:
    raw_map = {r.task_name: r for r in raw_results}
    gov_map = {r.task_name: r for r in gov_results}

    rows = []
    for name in [*raw_map.keys(), *[k for k in gov_map if k not in raw_map]]:
        raw = raw_map.get(name)
        gov = gov_map.get(name)

        rt  = raw.total_tokens if raw else 0
        gt  = gov.total_tokens if gov else 0
        pct = _pct(rt, gt)

        rows.append(ComparisonRow(
            task_name      = name,
            suite          = name.split("_")[0] if "_" in name else name,
            raw_tokens     = rt,
            gov_tokens     = gt,
            token_savings  = pct,
            raw_latency    = raw.latency_ms if raw else 0,
            gov_latency    = gov.latency_ms if gov else 0,
            policy         = gov.policy if gov else "—",
            turns          = gov.turns if gov else (raw.turns if raw else 0),
            children       = gov.children if gov else 0,
            raw_error      = raw.error if raw else None,
            gov_error      = gov.error if gov else None,
            raw_tool_calls = getattr(raw, "tool_calls", 0) if raw else 0,
            gov_tool_calls = getattr(gov, "tool_calls", 0) if gov else 0,
        ))

    return rows


def print_report(
    rows:       list[ComparisonRow],
    repo_path:  str,
    target_file: str | None = None,
) -> None:
    print()
    print(bold("  axor benchmark results"))
    print(dim(f"  repo: {repo_path}"))
    if target_file:
        print(dim(f"  file: {target_file}"))
    print()

    # header
    w_name   = max(18, max((len(r.task_name) for r in rows), default=18))
    header   = (
        f"  {'task':<{w_name}}  "
        f"{'raw tokens':>10}  "
        f"{'governed':>10}  "
        f"{'savings':>8}  "
        f"{'bar':<16}  "
        f"{'policy':<22}  "
        f"{'turns':>5}  "
        f"{'tools r/g':>9}  "
        f"{'children':>8}"
    )
    sep = "  " + "─" * (len(header) - 2)
    print(dim(header))
    print(dim(sep))

    for row in rows:
        name_str = row.task_name[:w_name]

        if row.raw_error or row.gov_error:
            err = row.raw_error or row.gov_error or ""
            print(f"  {red(name_str):<{w_name+10}}  {red('ERROR: ' + err[:40])}")
            continue

        savings_str = f"{row.token_savings:+.1f}%"
        if row.token_savings >= 30:
            savings_col = green(savings_str)
        elif row.token_savings >= 10:
            savings_col = yellow(savings_str)
        elif row.token_savings < 0:
            savings_col = red(savings_str)
        else:
            savings_col = savings_str

        bar = _bar(row.token_savings)
        tools_str = f"{row.raw_tool_calls}/{row.gov_tool_calls}"
        children_str = str(row.children) if row.children > 0 else dim("—")

        print(
            f"  {name_str:<{w_name}}  "
            f"{row.raw_tokens:>10,}  "
            f"{row.gov_tokens:>10,}  "
            f"{savings_col:>18}  "
            f"{green(bar)}  "
            f"{dim(row.policy):<31}  "
            f"{row.turns:>5}  "
            f"{dim(tools_str):>18}  "
            f"  {children_str:>6}"
        )

    print(dim(sep))

    # summary row
    valid = [r for r in rows if not r.raw_error and not r.gov_error and r.raw_tokens > 0]
    if valid:
        total_raw = sum(r.raw_tokens for r in valid)
        total_gov = sum(r.gov_tokens for r in valid)
        avg_savings = _pct(total_raw, total_gov)
        total_children = sum(r.children for r in valid)

        savings_str = f"{avg_savings:+.1f}%"
        savings_col = green(savings_str) if avg_savings >= 20 else yellow(savings_str)

        print(
            f"  {bold('TOTAL'):<{w_name}}  "
            f"{total_raw:>10,}  "
            f"{total_gov:>10,}  "
            f"{savings_col:>18}  "
            f"{green(_bar(avg_savings))}  "
            f"{'':22}  "
            f"{'':5}  "
            f"  {total_children:>6}"
        )

    print()
    _print_insights(rows)


def _print_insights(rows: list[ComparisonRow]) -> None:
    """Print human-readable takeaways."""
    valid = [r for r in rows if not r.raw_error and not r.gov_error and r.raw_tokens > 0]
    if not valid:
        return

    print(bold("  insights"))
    print()

    total_raw = sum(r.raw_tokens for r in valid)
    total_gov = sum(r.gov_tokens for r in valid)
    avg_savings = _pct(total_raw, total_gov)

    print(f"  {green('→')} Token reduction:   {green(f'{avg_savings:.1f}%')} "
          f"{dim(f'({total_raw:,} → {total_gov:,} tokens)')}")

    # tool call savings
    total_raw_tools = sum(r.raw_tool_calls for r in valid)
    total_gov_tools = sum(r.gov_tool_calls for r in valid)
    if total_raw_tools > 0:
        tool_savings = _pct(total_raw_tools, total_gov_tools)
        print(f"  {green('→')} Tool call reduction: {green(f'{tool_savings:.1f}%')} "
              f"{dim(f'({total_raw_tools} → {total_gov_tools} calls)')}")

    conv = [r for r in valid if r.turns > 3]
    if conv:
        conv_raw = sum(r.raw_tokens for r in conv)
        conv_gov = sum(r.gov_tokens for r in conv)
        conv_savings = _pct(conv_raw, conv_gov)
        print(f"  {green('→')} Multi-turn savings: {green(f'{conv_savings:.1f}%')} "
              f"{dim('(context compression effect)')}")

    fed = [r for r in valid if r.children > 0]
    if fed:
        total_children = sum(r.children for r in fed)
        print(f"  {cyan('→')} Federation:        {cyan(str(total_children))} child nodes spawned "
              f"{dim('with context isolation + lineage')}")

    policies = [r.policy for r in valid if r.policy not in ("error", "unknown", "—")]
    if policies:
        from collections import Counter
        top = Counter(policies).most_common(1)[0]
        print(f"  {dim('→')} Most used policy:  {dim(top[0])} "
              f"{dim(f'({top[1]} tasks)')}")

    print()
