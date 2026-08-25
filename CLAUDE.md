# Working agreements

## What this is

CaddieInsight v2 — the bag-first product: measured club carries, gapping,
a caddie recommendation engine, and the Clubhouse community. Package name is
`caddieinsight`. v1 (repository `caddieinsight`, package `swinglab`) remains
the swing-analysis product; this repo does not depend on it.

## Positioning is a constraint, not marketing

v2 deliberately ships **no GPS, no scorecard, no handicap, no leaderboards**
— that territory belongs to course-companion apps (18Birdies et al.) and
competing there is an explicit non-goal. If a feature needs the user's
position on a course, it does not belong here.

## The design system

INDUSTRY, carried over from v1: paper ground, ink type, Barlow Condensed
over Barlow, DM Mono for every measured value, hairline blueprint cards with
corner registration marks, **square corners everywhere**, and the deep green
`--ci-field` as the **only** dark surface. Tokens live in
`caddieinsight/static/app.css` under `--ci-*` names; the palette values match
v1's `--sl-*` sheet. `tests/test_design_gates.py` pins the grammar — run it
before calling any visual change done, then look at the page anyway: a green
pin can sit on a broken layout.

Fonts are self-hosted (copied from v1's built set): Barlow 400/500,
Barlow Condensed 600, DM Mono 400/500 — five faces, and only those five.
Never reference Google Fonts at runtime.

## Honesty is a product rule

A number the user has not earned is never shown. No shots logged → "log
shots first", not a guessed distance. Thin data gets a thin-data grade;
stale data says it is stale. The caddie reports reach percentage, not
certainty. Keep this when adding features — it is the difference between
this product and a chart of manufacturer lofts.

## Shipping

Branch → PR → merge; keep CI green. The app is self-contained
(FastAPI + SQLite, stdlib crypto) — resist new dependencies.
