"""OpenSeadragon backend: the suite's original client and its reference.

The page keeps ``window.__osd`` as the record of what OpenSeadragon did and
exposes the uniform ``window.__viewer`` view over it, so this adapter shares its
state shape with every other backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from e2e.viewers.base import OPEN_TIMEOUT_MS, READY_JS, ViewerState, read_state

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from e2e.harness import Site


class OpenSeadragon:
    """OpenSeadragon 6.1.1, driven through ``e2e/viewer/openseadragon``."""

    name = "openseadragon"
    page_path = "openseadragon/index.html"

    def open(self, page: Page, site: Site) -> None:
        page.goto(f"{site.base_url}/{self.page_path}?src={site.tile_source_url}")
        page.wait_for_function(READY_JS, timeout=OPEN_TIMEOUT_MS)
        open_failed = page.evaluate("() => window.__viewer.openFailed")
        assert open_failed is None, (
            f"OpenSeadragon could not open {site.tile_source_url}: {open_failed}"
        )

    def dimensions(self, page: Page) -> tuple[int, int]:
        """Image dimensions the viewer believes it is displaying."""
        dimensions = self.state(page).dimensions
        assert dimensions is not None, "the viewer reported no dimensions"
        return dimensions

    def home(self, page: Page, scale_factor: int) -> None:
        # OpenSeadragon picks its own home resolution; the argument is part of
        # the shared signature and is not used here.
        page.evaluate("() => window.__viewerHome()")

    def fit_cell(
        self, page: Page, cell: tuple[int, int, int, int], scale_factor: int
    ) -> None:
        page.evaluate(
            "([cell, factor]) => window.__viewerFit(cell, factor)",
            [list(cell), scale_factor],
        )

    def state(self, page: Page) -> ViewerState:
        return read_state(page)
