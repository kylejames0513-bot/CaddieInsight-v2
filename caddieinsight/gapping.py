"""Gapping: the bag ladder, and what it says about the bag.

Clubs with a measured carry are laid out longest-first. The interesting
facts are the *distances between* adjacent rungs: a gap wider than WIDE_GAP
yards is a yardage you own no club for; a gap narrower than OVERLAP yards
means two clubs are doing one club's job. Clubs without data are listed
separately — they are not on the ladder because nothing has earned them a
rung yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .distances import CarryNumber

WIDE_GAP = 25    # yards between rungs you cannot cover
OVERLAP = 8      # rungs this close are one club twice


@dataclass(frozen=True)
class Rung:
    key: str
    label: str
    kind: str
    number: CarryNumber


@dataclass(frozen=True)
class Gap:
    longer_key: str
    shorter_key: str
    yards: float
    verdict: str  # "wide" | "overlap" | "ok"


@dataclass(frozen=True)
class GappingReport:
    ladder: list[Rung] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    unmeasured: list[Rung] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)

    @property
    def wide_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.verdict == "wide"]

    @property
    def overlaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.verdict == "overlap"]


def _verdict(yards: float) -> str:
    if yards >= WIDE_GAP:
        return "wide"
    if yards <= OVERLAP:
        return "overlap"
    return "ok"


def analyze(clubs: list[Rung]) -> GappingReport:
    """Build the gapping report from ``Rung``s (measured or not)."""
    measured = [c for c in clubs if c.number.carry is not None]
    unmeasured = sorted(
        (c for c in clubs if c.number.carry is None),
        key=lambda c: c.key,
    )
    ladder = sorted(measured, key=lambda c: (-c.number.carry, c.key))

    gaps: list[Gap] = []
    for longer, shorter in zip(ladder, ladder[1:]):
        yards = round(longer.number.carry - shorter.number.carry, 1)
        gaps.append(Gap(longer.key, shorter.key, yards, _verdict(yards)))

    insights: list[str] = []
    for gap in gaps:
        longer = next(c for c in ladder if c.key == gap.longer_key)
        shorter = next(c for c in ladder if c.key == gap.shorter_key)
        if gap.verdict == "wide":
            low = int(shorter.number.carry)
            high = int(longer.number.carry)
            insights.append(
                f"{gap.yards:g} yards between {longer.label} and "
                f"{shorter.label} — you own nothing that carries "
                f"{low}–{high}. That is a layup you did not choose."
            )
        elif gap.verdict == "overlap":
            insights.append(
                f"{longer.label} and {shorter.label} carry within "
                f"{gap.yards:g} yards of each other — one of them is a "
                f"passenger in the bag."
            )
    for club in unmeasured:
        insights.append(
            f"{club.label} has no logged shots yet, so it has no rung on "
            f"the ladder. Log a few carries to place it."
        )
    if not measured:
        insights.append(
            "No club has a measured carry yet. Log a range session and the "
            "ladder builds itself."
        )
    return GappingReport(
        ladder=ladder, gaps=gaps, unmeasured=unmeasured, insights=insights
    )
