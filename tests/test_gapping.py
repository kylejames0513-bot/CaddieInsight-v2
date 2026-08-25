from datetime import datetime

from caddieinsight.distances import carry_number
from caddieinsight.gapping import OVERLAP, WIDE_GAP, Rung, analyze

NOW = datetime(2026, 8, 25)


def rung(key, label, carry=None, n=6):
    shots = [(float(carry), NOW)] * n if carry is not None else []
    return Rung(key=key, label=label, kind="iron",
                number=carry_number(shots, now=NOW))


def test_ladder_orders_longest_first():
    report = analyze([
        rung("9I", "9-iron", 130),
        rung("DR", "Driver", 240),
        rung("7I", "7-iron", 155),
    ])
    assert [r.key for r in report.ladder] == ["DR", "7I", "9I"]


def test_wide_gap_flagged():
    report = analyze([rung("DR", "Driver", 240), rung("7I", "7-iron", 150)])
    assert len(report.gaps) == 1
    gap = report.gaps[0]
    assert gap.yards == 90 >= WIDE_GAP
    assert gap.verdict == "wide"
    assert any("own nothing" in i for i in report.insights)


def test_overlap_flagged_as_passenger():
    report = analyze([rung("4I", "4-iron", 178), rung("5I", "5-iron", 174)])
    assert report.gaps[0].yards <= OVERLAP
    assert report.gaps[0].verdict == "overlap"
    assert any("passenger" in i for i in report.insights)


def test_healthy_gap_not_flagged():
    report = analyze([rung("7I", "7-iron", 155), rung("8I", "8-iron", 143)])
    assert report.gaps[0].verdict == "ok"
    assert report.wide_gaps == [] and report.overlaps == []


def test_unmeasured_clubs_kept_off_the_ladder():
    report = analyze([rung("7I", "7-iron", 155), rung("3W", "3-wood")])
    assert [r.key for r in report.ladder] == ["7I"]
    assert [r.key for r in report.unmeasured] == ["3W"]
    assert any("no logged shots" in i for i in report.insights)


def test_empty_bag_gets_the_honest_line():
    report = analyze([])
    assert report.ladder == []
    assert any("ladder builds itself" in i for i in report.insights)
