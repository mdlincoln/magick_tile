"""Unit tests for the browser suite's pure request helpers.

``e2e/requests.py`` takes only paths, URLs, an on-disk tree and access-log
entries, so the partition rules, the on-disk inventory and the request-to-level
arithmetic are checked in the default run — no Playwright, no browser, and no
generated tiles required.
"""

import json
from itertools import combinations
from pathlib import Path

import pytest

from magick_tile.settings import IIIFVersions

from e2e.requests import (
    TILE_SOURCE_PATH,
    classify_requested,
    classify_requests,
    declared_image_urls,
    disallowed_failures,
    failing_paths,
    image_requests,
    is_image_url,
    is_region_segment,
    normalize,
    region_tile_paths,
    tile_grid,
    whole_image_key,
)

BASE_URL = "http://127.0.0.1:8000"
TILE = f"/{TILE_SOURCE_PATH}/0,0,512,512/512,512/0/default.jpg"
OTHER_TILE = f"/{TILE_SOURCE_PATH}/512,0,512,512/512,512/0/default.jpg"
# Declared by info.json: a canonical full-image derivative, not a generated tile.
DECLARED = f"/{TILE_SOURCE_PATH}/full/max/0/default.jpg"
# Looks like a tile, is under the tile prefix, but this fixture's 512x512 image
# never yields it: the whole image at scale 8 of a larger picture. It is a
# generated path in a real tree, so it works here only because the miniature
# service below is 512x512, which makes the region a partial one.
INVENTED = f"/{TILE_SOURCE_PATH}/0,0,3202,4096/401,512/0/default.jpg"


@pytest.fixture
def site_root(tmp_path: Path) -> Path:
    """A miniature generated service: one region tile, one full derivative, and
    an info.json that declares one size."""
    service = tmp_path / TILE_SOURCE_PATH
    for relative in ("0,0,512,512/512,512/0", "full/max/0"):
        (service / relative).mkdir(parents=True)
        (service / relative / "default.jpg").write_bytes(b"tile")
    info = {"width": 512, "height": 512, "sizes": [{"width": 256, "height": 224}]}
    (service / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return tmp_path


def buckets(classification) -> list[frozenset[str]]:
    return [
        classification.in_pyramid,
        classification.declared,
        classification.out_of_pyramid,
    ]


def test_classify_partitions_exactly() -> None:
    recorded = [TILE, OTHER_TILE, DECLARED, INVENTED]
    classification = classify_requests(
        recorded,
        on_disk={TILE, OTHER_TILE},
        declared={f"{BASE_URL}{DECLARED}"},
    )

    assert classification.in_pyramid == {TILE, OTHER_TILE}
    assert classification.declared == {DECLARED}
    assert classification.out_of_pyramid == {INVENTED}

    # No path in two buckets, and none dropped.
    for left, right in combinations(buckets(classification), 2):
        assert not left & right
    assert sum(len(bucket) for bucket in buckets(classification)) == len(recorded)
    assert classification.requested == set(recorded)


def test_unknown_tile_path_is_out_of_pyramid() -> None:
    """A path under the tile prefix is only in the pyramid if it is on disk."""
    classification = classify_requests([INVENTED], on_disk={TILE}, declared={DECLARED})
    assert classification.in_pyramid == frozenset()
    assert classification.out_of_pyramid == {INVENTED}


def test_region_tile_paths_ignores_full_derivatives(site_root: Path) -> None:
    assert region_tile_paths(site_root) == {TILE}


def test_is_region_segment() -> None:
    assert is_region_segment("0,0,512,512")
    assert is_region_segment("3072,2048,130,2048")
    assert not is_region_segment("full")
    assert not is_region_segment("512,512")
    assert not is_region_segment("1,2,3,x")


def test_declared_image_urls_uses_the_canonical_size_form(site_root: Path) -> None:
    """3.0 declares sizes as w,h and the unscaled image as max; 2.1 uses w, and
    full. A regression here would make every declared URL a 404."""
    three = declared_image_urls(site_root, BASE_URL, IIIFVersions._3_0)
    assert three == {
        f"{BASE_URL}/{TILE_SOURCE_PATH}/full/max/0/default.jpg",
        f"{BASE_URL}/{TILE_SOURCE_PATH}/full/256,224/0/default.jpg",
    }

    two = declared_image_urls(site_root, BASE_URL, IIIFVersions._2_1)
    assert two == {
        f"{BASE_URL}/{TILE_SOURCE_PATH}/full/full/0/default.jpg",
        f"{BASE_URL}/{TILE_SOURCE_PATH}/full/256,/0/default.jpg",
    }


def test_classify_requested_reads_the_tree_and_info_json(site_root: Path) -> None:
    classification = classify_requested(
        [TILE, DECLARED, INVENTED], site_root, BASE_URL, IIIFVersions._3_0
    )
    assert classification.in_pyramid == {TILE}
    assert classification.declared == {DECLARED}
    assert classification.out_of_pyramid == {INVENTED}


@pytest.fixture
def large_site_root(tmp_path: Path) -> Path:
    """A miniature service at the e2e fixture's dimensions, holding the
    coarsest level under both spellings."""
    service = tmp_path / TILE_SOURCE_PATH
    for relative in ("0,0,3202,4096/401,512/0", "full/401,512/0", "full/max/0"):
        (service / relative).mkdir(parents=True)
        (service / relative / "default.jpg").write_bytes(b"tile")
    info = {
        "width": 3202,
        "height": 4096,
        "sizes": [{"width": 256, "height": 327}],
    }
    (service / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return tmp_path


@pytest.fixture
def region_spelling() -> str:
    return f"/{TILE_SOURCE_PATH}/0,0,3202,4096/401,512/0/default.jpg"


@pytest.fixture
def full_spelling() -> str:
    return f"/{TILE_SOURCE_PATH}/full/401,512/0/default.jpg"


def test_whole_image_key_maps_both_spellings(
    region_spelling: str, full_spelling: str
) -> None:
    assert whole_image_key(region_spelling, 3202, 4096) == full_spelling
    assert whole_image_key(full_spelling, 3202, 4096) == full_spelling


def test_whole_image_key_leaves_other_paths_alone() -> None:
    # A partial region is a different file, whatever its size directory says.
    partial = f"/{TILE_SOURCE_PATH}/0,0,512,512/512,512/0/default.jpg"
    assert whole_image_key(partial, 3202, 4096) == partial
    # The whole image at its unscaled size keeps its keyword: full/max is not
    # the coarsest level, and neither is the 2.1 spelling of it.
    for unscaled in (
        f"/{TILE_SOURCE_PATH}/full/max/0/default.jpg",
        f"/{TILE_SOURCE_PATH}/full/full/0/default.jpg",
    ):
        assert whole_image_key(unscaled, 3202, 4096) == unscaled
    # A page or a non-image path has no region segment to rewrite.
    assert whole_image_key("/leaflet/index.html", 3202, 4096) == "/leaflet/index.html"


def test_classify_requested_accepts_either_spelling(
    large_site_root: Path, region_spelling: str, full_spelling: str
) -> None:
    classification = classify_requested(
        [region_spelling, full_spelling], large_site_root, BASE_URL, IIIFVersions._3_0
    )
    # Both buckets keep the requested paths, not the shared key, so a caller
    # looking up a path's status still finds it.
    assert classification.in_pyramid == {region_spelling, full_spelling}
    assert classification.out_of_pyramid == frozenset()


def test_classify_requested_keeps_a_missing_spelling_visible(
    tmp_path: Path, full_spelling: str
) -> None:
    """A half-written level is still the tree's problem, not a pass.

    Here the tree holds only the explicit-region spelling, as a regression that
    dropped the ``full`` writer would leave it. The request for the missing
    spelling still classifies as in-pyramid — it names the same level — and the
    404 it recorded is then what ``test_in_pyramid_requests_resolve`` reports.
    Equivalence must not turn the absence into an out-of-pyramid request that
    nobody owns.
    """
    service = tmp_path / TILE_SOURCE_PATH
    region_dir = service / "0,0,3202,4096" / "401,512" / "0"
    region_dir.mkdir(parents=True)
    (region_dir / "default.jpg").write_bytes(b"tile")
    (service / "info.json").write_text(
        json.dumps({"width": 3202, "height": 4096, "sizes": []}), encoding="utf-8"
    )
    assert not (service / "full" / "401,512" / "0" / "default.jpg").exists()

    classification = classify_requested(
        [full_spelling], tmp_path, BASE_URL, IIIFVersions._3_0
    )
    assert classification.in_pyramid == {full_spelling}
    refused = {
        path: status
        for path, status in {full_spelling: 404}.items()
        if path in classification.in_pyramid and status != 200
    }
    assert refused == {full_spelling: 404}


def test_classify_requests_without_dimensions_keeps_paths_distinct(
    region_spelling: str, full_spelling: str
) -> None:
    """The equivalence is opt-in, so the pre-existing callers keep their
    meaning: a path is only generated if it is on disk."""
    classification = classify_requests(
        [region_spelling, full_spelling], on_disk={region_spelling}, declared=set()
    )
    assert classification.in_pyramid == {region_spelling}
    assert classification.out_of_pyramid == {full_spelling}


def test_is_image_url_requires_the_tile_prefix_and_an_image_suffix() -> None:
    assert is_image_url(BASE_URL, f"{BASE_URL}{TILE}")
    assert not is_image_url(BASE_URL, f"{BASE_URL}/openlayers/vendor/ol-10.11.0.css")
    assert not is_image_url(BASE_URL, f"{BASE_URL}/{TILE_SOURCE_PATH}/info.json")
    # Same path, different server: not this site's image.
    assert not is_image_url("http://127.0.0.1:9999", f"{BASE_URL}{TILE}")


def test_tile_grid_covers_partial_edge_cells() -> None:
    assert tile_grid(1200, 300, 512) == [
        (0, 0, 512, 300),
        (512, 0, 512, 300),
        (1024, 0, 176, 300),
    ]


def test_image_requests_ignores_files_outside_the_tile_prefix() -> None:
    access_log = [
        (TILE, 200),
        ("/favicon.ico", 404),
        ("/openlayers/vendor/ol-10.11.0.css", 404),
        (f"/{TILE_SOURCE_PATH}/info.json", 200),
    ]
    assert image_requests(access_log) == [(TILE, 200)]
    assert failing_paths(access_log) == {}


def test_disallowed_failures_ignores_allowance() -> None:
    access_log = [
        (TILE, 404),
        (OTHER_TILE, 200),
        (DECLARED, 500),
        (INVENTED, 404),
        ("/favicon.ico", 404),
    ]
    failures = failing_paths(access_log)
    assert failures == {TILE: 404, DECLARED: 500, INVENTED: 404}

    assert disallowed_failures(access_log, frozenset({TILE})) == {
        DECLARED: 500,
        INVENTED: 404,
    }


def test_normalize_strips_origin_query_and_escapes() -> None:
    url = f"{BASE_URL}{TILE}?v=2"
    assert normalize(url) == TILE
