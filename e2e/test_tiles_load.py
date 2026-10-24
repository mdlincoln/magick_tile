"""Browser acceptance tests for generated IIIF trees.

Each test runs once per (API version, viewer backend) combination. The sweep
itself runs once per combination in the ``sweep_recording`` fixture; the tests
only inspect what it recorded.

Requests the tree does not satisfy are not invisible here: they are pinned in
``e2e.viewers.base.ALLOWANCES`` and checked by ``test_request_policy.py``, so
these assertions can stay about the files the generator wrote.
"""

import math
from collections import defaultdict

import pytest
from playwright.sync_api import Page

from magick_tile.settings import IIIFVersions

from e2e.conftest import BACKENDS
from e2e.harness import Recording, Site
from e2e.requests import (
    DECLARED_SIZE_SEGMENT,
    TILE_SOURCE_PATH,
    classify_requested,
    declared_image_urls,
    disallowed_failures,
    failing_paths,
    normalize,
    region_tile_paths,
    whole_image_key,
)


def test_all_requested_tiles_load(site: Site, sweep_recording: Recording) -> None:
    """Every image the viewer asked for came back intact."""
    recording = sweep_recording
    # The viewer read the dimensions from info.json, so a mismatch means it is
    # looking at a different image than the one under test.
    assert recording.dimensions == (site.info["width"], site.info["height"])
    assert recording.requested, "the sweep requested no image files at all"

    classification = classify_requested(
        recording.requested, site.site_root, site.base_url, site.version
    )
    # What the tree owes a client: generated tiles and the derivatives that
    # info.json declares. Out-of-pyramid requests belong to the policy test.
    owed = classification.in_pyramid | classification.declared

    failed = {
        path: status
        for path, (status, _length) in recording.requested.items()
        if path in owed and status != 200
    }
    assert not failed, f"{len(failed)} image requests did not return 200: {failed}"

    empty = {
        path: length
        for path, (_status, length) in recording.requested.items()
        if path in owed and length <= 0
    }
    assert not empty, f"{len(empty)} image requests returned an empty body: {empty}"

    assert recording.viewer_state.open_failed is None
    assert disallowed_failures(recording.access_log, recording.allowance) == {}, (
        f"{recording.backend} requested a file the tree does not have"
    )

    logged = {
        path: status
        for path, status in failing_paths(recording.access_log).items()
        if path in classification.in_pyramid
    }
    assert not logged, f"server access log recorded failed image requests: {logged}"

    # Nothing is tolerated for any backend, so a client-side tile failure is a
    # real one: the coarsest level each client derives is a written file.
    assert recording.viewer_state.failures == [], (
        f"{recording.backend} recorded tile load failures: "
        f"{recording.viewer_state.failures[:3]}"
    )
    assert recording.viewer_state.loaded_count > 0, (
        "the viewer reported no completed tile loads"
    )


def test_all_generated_tiles_are_requested(
    site: Site, sweep_recording: Recording
) -> None:
    """The generated tree contains no tile the sweep failed to reach.

    Coverage is compared by whole-image key, not by raw path: the coarsest level
    is written under two spellings and each backend asks for one of them, so a
    level requested under only the other spelling is still covered. The paths in
    the failure messages are still on-disk paths, because a key names no file.
    """
    recording = sweep_recording
    width, height = site.info["width"], site.info["height"]

    def key(path: str) -> str:
        return whole_image_key(path, width, height)

    requested = {key(path) for path in recording.requested_paths}
    # A tile the viewer could not load stops the sweep, so report that first
    # instead of the coverage gap it caused.
    stopped = disallowed_failures(recording.access_log, recording.allowance)
    assert not stopped, (
        f"the sweep stopped after {len(stopped)} failed requests, "
        f"so coverage is incomplete: {stopped}"
    )

    on_disk = region_tile_paths(site.site_root)
    assert on_disk, "no region tiles were found in the generated tree"
    representative = {key(path): path for path in sorted(on_disk)}

    # Coverage per level first: a whole level the sweep never reached is the one
    # case the generic containment message below cannot name.
    per_level: dict[int, set[str]] = defaultdict(set)
    for tile in site.source.tiles:
        relative = tile.target_file.relative_to(site.site_root).as_posix()
        per_level[tile.sf].add(key(normalize(f"/{relative}")))
    for scale_factor in sorted(per_level, reverse=True):
        requested_at_level = per_level[scale_factor] & requested
        assert requested_at_level, (
            f"no tile at scale factor {scale_factor} "
            f"({len(per_level[scale_factor])} generated) was requested"
        )

    missing = sorted(
        representative[missing_key] for missing_key in representative.keys() - requested
    )
    assert not missing, (
        f"{len(missing)} of {len(on_disk)} generated tiles were never requested, "
        f"e.g. {missing[:5]}"
    )


def coarsest_level_spellings(site: Site) -> dict[str, str]:
    """The coarsest level's two paths: explicit region and canonical `full`."""
    info = site.info
    width, height = info["width"], info["height"]
    scale_factor = max(info["tiles"][0]["scaleFactors"])
    segment = DECLARED_SIZE_SEGMENT[site.version].format(
        w=math.ceil(width / scale_factor), h=math.ceil(height / scale_factor)
    )
    return {
        "region": f"/{TILE_SOURCE_PATH}/0,0,{width},{height}/{segment}/0/default.jpg",
        "full": f"/{TILE_SOURCE_PATH}/full/{segment}/0/default.jpg",
    }


def test_coarsest_level_resolves_where_requested(
    site: Site,
    sweep_recording: Recording,
) -> None:
    """The tree holds both spellings of the coarsest level, and whatever this
    client asked for came back intact.

    An empty allowance alone would let a half-write pass: a tree with only the
    explicit-region file still satisfies every client that canonicalizes the
    whole image to ``full`` — except the ones that do not. So the tree itself has
    to hold both files, and each spelling a client actually requested has to be
    200 with a body.
    """
    recording = sweep_recording
    spellings = coarsest_level_spellings(site)

    for name, path in sorted(spellings.items()):
        on_disk = site.site_root / path.lstrip("/")
        assert on_disk.exists(), f"coarsest level missing its {name} spelling {path}"

    requested_here = {
        path for path in spellings.values() if path in recording.requested
    }
    assert requested_here, (
        f"{recording.backend} requested neither spelling of the coarsest level "
        f"({', '.join(sorted(spellings.values()))})"
    )
    for path in sorted(requested_here):
        status, length = recording.requested[path]
        assert status == 200, f"{path} returned {status}"
        assert length > 0, f"{path} returned an empty body"


def test_both_coarsest_level_spellings_are_requested(
    site: Site,
    sweep_recording: Recording,
    requested_by_backend: dict[IIIFVersions, dict[str, set[str]]],
) -> None:
    """Both spellings of the coarsest level are exercised by a real client.

    No single client owes both requests — each asks for the spelling its own URL
    construction produces — so this is a claim about the union over the version's
    backends, and it is only decidable once they have all swept. The
    combinations that run before that skip with a visible message rather than
    passing: without the union, a `full` file no browser ever asks for would go
    unnoticed, since the per-client checks accept either spelling.
    """
    seen = requested_by_backend[site.version]
    if set(seen) < set(BACKENDS):
        pytest.skip(
            f"{len(seen)} of {len(BACKENDS)} backends have swept "
            f"{site.version.value}; the union is checked by the last of them"
        )

    union = set().union(*seen.values())
    unused = {
        name: path
        for name, path in coarsest_level_spellings(site).items()
        if path not in union
    }
    assert not unused, (
        f"no backend requested the coarsest level's "
        f"{', '.join(sorted(unused))} spelling: {unused}"
    )


def test_declared_sizes_and_full_size_resolve(site: Site, page: Page) -> None:
    """The full-image URLs info.json declares are served (no viewer asks for
    them, because none of them builds a pyramid from the sizes array)."""
    for url in sorted(declared_image_urls(site.site_root, site.base_url, site.version)):
        response = page.request.get(url)
        assert response.status == 200, f"{url} returned {response.status}"
        assert response.body(), f"{url} returned an empty body"
