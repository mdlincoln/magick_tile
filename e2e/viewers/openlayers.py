"""OpenLayers backend: an IIIF-aware client with its own deep-zoom engine.

OpenLayers builds the pyramid from ``info.json``'s ``tiles`` and
``scaleFactors`` itself, so its URL set is an independent opinion about what the
generated tree should contain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from e2e.viewers.base import OPEN_TIMEOUT_MS, READY_JS, ViewerState, read_state

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from e2e.harness import Site


class OpenLayers:
    """OpenLayers 10.11.0, driven through ``e2e/viewer/openlayers``."""

    name = "openlayers"
    page_path = "openlayers/index.html"

    def open(self, page: Page, site: Site) -> None:
        page.goto(f"{site.base_url}/{self.page_path}?src={site.tile_source_url}")
        page.wait_for_function(READY_JS, timeout=OPEN_TIMEOUT_MS)
        open_failed = page.evaluate("() => window.__viewer.openFailed")
        assert open_failed is None, (
            f"OpenLayers could not open {site.tile_source_url}: {open_failed}"
        )

    def dimensions(self, page: Page) -> tuple[int, int]:
        """Image dimensions the viewer parsed out of info.json."""
        dimensions = self.state(page).dimensions
        assert dimensions is not None, "the viewer reported no dimensions"
        return dimensions

    def home(self, page: Page, scale_factor: int) -> None:
        page.evaluate("(factor) => window.__viewerHome(factor)", scale_factor)

    def fit_cell(
        self, page: Page, cell: tuple[int, int, int, int], scale_factor: int
    ) -> None:
        observed = page.evaluate(
            "([cell, factor]) => window.__viewerFit(cell, factor)",
            [list(cell), scale_factor],
        )
        # The view resolution is the level, so a clamp or a view that ignored
        # the setter shows up here rather than as a coverage gap later.
        assert observed is not None, "the OpenLayers page was not ready for a fit"
        assert abs(observed - scale_factor) < 1e-9, (
            f"a fit to scale factor {scale_factor} landed on resolution "
            f"{observed}: the view did not take the level it was given"
        )

    def state(self, page: Page) -> ViewerState:
        return read_state(page)
