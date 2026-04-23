"""Tests for benchmarks.reporter — result formatting and insights."""
from __future__ import annotations

import pytest

from benchmarks.raw import RawResult
from benchmarks.governed import GovernedResult
from benchmarks.reporter import build_rows, _pct, _bar, ComparisonRow


# ── _pct ──────────────────────────────────────────────────────────────────────


def test_pct_normal():
    assert _pct(100, 70) == pytest.approx(30.0)


def test_pct_no_savings():
    assert _pct(100, 100) == pytest.approx(0.0)


def test_pct_negative_savings():
    assert _pct(100, 120) == pytest.approx(-20.0)


def test_pct_zero_raw():
    assert _pct(0, 50) == 0.0


# ── _bar ──────────────────────────────────────────────────────────────────────


def test_bar_full():
    bar = _bar(100.0, width=10)
    assert bar.count("█") == 10


def test_bar_empty():
    bar = _bar(0.0, width=10)
    assert "█" not in bar


def test_bar_half():
    bar = _bar(50.0, width=10)
    assert bar.count("█") == 5


# ── build_rows ────────────────────────────────────────────────────────────────


def test_build_rows_matches_by_name():
    raw = [RawResult(task_name="t1", suite="small", total_tokens=1000, input_tokens=700,
                     output_tokens=300, latency_ms=100, turns=1, output="ok")]
    gov = [GovernedResult(task_name="t1", suite="small", total_tokens=700, input_tokens=500,
                          output_tokens=200, latency_ms=90, turns=1, output="ok", policy="focused_readonly")]

    rows = build_rows(raw, gov)
    assert len(rows) == 1
    assert rows[0].task_name == "t1"
    assert rows[0].raw_tokens == 1000
    assert rows[0].gov_tokens == 700
    assert rows[0].token_savings == pytest.approx(30.0)


def test_build_rows_suite_from_result():
    """Suite should come from the result object, not from parsing task name."""
    raw = [RawResult(task_name="iterative_review", suite="conversation",
                     total_tokens=5000, input_tokens=4000, output_tokens=1000,
                     latency_ms=200, turns=10, output="ok")]
    gov = [GovernedResult(task_name="iterative_review", suite="conversation",
                          total_tokens=3000, input_tokens=2000, output_tokens=1000,
                          latency_ms=150, turns=10, output="ok", policy="moderate_readonly")]

    rows = build_rows(raw, gov)
    assert rows[0].suite == "conversation"  # not "iterative"


def test_build_rows_gov_only():
    """Federation tasks have no raw baseline."""
    gov = [GovernedResult(task_name="parallel_analysis", suite="federation",
                          total_tokens=2000, input_tokens=1500, output_tokens=500,
                          latency_ms=300, turns=1, output="ok",
                          policy="federated", children=3)]

    rows = build_rows([], gov)
    assert len(rows) == 1
    assert rows[0].raw_tokens == 0
    assert rows[0].gov_tokens == 2000
    assert rows[0].children == 3


def test_build_rows_handles_errors():
    raw = [RawResult(task_name="t1", suite="small", total_tokens=0, input_tokens=0,
                     output_tokens=0, latency_ms=10, turns=1, output="", error="timeout")]
    gov = [GovernedResult(task_name="t1", suite="small", total_tokens=500, input_tokens=300,
                          output_tokens=200, latency_ms=80, turns=1, output="ok", policy="focused_generative")]

    rows = build_rows(raw, gov)
    assert rows[0].raw_error == "timeout"
    assert rows[0].gov_error is None
