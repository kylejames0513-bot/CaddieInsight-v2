"""The caddie: a yardage in, a club out, and no pretending.

The recommendation is deliberately explainable. The target is first adjusted
to a plays-like number using three published rules of thumb (slope, wind,
temperature), then the club whose measured carry sits closest to that number
wins; on a near-tie the caddie takes the longer club, because long misses
past the pin beat short misses into the front bunker. Alongside the pick we
report the share of your logged shots that actually carried the distance —
a percentage, never certainty.

With no measured clubs there is no pick. The caddie does not guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from .distances import CarryNumber, reach_percent
from .gapping import Rung

# Plays-like rules of thumb, all linear and all stated where users see them:
YARDS_PER_FOOT_ELEVATION = 1 / 3    # uphill foot ≈ a third of a yard longer
YARDS_PER_MPH_HEADWIND = 1.0        # headwind bites…
YARDS_PER_MPH_TAILWIND = 0.5        # …twice as hard as a tailwind helps
YARDS_PER_10F_BELOW_70 = 2.0        # cold air is heavy air
TIE_MARGIN = 3.0                    # carries this close are a tie → longer club


@dataclass(frozen=True)
class PlaysLike:
    target: float
    adjusted: float
    elevation_ft: float
    wind_mph: float          # positive = headwind, negative = tailwind
    temp_f: float

    @property
    def delta(self) -> float:
        return round(self.adjusted - self.target, 1)


@dataclass(frozen=True)
class Recommendation:
    plays: PlaysLike
    pick: Rung | None
    reach: int | None            # % of the pick's window that carried it
    alternative: Rung | None     # the next-longer club, when one exists
    note: str


def plays_like(
    target: float,
    elevation_ft: float = 0.0,
    wind_mph: float = 0.0,
    temp_f: float = 70.0,
) -> PlaysLike:
    adjusted = target
    adjusted += elevation_ft * YARDS_PER_FOOT_ELEVATION
    if wind_mph >= 0:
        adjusted += wind_mph * YARDS_PER_MPH_HEADWIND
    else:
        adjusted += wind_mph * YARDS_PER_MPH_TAILWIND
    adjusted += (70.0 - temp_f) / 10.0 * YARDS_PER_10F_BELOW_70
    return PlaysLike(
        target=target,
        adjusted=round(adjusted, 1),
        elevation_ft=elevation_ft,
        wind_mph=wind_mph,
        temp_f=temp_f,
    )


def recommend(
    clubs: list[Rung],
    target: float,
    elevation_ft: float = 0.0,
    wind_mph: float = 0.0,
    temp_f: float = 70.0,
) -> Recommendation:
    plays = plays_like(target, elevation_ft, wind_mph, temp_f)
    measured = sorted(
        (c for c in clubs if c.number.carry is not None),
        key=lambda c: -c.number.carry,
    )
    if not measured:
        return Recommendation(
            plays=plays,
            pick=None,
            reach=None,
            alternative=None,
            note=(
                "No club in your bag has a measured carry yet. The caddie "
                "does not guess — log a range session first."
            ),
        )

    adjusted = plays.adjusted
    best = min(measured, key=lambda c: abs(c.number.carry - adjusted))
    # Near-tie: take the longer club.
    for club in measured:
        if (
            club.number.carry > best.number.carry
            and abs(club.number.carry - adjusted)
            <= abs(best.number.carry - adjusted) + TIE_MARGIN
        ):
            best = club
    longer = [c for c in measured if c.number.carry > best.number.carry]
    alternative = longer[-1] if longer else None
    reach = reach_percent(best.number, adjusted)

    longest, shortest = measured[0], measured[-1]
    if adjusted > longest.number.carry + TIE_MARGIN:
        note = (
            f"That plays {adjusted:g} — more than your longest measured "
            f"club ({longest.label}, {longest.number.carry:g}). Take "
            f"{longest.label} and plan the next shot; there is no hero "
            f"club in the bag."
        )
    elif adjusted < shortest.number.carry - TIE_MARGIN:
        note = (
            f"That plays {adjusted:g} — inside your shortest measured club "
            f"({shortest.label}, {shortest.number.carry:g}). This is a "
            f"partial swing, and partial swings are a feel the yardage "
            f"book cannot give you."
        )
    else:
        note = (
            f"{best.label} carries {best.number.carry:g} for you "
            f"(P25 {best.number.p25:g} – P75 {best.number.p75:g})."
        )
    return Recommendation(
        plays=plays, pick=best, reach=reach, alternative=alternative, note=note
    )
