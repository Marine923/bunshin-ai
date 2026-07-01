"""Regression tests for v0.10.14 photos_clusters admin regex.

The Wikipedia geosearch fallback picks a title using tiered priority
rules on the japanese admin suffix. v0.10.14 fixed a footgun where
"小栗村 (長崎県)" was skipped by an over-strict `(町|村|郡)$` because
the "村" was followed by " (長崎県)" not the end-of-string. The regex
now optionally allows a disambiguation-paren tail.

Also locks in the modern-admin tier so titles like "諫早市" outrank
titles like "小栗村" in the sort — Nominatim is the primary geocoder
now (v0.10.23) but this fallback still matters when Nominatim is
unreachable.
"""
import re


def _make_regexes():
    """Rebuilds the exact regex pair used in photos_clusters._wikipedia_place."""
    _dab_tail = r"(?:\s*[（(].+?[）)])?$"
    ja_modern_admin_re = re.compile(r"(市|区|県|府|都)" + _dab_tail)
    ja_old_admin_re = re.compile(r"(町|村|郡)" + _dab_tail)
    return ja_modern_admin_re, ja_old_admin_re


def test_modern_admin_matches_plain_and_disambiguated_titles():
    modern, _ = _make_regexes()
    # Plain
    assert modern.search("諫早市")
    assert modern.search("東京都")
    assert modern.search("北海道") is None, (
        "'道' isn't in the admin set — 北海道 shouldn't be picked as a "
        "photo-place cluster name (Wikipedia article for the prefecture)"
    )
    assert modern.search("諫早市 (長崎県)"), (
        "disambiguation tail with 市 should still match — Wikipedia often "
        "appends `(prefecture)` for city name collisions"
    )
    assert modern.search("諫早市（長崎県）"), (
        "full-width parens are the more common form for JA titles"
    )


def test_old_admin_matches_disambiguated_titles():
    """The v0.10.14 fix: 「小栗村 (長崎県)」was being skipped because the
    old regex `(町|村|郡)$` only matched at bare end-of-string."""
    _, old = _make_regexes()
    assert old.search("小栗村")
    assert old.search("小栗村 (長崎県)"), (
        "REGRESSION: this was the v0.10.14 fix — 「小栗村 (長崎県)」must "
        "match the ja_old_admin_re tier"
    )
    assert old.search("多比良町")
    assert old.search("玉名郡")
    assert old.search("玉名郡（熊本県）"), "full-width parens work"


def test_admin_regex_rejects_non_admin_titles():
    """Regex must not fire on titles that just contain the suffix as
    a substring but aren't administrative divisions."""
    modern, old = _make_regexes()
    # These pieces used to be false positives:
    assert modern.search("市立小栗小学校") is None, (
        "「学校」 suffix — school, not an admin. modern regex must reject."
    )
    assert old.search("PINCH HITTER JAPAN") is None
    assert old.search("Bunshin Memory") is None
    assert old.search("Latent Space") is None
    # These should still work — pathological but valid:
    assert old.search("小栗村（新潟県）"), (
        "same shape as the Nagasaki bug, different prefecture — pass"
    )


def test_admin_priority_order_modern_beats_old():
    """When both modern and old admin titles are present for the same
    coordinate, ja_modern_admin_re fires first — 「諫早市」 gets picked
    over 「小栗村 (長崎県)」 even though old-village Wikipedia article
    might be geographically closer to the GPS coordinate."""
    modern, old = _make_regexes()
    candidates = ["小栗村 (長崎県)", "諫早市", "県央広域組合"]
    # Simulate the pipeline: modern first, then old, then facility fallback
    modern_hit = next((c for c in candidates if modern.search(c)), None)
    old_hit = next((c for c in candidates if old.search(c)), None)
    assert modern_hit == "諫早市", (
        f"modern-admin tier should pick 諫早市 first — got {modern_hit}"
    )
    assert old_hit == "小栗村 (長崎県)", (
        f"old-admin tier does exist as fallback, but modern wins — "
        f"got old_hit={old_hit}"
    )
