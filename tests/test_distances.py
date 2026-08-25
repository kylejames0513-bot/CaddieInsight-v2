from datetime import datetime, timedelta

from caddieinsight.distances import (
    STALE_DAYS,
    WINDOW,
    carry_number,
    reach_percent,
)

NOW = datetime(2026, 8, 25, 12, 0, 0)


def shots(carries, days_ago=1):
    when = NOW - timedelta(days=days_ago)
    return [(float(c), when) for c in carries]


def test_no_shots_means_no_number():
    number = carry_number([], now=NOW)
    assert number.carry is None
    assert number.grade is None
    assert number.shots_total == 0
    assert not number.stale


def test_single_shot_is_thin_data():
    number = carry_number(shots([150]), now=NOW)
    assert number.carry == 150
    assert number.p25 == 150 and number.p75 == 150
    assert number.grade == "D"


def test_median_not_mean():
    # One thinned shot must not drag the number.
    number = carry_number(shots([150, 151, 152, 90]), now=NOW)
    assert number.carry == 150.5


def test_window_uses_most_recent_shots():
    old = [(100.0, NOW - timedelta(days=300 + i)) for i in range(WINDOW)]
    new = [(160.0, NOW - timedelta(days=i + 1)) for i in range(WINDOW)]
    number = carry_number(old + new, now=NOW)
    assert number.carry == 160
    assert number.shots_in_window == WINDOW
    assert number.shots_total == 2 * WINDOW


def test_grades_scale_with_evidence():
    tight = shots([148, 149, 150, 150, 151, 152] * 2)  # 12 tight shots
    assert carry_number(tight, now=NOW).grade == "A"
    six = shots([148, 149, 150, 150, 151, 152])
    assert carry_number(six, now=NOW).grade == "B"
    scattered = shots([120, 150, 180])
    assert carry_number(scattered, now=NOW).grade == "C"
    assert carry_number(shots([150, 151]), now=NOW).grade == "D"


def test_wide_spread_never_grades_a():
    wild = shots([120, 130, 140, 150, 160, 170, 180, 190, 200, 130, 170, 150])
    number = carry_number(wild, now=NOW)
    assert number.shots_in_window >= 12
    assert number.grade == "C"


def test_stale_flag():
    number = carry_number(shots([150], days_ago=STALE_DAYS + 5), now=NOW)
    assert number.stale
    fresh = carry_number(shots([150], days_ago=5), now=NOW)
    assert not fresh.stale


def test_reach_percent():
    number = carry_number(shots([140, 145, 150, 155]), now=NOW)
    assert reach_percent(number, 150) == 50
    assert reach_percent(number, 100) == 100
    assert reach_percent(number, 200) == 0
    assert reach_percent(carry_number([], now=NOW), 150) is None
