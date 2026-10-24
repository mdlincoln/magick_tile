"""Leaflet backend: leaflet-iiif's tile-URL construction against the tree.

leaflet-iiif derives its own tier count from the image dimensions and the tile
size rather than reading ``scaleFactors``, so it is the client that would notice
a pyramid whose top level is not the level where the whole image fits one tile.
Its tier-0 scale and the library's top level agree, and the request it makes at
that level resolves: the tree writes the level under the explicit-region
spelling as well as under ``full``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from e2e.viewers.base import OPEN_TIMEOUT_MS, READY_JS, ViewerState, read_state

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from e2e.harness import Site


class Leaflet:
    """Leaflet 1.9.4 with leaflet-iiif 3.0.0, driven through ``viewer/leaflet``."""

    name = "leaflet"
    page_path = "leaflet/index.html"

    def open(self, page: Page, site: Site) -> None:
        page.goto(f"{site.base_url}/{self.page_path}?src={site.tile_source_url}")
        page.wait_for_function(READY_JS, timeout=OPEN_TIMEOUT_MS)
        open_failed = page.evaluate("() => window.__viewer.openFailed")
        assert open_failed is None, (
            f"leaflet-iiif could not open {site.tile_source_url}: {open_failed}"
        )

    def dimensions(self, page: Page) -> tuple[int, int]:
        """Image dimensions leaflet-iiif computed from info.json."""
        dimensions = self.state(page).dimensions
        assert dimensions is not None, "the viewer reported no dimensions"
        return dimensions

    def home(self, page: Page, scale_factor: int) -> None:
        # The page fits the whole image and ignores the scale factor on purpose:
        # leaflet-iiif's coarsest tier is the pyramid's top level, and a home fit
        # is how the sweep exercises the whole-image request under the
        # explicit-region spelling.
        page.evaluate("() => window.__viewerHome()")

    def fit_cell(
        self, page: Page, cell: tuple[int, int, int, int], scale_factor: int
    ) -> None:
        observed = page.evaluate(
            "([cell, factor]) => window.__viewerFit(cell, factor)",
            [list(cell), scale_factor],
        )
        assert observed is not None, "the leaflet page was not ready for a fit"
        # A wrong lat/lng convention or zoom direction still renders something,
        # so the level is checked against the request here rather than being
        # discovered later as a coverage gap.
        assert abs(observed - scale_factor) < 1e-9, (
            f"a fit to scale factor {scale_factor} landed on scale {observed}: "
            "the page's zoom-to-scale mapping or its lat/lng convention is wrong"
        )

    def state(self, page: Page) -> ViewerState:
        return read_state(page)
