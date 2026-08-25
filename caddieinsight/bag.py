"""The club catalogue and the default bag.

Every club a user can carry is named here once: a stable key, a display
label, a kind, and a sort rank used whenever there is no measured carry to
order by. The putter is deliberately absent — this product is a yardage
book, and the putter needs no yardage book.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClubSpec:
    key: str
    label: str
    kind: str  # wood | hybrid | iron | wedge
    rank: int  # longest club first


CATALOGUE: tuple[ClubSpec, ...] = (
    ClubSpec("DR", "Driver", "wood", 0),
    ClubSpec("3W", "3-wood", "wood", 1),
    ClubSpec("5W", "5-wood", "wood", 2),
    ClubSpec("7W", "7-wood", "wood", 3),
    ClubSpec("2H", "2-hybrid", "hybrid", 4),
    ClubSpec("3H", "3-hybrid", "hybrid", 5),
    ClubSpec("4H", "4-hybrid", "hybrid", 6),
    ClubSpec("5H", "5-hybrid", "hybrid", 7),
    ClubSpec("2I", "2-iron", "iron", 8),
    ClubSpec("3I", "3-iron", "iron", 9),
    ClubSpec("4I", "4-iron", "iron", 10),
    ClubSpec("5I", "5-iron", "iron", 11),
    ClubSpec("6I", "6-iron", "iron", 12),
    ClubSpec("7I", "7-iron", "iron", 13),
    ClubSpec("8I", "8-iron", "iron", 14),
    ClubSpec("9I", "9-iron", "iron", 15),
    ClubSpec("PW", "Pitching wedge", "wedge", 16),
    ClubSpec("GW", "Gap wedge", "wedge", 17),
    ClubSpec("SW", "Sand wedge", "wedge", 18),
    ClubSpec("LW", "Lob wedge", "wedge", 19),
)

BY_KEY: dict[str, ClubSpec] = {spec.key: spec for spec in CATALOGUE}

# Thirteen slots: with the putter that is the legal fourteen. Chosen as the
# most common off-the-rack setup so onboarding is one tap, not twenty.
DEFAULT_BAG: tuple[str, ...] = (
    "DR", "3W", "5W", "4H",
    "5I", "6I", "7I", "8I", "9I",
    "PW", "GW", "SW", "LW",
)

KIND_LABELS: dict[str, str] = {
    "wood": "Woods",
    "hybrid": "Hybrids",
    "iron": "Irons",
    "wedge": "Wedges",
}


def spec_for(key: str) -> ClubSpec:
    """Return the catalogue entry for ``key`` or raise ``KeyError``."""
    return BY_KEY[key.upper()]


def is_valid_key(key: str) -> bool:
    return key.upper() in BY_KEY
