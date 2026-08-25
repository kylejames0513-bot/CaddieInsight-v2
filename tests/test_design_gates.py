"""Design gates: pins for the INDUSTRY grammar.

A green pin can sit on a broken layout — these hold the grammar, not the
page. Look at the rendered page too before calling a visual change done.
"""

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "caddieinsight"
CSS = (PACKAGE / "static" / "app.css").read_text()
TEMPLATES = {
    path.name: path.read_text()
    for path in (PACKAGE / "templates").glob("*.j2")
}

# The palette, byte-for-byte the values v1 ships as --sl-*.
PALETTE_PINS = {
    "--ci-bg: #f2f2f3": "the paper ground",
    "--ci-ink: #1d1f20": "primary type",
    "--ci-btn: #2c455d": "the one solid object",
    "--ci-signal: #416180": "the signal — a measured value",
    "--ci-steel: #5980a6": "structure",
    "--ci-trace: #94bce3": "the live read",
    "--ci-field: #070f0b": "the one reversed ground",
    "--ci-band: #1d2d3d": "the announcement strip",
    "--ci-control-border: #7a7a7d": "interactive edges (WCAG 1.4.11)",
}


def test_palette_tokens_pin_the_industry_values():
    for pin, why in PALETTE_PINS.items():
        assert pin in CSS, f"missing {pin} ({why})"


def test_square_corners_everywhere():
    # A radius is a foreign object in this grammar. No border-radius at
    # all — not even 0, which invites someone to change the value.
    assert "border-radius" not in CSS
    for name, text in TEMPLATES.items():
        assert "border-radius" not in text, name


def test_decorative_and_control_borders_stay_distinct():
    decorative = re.search(r"--ci-border:\s*(#\w+)", CSS).group(1)
    control = re.search(r"--ci-control-border:\s*(#\w+)", CSS).group(1)
    assert decorative != control


def test_the_field_is_defined_once():
    # One reversed ground: the field hex exists only as its token
    # definition. Surfaces opt in through var(--ci-field), never by
    # respelling the colour.
    assert CSS.count("#070f0b") == 1


def test_no_google_fonts_at_runtime():
    for name, text in TEMPLATES.items():
        assert "fonts.googleapis" not in text, name
        assert "fonts.gstatic" not in text, name
    assert "fonts.googleapis" not in CSS


def test_exactly_five_self_hosted_faces():
    faces = re.findall(r"@font-face", CSS)
    assert len(faces) == 5
    fonts_dir = PACKAGE / "static" / "fonts"
    woff2 = sorted(p.name for p in fonts_dir.glob("*.woff2"))
    assert woff2 == [
        "barlow-condensed-latin-600.woff2",
        "barlow-latin-400.woff2",
        "barlow-latin-500.woff2",
        "dm-mono-latin-400.woff2",
        "dm-mono-latin-500.woff2",
    ]


def test_breakpoints_come_from_the_four_stops():
    widths = re.findall(r"@media\s*\((min|max)-width:\s*(\d+)px\)", CSS)
    allowed = {("min", "560"), ("min", "750"), ("min", "1000"),
               ("min", "1280"), ("max", "559"), ("max", "749"),
               ("max", "999")}
    assert set(widths) <= allowed, sorted(set(widths) - allowed)


def test_theme_color_is_a_literal():
    # <meta name="theme-color"> is parsed by browser chrome, not the
    # CSSOM — a var() there is discarded silently.
    layout = TEMPLATES["layout.html.j2"]
    match = re.search(r'name="theme-color" content="([^"]+)"', layout)
    assert match, "layout must carry a theme-color"
    assert match.group(1).startswith("#"), "theme-color must be a literal"


def test_every_page_extends_the_layout():
    for name, text in TEMPLATES.items():
        if name in ("layout.html.j2", "macros.html.j2"):
            continue
        assert 'extends "layout.html.j2"' in text, name


def test_measured_values_are_mono():
    # The carry a club earned is a measured value: mono face, signal
    # colour, paper side. These classes travel together in the bag list
    # and the ladder.
    assert "ci-baglist__carry ci-mono ci-signal" in TEMPLATES["bag.html.j2"]
    assert "ci-ladder__carry ci-mono ci-signal" in TEMPLATES["macros.html.j2"]


def test_the_verdict_readout_is_field_ink_not_signal():
    # On the field a measured value is set in field ink — the signal is
    # 3.00:1 there and unreadable. The pin holds the rule.
    verdict = re.search(
        r"\.ci-verdict__plays\s*\{[^}]+\}", CSS
    ).group(0)
    assert "var(--ci-field-ink)" in verdict
    assert "--ci-signal" not in verdict


def test_no_page_scripts_beyond_the_service_worker():
    # Every page renders complete without JavaScript. The only script the
    # layout ships is the service-worker registration.
    layout = TEMPLATES["layout.html.j2"]
    assert layout.count("<script>") == 1
    assert "serviceWorker" in layout
    for name, text in TEMPLATES.items():
        if name != "layout.html.j2":
            assert "<script" not in text, name
