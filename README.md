# CaddieInsight v2

**Know your carry. Trust the club.**

CaddieInsight v2 is the yardage book for *your* bag: measured carry distances
for every club you own, built from shots you actually hit — plus a caddie
that turns "152 to the pin" into a club you can commit to, and a clubhouse
where golfers compare bags instead of scores.

## What it deliberately is not

Apps that follow you around the course already exist — GPS rangefinders,
live scorecards, handicap trackers, round-by-round social feeds. CaddieInsight
does **none** of that, on purpose. It is what you open *before* the round:
on the range, at a fitting, in the clubhouse. No GPS, no scorecard, no
leaderboard — your numbers, your gaps, your bag.

## The product

- **My Bag** — every club with its *trust number*: the carry you actually
  produce (a windowed median), the honest spread around it, and a confidence
  grade that says how much data stands behind the number. A stale number says
  so instead of pretending.
- **Range log** — the fastest shot logger there is: pick a club, type carries
  (`148 152 141`), done. A range session takes 30 seconds to record.
- **Gapping** — the bag ladder drawn as an instrument readout. Gaps wide
  enough to cost you a shot are flagged; clubs carrying on top of each other
  are called what they are — a passenger in the bag.
- **The Caddie** — give it the yardage; it gives you the club, the plays-like
  number after slope, wind and temperature, and the percentage of your logged
  shots that would actually get there. With no data it says "log shots
  first" — it never guesses.
- **The Clubhouse** — a community built around bags, not rounds. Publish your
  bag card, browse the bag rack, tip your cap, talk gapping. Sharing is
  opt-in; your numbers are private until you decide otherwise.

## Running it

```bash
pip install -e ".[web]"
python -m uvicorn --factory caddieinsight.web.app:create_app --port 8799
```

Environment:

| Variable | Meaning | Default |
| --- | --- | --- |
| `CADDIE_DB` | Path to the SQLite database file | `caddieinsight.db` in the working directory |
| `CADDIE_SECRET` | HMAC key for session cookies | random per process (sessions reset on restart) |

Set `CADDIE_SECRET` in production; the Dockerfile expects a `/data` volume
for the database.

## Tests

```bash
pip install -e ".[web,test]"
python -m pytest
```

The suite covers the distance model, gapping analysis, caddie maths, the
store, every web flow, and a set of design gates that pin the INDUSTRY
grammar (square corners, the one dark field, mono for measured values).

## Lineage

v1 (the `caddieinsight` repository, package `swinglab`) is the swing-analysis
lab: phone video in, swing metrics and coaching out. v2 is a new product
surface with its own repository, focused on the bag. They share the brand,
the palette, and the type system.
