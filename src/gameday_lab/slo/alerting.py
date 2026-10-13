"""Part E — Multi-window, multi-burn-rate alerting (Google SRE Workbook, ch. 5).

Input: per-minute ``total`` and ``bad`` request counts for a 30-day window.

burn_rate(window) = error_ratio(window) / (1 - SLO)

A rule fires at minute i when BOTH its long and its short window (ending at i,
inclusive) burn at least ``burn_rate``. The long window says "this is
significant"; the short window says "it is still happening" (so the alert
resets quickly after recovery).

Tests: tests/test_alerting.py, then `make slo`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AlertRule:
    name: str
    severity: str  # "page" or "ticket"
    long_min: int
    short_min: int
    burn_rate: float


# SRE Workbook defaults for a 30-day SLO window
DEFAULT_RULES: tuple[AlertRule, ...] = (
    AlertRule("fast_burn_2pct_1h", "page", 60, 5, 14.4),
    AlertRule("slow_burn_5pct_6h", "page", 360, 30, 6.0),
    AlertRule("budget_leak_10pct_3d", "ticket", 4320, 360, 1.0),
)


@dataclass(frozen=True)
class AlertEvent:
    rule: str
    severity: str
    start_min: int  # first minute the rule fired
    end_min: int  # first minute it stopped firing (exclusive)


class WindowSums:
    """O(1) sum of any window, via prefix sums. Build once, query many times.

    43,200 minutes x 6 windows: recomputing every window with sum() is far too slow.
    """

    def __init__(self, values: list[int]) -> None:
        """TODO(student): build the prefix-sum list (prefix[0] = 0)."""
        self.prefix = [0]
        for value in values:
            self.prefix.append(self.prefix[-1] + value)

    def sum(self, end_inclusive: int, length: int) -> int:
        """TODO(student): sum of values[end_inclusive - length + 1 .. end_inclusive],
        clipped at index 0 when the window starts before the data."""
        if length < 1:
            raise ValueError("length must be >= 1")
        if end_inclusive < 0:
            return 0
        end = min(end_inclusive + 1, len(self.prefix) - 1)
        start = min(end, max(0, end_inclusive - length + 1))
        return self.prefix[end] - self.prefix[start]


class BurnRateAlerter:
    def __init__(self, slo: float = 0.995, rules: tuple[AlertRule, ...] = DEFAULT_RULES) -> None:
        if not 0 < slo < 1:
            raise ValueError("slo must be in (0, 1)")
        self.slo = slo
        self.rules = rules

    def burn_rate(self, total: WindowSums, bad: WindowSums, end: int, length: int) -> float:
        """TODO(student): (bad / total over the window) / (1 - slo); 0.0 if total is 0."""
        requests = total.sum(end, length)
        if requests == 0:
            return 0.0
        return (bad.sum(end, length) / requests) / (1 - self.slo)

    def evaluate(self, total: list[int], bad: list[int]) -> list[AlertEvent]:
        """TODO(student): one AlertEvent per contiguous firing episode of each rule.

        For each rule, scan the minutes; the rule fires at minute i when
        burn(long) >= rule.burn_rate AND burn(short) >= rule.burn_rate.
        An episode starts at the first firing minute and ends (exclusive) at the
        first minute it stops firing (or len(total)). Sort by start_min.
        """
        if len(total) != len(bad):
            raise ValueError("total and bad must have the same length")
        total_sums, bad_sums = WindowSums(total), WindowSums(bad)
        events: list[AlertEvent] = []
        for rule in self.rules:
            start: int | None = None
            for minute in range(len(total)):
                long_rate = self.burn_rate(total_sums, bad_sums, minute, rule.long_min)
                short_rate = self.burn_rate(total_sums, bad_sums, minute, rule.short_min)
                # Include exact thresholds despite binary floating-point rounding.
                firing = (
                    (long_rate >= rule.burn_rate or math.isclose(long_rate, rule.burn_rate, rel_tol=1e-12))
                    and (short_rate >= rule.burn_rate or math.isclose(short_rate, rule.burn_rate, rel_tol=1e-12))
                )
                if firing and start is None:
                    start = minute
                elif not firing and start is not None:
                    events.append(AlertEvent(rule.name, rule.severity, start, minute))
                    start = None
            if start is not None:
                events.append(AlertEvent(rule.name, rule.severity, start, len(total)))
        return sorted(events, key=lambda event: event.start_min)


def error_budget_report(total: list[int], bad: list[int], slo: float = 0.995) -> dict[str, float | bool]:
    """TODO(student): how much of the 30-day error budget is spent?

    Return a dict with:
      requests          sum(total)
      allowed_bad       (1 - slo) * requests            (round to 1 decimal)
      bad               sum(bad)
      availability      1 - bad / requests              (round to 6 decimals)
      budget_consumed   bad / allowed_bad               (round to 4 decimals)
      budget_remaining  1 - budget_consumed             (round to 4 decimals)
      freeze_releases   True when nothing is left (budget_remaining <= 0)
    """
    if not 0 < slo < 1:
        raise ValueError("slo must be in (0, 1)")
    if len(total) != len(bad):
        raise ValueError("total and bad must have the same length")
    requests, errors = sum(total), sum(bad)
    allowed_bad = (1 - slo) * requests
    consumed = errors / allowed_bad if allowed_bad else 0.0
    remaining = 1 - consumed
    return {
        "requests": requests,
        "allowed_bad": round(allowed_bad, 1),
        "bad": errors,
        "availability": round(1 - errors / requests, 6) if requests else 1.0,
        "budget_consumed": round(consumed, 4),
        "budget_remaining": round(remaining, 4),
        "freeze_releases": remaining <= 0 or math.isclose(consumed, 1.0, rel_tol=1e-12),
    }
