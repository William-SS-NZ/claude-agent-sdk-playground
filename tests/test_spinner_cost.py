"""Spinner live token / cost rendering behaviour."""

import time

import pytest

from agent_builder.utils import Spinner


def test_initial_render_shows_label_and_elapsed():
    s = Spinner("thinking")
    s._started_at = time.monotonic()
    line = s._render_line()
    assert "thinking" in line
    assert "s)" in line
    # No tokens yet — no cost parts
    assert "tok" not in line
    assert "$" not in line


def test_adds_tokens_and_shows_estimated_cost():
    s = Spinner("thinking")
    s._started_at = time.monotonic() - 0.05  # fresh spinner
    s.add_tokens(input_tokens=1_000_000)  # 1M input at $15 = $15.00
    line = s._render_line()
    assert "1,000,000 tok" in line
    assert "~$15.0000" in line  # tilde means estimated
    assert "/min" not in line  # elapsed < 1.0s so no per-min yet


def test_set_cost_overrides_estimate_and_flips_tag():
    s = Spinner("done")
    s._started_at = time.monotonic() - 30
    s.add_tokens(input_tokens=1_000_000, output_tokens=0)  # estimate = $15
    s.set_cost(0.42)  # authoritative, much smaller
    line = s._render_line()
    assert "$0.4200" in line
    assert "~$" not in line  # tilde gone — authoritative


def test_per_minute_shows_after_one_second():
    s = Spinner("thinking")
    s._started_at = time.monotonic() - 60  # exactly one minute elapsed
    s.add_tokens(output_tokens=1_000_000)  # 1M output at $75 = $75.00
    line = s._render_line()
    assert "/min" in line


def test_input_plus_output_costs_combine():
    s = Spinner("thinking")
    s._started_at = time.monotonic() - 0.05
    s.add_tokens(input_tokens=1_000_000, output_tokens=1_000_000)
    # 1M in ($15) + 1M out ($75) = $90.00
    assert abs(s._estimated_cost() - 90.0) < 1e-6


def test_add_tokens_accumulates():
    s = Spinner("thinking")
    s.add_tokens(input_tokens=100, output_tokens=50)
    s.add_tokens(input_tokens=200, output_tokens=25)
    assert s.input_tokens == 300
    assert s.output_tokens == 75
