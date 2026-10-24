"""The viewer-backend seam: settle, sweep and the request allowance.

A backend pairs a Python adapter with a static page at
``e2e/viewer/<name>/index.html`` that exposes the same ``window.__viewer``
contract, so tests read a uniform state object instead of reaching into each
library's internals. Everything in this module is viewer-agnostic: the poll that
waits for a view to settle, the sweep that walks the whole pyramid, and the
table of requests the suite tolerates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from e2e.requests import AccessLog, disallowed_failures, tile_grid
from magick_tile.settings import IIIFVersions

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from e2e.harness import Site

# The sweep's fit-to-cell moves resolve to a tile level through the viewport
# height, so the viewport is pinned to keep coverage reproducible.
OPEN_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_SECONDS = 15.0
SETTLE_POLL_SECONDS = 0.05
SETTLE_STABLE_POLLS = 3

# Readiness for the first poll: the page either opened the tile source or
# recorded why it could not.
READY_JS = """() => window.__viewer.opened || window.__viewer.openFailed !== null"""

# Two animation frames let the viewer enqueue the tiles for the new view.
DOUBLE_FRAME_JS = """() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
})"""


@dataclass
class ViewerState:
    """What every viewer page reports about itself, in one shape."""

    opened: bool
    open_failed: str | None
    loaded_count: int
    failures: list[dict[str, Any]]
    idle: bool
    dimensions: tuple[int, int] | None
    # The scale factor the viewer is currently drawing, as the adapter
    # translates its own resolution/zoom into the pyramid's terms.
    level: float | None


class ViewerBackend(Protocol):
    """One IIIF client, driven through its page and read through its state."""

    name: str
    # Page path under the served site root, e.g. "openlayers/index.html".
    page_path: str

    def open(self, page: Page, site: Site) -> None: ...

    def dimensions(self, page: Page) -> tuple[int, int]: ...

    def home(self, page: Page, scale_factor: int) -> None: ...

    def fit_cell(
        self, page: Page, cell: tuple[int, int, int, int], scale_factor: int
    ) -> None: ...

    def state(self, page: Page) -> ViewerState: ...


# The uniform state object every backend page exposes as ``window.__viewer``.
STATE_JS = """() => ({
    opened: window.__viewer.opened,
    openFailed: window.__viewer.openFailed,
    loadedCount: window.__viewer.loadedCount,
    failures: window.__viewer.failed,
    idle: window.__viewer.idle,
    dimensions: window.__viewer.dimensions,
    level: window.__viewer.level,
})"""


def read_state(page: Page) -> ViewerState:
    """Read one page's ``window.__viewer`` into a :class:`ViewerState`."""
    state = page.evaluate(STATE_JS)
    dimensions = state["dimensions"]
    return ViewerState(
        opened=state["opened"],
        open_failed=state["openFailed"],
        loaded_count=state["loadedCount"],
        failures=state["failures"],
        idle=state["idle"],
        dimensions=(dimensions[0], dimensions[1]) if dimensions else None,
        level=state["level"],
    )


# Requests each backend is allowed to make that the generated tree does not
# satisfy, keyed by backend name and API version, as normalized paths.
#
# The table is deliberately the single copy of these paths: sweep control flow
# (``settle`` and ``sweep`` below) and the request-policy assertions both read
# it, so the suite cannot tolerate something one place and fail it in another.
#
# It is empty for every combination, and that is the assertion: no client asks
# for anything the tree does not hold. What closed the last gap was the
# generator writing its coarsest level at the tier-0 scale such clients derive,
# under both spellings of the whole image. leaflet-iiif ignores info.json's
# scaleFactors and counts tiers from the image dimensions and the tile size:
#
#     maxNativeZoom = max(ceilLog2(3202 / 512), ceilLog2(4096 / 512), 0) = 3
#     tier 0 scale  = 2 ** (maxNativeZoom - 0) = 8
#
# The pyramid's top level is now scale 8, so the whole image requested as one
# tile at that scale — region 0,0,3202,4096 with size ceil(3202/8) = 401 by
# ceil(4096/8) = 512 — is a written file. OpenSeadragon and OpenLayers, which
# canonicalize that region to `full`, get their own copy at full/401,512 (3.0)
# or full/401, (2.1).
#
# The empty table stays rather than being deleted with the machinery: it is what
# makes a future out-of-pyramid request fail loudly, and `sweep`/`settle` still
# consult it.
ALLOWANCES: dict[tuple[str, IIIFVersions], frozenset[str]] = {
    ("openseadragon", IIIFVersions._3_0): frozenset(),
    ("openseadragon", IIIFVersions._2_1): frozenset(),
    ("openlayers", IIIFVersions._3_0): frozenset(),
    ("openlayers", IIIFVersions._2_1): frozenset(),
    ("leaflet", IIIFVersions._3_0): frozenset(),
    ("leaflet", IIIFVersions._2_1): frozenset(),
}


def settle(
    page: Page,
    backend: ViewerBackend,
    allowance: frozenset[str],
    access_log: AccessLog,
) -> ViewerState:
    """Wait until the current view's tiles have loaded.

    An image request the run does not tolerate returns immediately, so the
    caller reports the offending path instead of timing out. Idleness has to
    hold for several consecutive polls because a viewer can still describe the
    previous view for a frame or two after a viewport change.
    """
    page.wait_for_function(READY_JS, timeout=OPEN_TIMEOUT_MS)
    page.evaluate(DOUBLE_FRAME_JS)
    deadline = time.monotonic() + SETTLE_TIMEOUT_SECONDS
    stable = 0
    while time.monotonic() < deadline:
        if disallowed_failures(access_log, allowance):
            return backend.state(page)
        state = backend.state(page)
        if state.idle:
            stable += 1
            if stable >= SETTLE_STABLE_POLLS:
                return state
        else:
            stable = 0
        time.sleep(SETTLE_POLL_SECONDS)
    raise AssertionError(
        f"{backend.name} did not settle within {SETTLE_TIMEOUT_SECONDS}s; "
        f"state: {backend.state(page)}; "
        f"failed requests: {disallowed_failures(access_log, allowance)}"
    )


def sweep(
    page: Page,
    backend: ViewerBackend,
    site: Site,
    allowance: frozenset[str],
    access_log: AccessLog,
) -> list[tuple[int, float]]:
    """Walk the whole image at every generated scale factor.

    Each move fits one tile-aligned cell, so the viewer requests exactly the
    tiles of that cell rather than whatever a blind pan happens to expose.
    Coarsest level first, matching how a reader arrives at the image.

    Returns the ``(scale factor asked for, level observed)`` pairs for the cell
    fits only: a home fit is not recorded, because a backend's home view may
    legitimately land somewhere the sweep never asks for.
    """
    info = site.info
    width, height = info["width"], info["height"]
    tile_size = info["tiles"][0]["width"]
    scale_factors = info["tiles"][0]["scaleFactors"]
    coarsest = max(scale_factors)
    cell_fits: list[tuple[int, float]] = []

    backend.home(page, coarsest)
    settle(page, backend, allowance, access_log)
    for scale_factor in sorted(scale_factors, reverse=True):
        for cell in tile_grid(width, height, tile_size * scale_factor):
            backend.fit_cell(page, cell, scale_factor)
            state = settle(page, backend, allowance, access_log)
            if state.level is not None:
                cell_fits.append((scale_factor, state.level))
            if disallowed_failures(access_log, allowance):
                # One unreachable tile decides the run already; walking the
                # rest of the grid would only repeat the same failure.
                return cell_fits
    backend.home(page, coarsest)
    settle(page, backend, allowance, access_log)
    return cell_fits
