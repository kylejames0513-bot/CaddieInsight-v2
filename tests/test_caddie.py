from datetime import datetime

import pytest

from caddieinsight.caddie import plays_like, recommend
from caddieinsight.distances import carry_number
from caddieinsight.gapping import Rung

NOW = datetime(2026, 8, 25)


def rung(key, label, carry, n=10):
    shots = [(float(carry + i - n // 2), NOW) for i in range(n)]
    return Rung(key=key, label=label, kind="iron",
                number=carry_number(shots, now=NOW))


BAG = [
    rung("DR", "Driver", 240),
    rung("7I", "7-iron", 155),
    rung("8I", "8-iron", 143),
    rung("9I", "9-iron", 131),
]


def test_plays_like_neutral_conditions_change_nothing():
    assert plays_like(150).adjusted == 150


def test_plays_like_uphill_adds_a_yard_per_three_feet():
    assert plays_like(150, elevation_ft=30).adjusted == 160


def test_plays_like_headwind_bites_twice_as_hard_as_tailwind_helps():
    assert plays_like(150, wind_mph=10).adjusted == 160
    assert plays_like(150, wind_mph=-10).adjusted == 145


def test_plays_like_cold_air_is_heavy_air():
    assert plays_like(150, temp_f=50).adjusted == 154


def test_recommend_picks_the_nearest_carry():
    result = recommend(BAG, 144)
    assert result.pick.key == "8I"
    assert result.reach is not None
    assert result.alternative.key == "7I"


def test_recommend_near_tie_takes_the_longer_club():
    # 149 sits between 8I (143) and 7I (155): 7I is 6 away, 8I is 6 away —
    # within the tie margin the longer club wins.
    result = recommend(BAG, 149)
    assert result.pick.key == "7I"


def test_recommend_uses_plays_like_not_raw_target():
    # 143 raw is the 8-iron, but 12 yards of headwind makes it the 7-iron.
    result = recommend(BAG, 143, wind_mph=12)
    assert result.plays.adjusted == 155
    assert result.pick.key == "7I"


def test_recommend_never_guesses_without_data():
    result = recommend([], 150)
    assert result.pick is None
    assert "does not guess" in result.note


def test_recommend_beyond_the_bag_is_honest():
    result = recommend(BAG, 300)
    assert result.pick.key == "DR"
    assert "no hero club" in result.note


def test_recommend_inside_the_bag_is_honest():
    result = recommend(BAG, 60)
    assert result.pick.key == "9I"
    assert "partial swing" in result.note


@pytest.mark.parametrize("target", [144, 149, 155, 240])
def test_recommend_always_reports_reach(target):
    result = recommend(BAG, target)
    assert 0 <= result.reach <= 100
