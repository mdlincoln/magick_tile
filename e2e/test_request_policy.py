"""What the viewers ask for beyond the generated pyramid.

The tree is a Level 0 service: a client is entitled to ask for a whole-image
derivative, and ``leaflet-iiif`` does, because it counts tiers from the image
dimensions instead of reading ``scaleFactors``. What a client may not do is
invent a tile the generator never wrote, which is what this module pins: the
observed out-of-pyramid set has to equal the frozen allowance exactly, so a new
URL fails as loudly as an allowance entry that stopped happening.

That allowance is empty for every combination, because the pyramid's top level is
the level those clients derive. The table stays as the pin, not as a tolerance.
"""

from collections import defaultdict

from e2e.harness import Recording, Site
from e2e.requests import classify_requested


def test_fixture_pyramid_declares_the_whole_image_level(site: Site) -> None:
    """The served fixture's pyramid really has the coarsest level the rest of
    the suite assumes.

    3202x4096 at tile 512 reaches the whole image in one tile at 8 * 512, so the
    level list has to end there. Without this check, an accidental return to the
    shorter-side rule would show up only as a pile of request-policy failures.
    """
    tile_size = site.info["tiles"][0]["width"]
    assert tile_size == 512
    assert site.info["tiles"][0]["scaleFactors"] == [1, 2, 4, 8]
    top = site.info["tiles"][0]["scaleFactors"][-1]
    assert top * tile_size >= max(site.info["width"], site.info["height"])


def test_out_of_pyramid_requests_match_allowance(
    site: Site, sweep_recording: Recording
) -> None:
    recording = sweep_recording
    observed = classify_requested(
        recording.requested, site.site_root, site.base_url, site.version
    ).out_of_pyramid
    assert observed == recording.allowance, (
        f"{recording.backend} on IIIF {site.version.value} requested "
        f"{len(observed)} paths outside the pyramid, {len(recording.allowance)} "
        f"allowed; unallowed: {sorted(observed - recording.allowance)}; "
        f"allowed but never requested: {sorted(recording.allowance - observed)}"
    )

    # Each tolerated path has to fail for the reason the allowance documents.
    statuses: dict[str, set[int]] = defaultdict(set)
    for path, (status, _length) in recording.requested.items():
        statuses[path].add(status)
    for path in sorted(recording.allowance):
        assert statuses.get(path) == {404}, (
            f"the allowance expects a 404 for {path}, saw {statuses.get(path)}"
        )


def test_in_pyramid_requests_resolve(site: Site, sweep_recording: Recording) -> None:
    """Nothing the tree does hold was requested in vain."""
    recording = sweep_recording
    in_pyramid = classify_requested(
        recording.requested, site.site_root, site.base_url, site.version
    ).in_pyramid
    refused = {
        path: status
        for path, (status, _length) in recording.requested.items()
        if path in in_pyramid and status != 200
    }
    assert not refused, f"generated tiles did not return 200: {refused}"
