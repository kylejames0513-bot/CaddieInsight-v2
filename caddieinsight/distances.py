"""The carry model: what a club's number is and how much to trust it.

The number shown for a club is the median carry of its most recent WINDOW
shots — a median because one thinned 7-iron should not move your yardage
book, and windowed because the swing you have now is not the swing you had
two seasons ago. Around it we keep the honest spread (P25–P75 of the same
window) and a confidence grade earned by sample size and consistency.

Honesty rule: a club with no shots has no carry, full stop. Thin data is
graded thin; data older than STALE_DAYS is flagged stale rather than
silently trusted.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

WINDOW = 20          # most recent shots considered for the number
STALE_DAYS = 90      # newest shot older than this → the number is stale

# Grade thresholds: shots in window, and max spread as a fraction of carry.
GRADE_A = (12, 0.12)
GRADE_B = (6, 0.18)
GRADE_C_MIN_SHOTS = 3

GRADE_LABELS = {
    "A": "Dialed",
    "B": "Solid",
    "C": "Forming",
    "D": "Thin data",
}


@dataclass(frozen=True)
class CarryNumber:
    """The measured story of one club."""

    carry: float | None      # windowed median, None until a shot is logged
    p25: float | None
    p75: float | None
    shots_in_window: int
    shots_total: int
    grade: str | None        # A/B/C/D, None without data
    stale: bool
    newest: datetime | None
    window: tuple[float, ...] = ()   # the shots behind the number

    @property
    def spread(self) -> float | None:
        if self.p25 is None or self.p75 is None:
            return None
        return self.p75 - self.p25

    @property
    def grade_label(self) -> str | None:
        return GRADE_LABELS.get(self.grade) if self.grade else None


def _quartiles(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def carry_number(
    shots: list[tuple[float, datetime]],
    now: datetime | None = None,
) -> CarryNumber:
    """Compute the club's number from ``(carry, logged_at)`` pairs.

    ``shots`` may arrive in any order; recency is decided by ``logged_at``.
    """
    now = now or datetime.utcnow()
    if not shots:
        return CarryNumber(None, None, None, 0, 0, None, False, None)

    ordered = sorted(shots, key=lambda s: s[1], reverse=True)
    window = [carry for carry, _ in ordered[:WINDOW]]
    newest = ordered[0][1]

    carry = float(statistics.median(window))
    p25, p75 = _quartiles(sorted(window))
    n = len(window)
    spread = p75 - p25

    if n >= GRADE_A[0] and spread <= GRADE_A[1] * carry:
        grade = "A"
    elif n >= GRADE_B[0] and spread <= GRADE_B[1] * carry:
        grade = "B"
    elif n >= GRADE_C_MIN_SHOTS:
        grade = "C"
    else:
        grade = "D"

    stale = (now - newest) > timedelta(days=STALE_DAYS)
    return CarryNumber(
        carry=round(carry, 1),
        p25=round(float(p25), 1),
        p75=round(float(p75), 1),
        shots_in_window=n,
        shots_total=len(ordered),
        grade=grade,
        stale=stale,
        newest=newest,
        window=tuple(window),
    )


def reach_percent(number: CarryNumber, target: float) -> int | None:
    """Share of the window that carried at least ``target``, as 0–100."""
    if not number.window:
        return None
    reached = sum(1 for carry in number.window if carry >= target)
    return round(100 * reached / len(number.window))
