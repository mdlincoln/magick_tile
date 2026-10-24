"""Every fit-to-cell move has to land on a level the generator wrote.

This is the self-diagnosing guard for each backend's fit convention: a wrong
coordinate or zoom mapping still renders something, and the damage shows up as
silent under-coverage — a pile of tiles nobody requested — unless the level the
viewer actually drew is checked against the pyramid.

The backends split in two. OpenLayers is asked for a resolution and leaflet-iiif
for a zoom, so each adapter asserts on the spot that the level it got back is
the scale factor the sweep asked for: the strongest form of this check, failing
at the offending fit instead of at the end of the sweep. OpenSeadragon is only
asked to fit a bounds and picks the closest level itself, so what holds for it
is that the level it drew is a level of the generated pyramid — its level index
to scale factor conversion is what is under test here.
"""

import math

from playwright.sync_api import Page

from e2e.harness import Recording, Site


def test_every_fit_landed_on_a_generated_level(
    site: Site, sweep_recording: Recording
) -> None:
    recording = sweep_recording
    assert recording.cell_fits, "the sweep recorded no fit-to-cell moves"

    generated = [float(sf) for sf in site.info["tiles"][0]["scaleFactors"]]
    off_level = [
        (asked, observed)
        for asked, observed in recording.cell_fits
        if not any(math.isclose(observed, sf) for sf in generated)
    ]
    assert not off_level, (
        f"{recording.backend} drew a level outside the generated pyramid "
        f"({sorted(generated)}) in {len(off_level)} of {len(recording.cell_fits)} "
        f"fits; e.g. (asked, drew) {off_level[:5]}"
    )


def test_library_top_matches_leaflet_tier_zero(site: Site, page: Page) -> None:
    """leaflet-iiif's own tier expression, evaluated in a browser, agrees with
    the pyramid's top level.

    The library derives its top level with integer arithmetic, and the client
    derives tier 0 with floating-point ``Math.log``. For the served fixture the
    longer side is exactly eight tiles (4096 / 512), which is where a
    ``ceil(log2(...))`` can overshoot, so the client's formula is evaluated as
    the client evaluates it — computing the expected value in Python here would
    compare the library's arithmetic with a Python reimplementation of it and
    miss exactly that boundary.
    """
    width, height = site.info["width"], site.info["height"]
    tile_size = site.info["tiles"][0]["width"]
    tier_zero = page.evaluate(
        """([w, h, tile]) => 2 ** Math.max(
            Math.ceil(Math.log(w / tile) / Math.LN2),
            Math.ceil(Math.log(h / tile) / Math.LN2),
            0
        )""",
        [width, height, tile_size],
    )
    assert tier_zero == max(site.info["tiles"][0]["scaleFactors"]), (
        f"leaflet-iiif derives tier 0 at scale {tier_zero} for {width}x{height} "
        f"at tile {tile_size}, but the pyramid's top level is "
        f"{max(site.info['tiles'][0]['scaleFactors'])}"
    )
