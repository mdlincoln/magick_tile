"""Fixtures for the browser end-to-end suite.

One generated tree per IIIF version is built and served for the whole session.
Each ``(version, backend)`` combination gets exactly one viewport sweep in
``sweep_recording``, and every assertion test inspects that recording instead of
driving a browser of its own.
"""

import json
from typing import Iterator
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, Page, Response, Route

from magick_tile.settings import IIIFVersions

from e2e.harness import (
    VIEWPORT,
    AccessLogWindow,
    Recording,
    Site,
    StaticSiteServer,
    build_site,
)
from e2e.requests import TILE_SOURCE_PATH, is_image_url, normalize
from e2e.viewers.base import ALLOWANCES, ViewerBackend, sweep
from e2e.viewers.leaflet import Leaflet
from e2e.viewers.openlayers import OpenLayers
from e2e.viewers.openseadragon import OpenSeadragon

BACKENDS: dict[str, ViewerBackend] = {
    backend.name: backend for backend in (OpenSeadragon(), OpenLayers(), Leaflet())
}


@pytest.fixture(
    scope="session",
    params=[IIIFVersions._3_0, IIIFVersions._2_1],
    ids=["3.0", "2.1"],
)
def site(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Site]:
    version: IIIFVersions = request.param
    site_root = tmp_path_factory.mktemp("site")
    # Bind the port before generating, then start serving afterwards: info.json
    # must carry the URL the page will request tiles from, and generating while
    # the socket is bound but idle keeps the port from being raced for.
    server = StaticSiteServer(site_root)
    try:
        source = build_site(site_root, server.base_url, version)
        server.start()
        info = json.loads((site_root / TILE_SOURCE_PATH / "info.json").read_text())
        yield Site(
            version=version,
            base_url=server.base_url,
            site_root=site_root,
            access_log=server.access_log,
            source=source,
            info=info,
        )
    finally:
        server.stop()


@pytest.fixture(scope="session", params=list(BACKENDS))
def viewer(request: pytest.FixtureRequest) -> ViewerBackend:
    return BACKENDS[request.param]


@pytest.fixture(scope="session")
def requested_by_backend() -> dict[IIIFVersions, dict[str, set[str]]]:
    """Every image path each backend requested, per version.

    A session-wide record so a test can make a claim that spans clients: one
    client asking only one spelling of a whole-image derivative is correct
    behaviour, so only the union over a version's backends covers both.
    ``sweep_recording`` fills it in.
    """
    return {version: {} for version in IIIFVersions}


@pytest.fixture(scope="session")
def sweep_recording(
    site: Site,
    viewer: ViewerBackend,
    browser: Browser,
    requested_by_backend: dict[IIIFVersions, dict[str, set[str]]],
) -> Iterator[Recording]:
    """One sweep of one backend over one version's tree."""
    allowance = ALLOWANCES[(viewer.name, site.version)]
    context = browser.new_context(viewport=VIEWPORT)
    page: Page = context.new_page()
    # Each sweep owns its collector; the response listener is the single source
    # of truth for which tile URLs the viewer actually requested.
    requested: dict[str, tuple[int, int]] = {}
    blocked: list[str] = []

    def record(response: Response) -> None:
        if not is_image_url(site.base_url, response.url):
            return
        # Reading the body inside a handler is not safe in the sync API, and
        # every response under test is a plain file served with a length.
        length = int(response.headers.get("content-length") or 0)
        requested[normalize(response.url)] = (response.status, length)

    def only_local(route: Route) -> None:
        # A page that reached the network would make the run depend on whatever
        # it fetched, so anything off the local server is refused. Comparing the
        # full host:port keeps a second local service from passing as "local". A
        # route handler that neither continues nor fulfils stalls the request,
        # hence the explicit continue_ for everything else.
        if urlparse(route.request.url).netloc != urlparse(site.base_url).netloc:
            blocked.append(route.request.url)
            route.abort()
            return
        route.continue_()

    page.on("response", record)
    # Installed before the first navigation so it sees the very first request.
    page.route("**/*", only_local)
    try:
        # Each sweep reads only its own window of the shared server log: one
        # backend's tolerated 404 must not abort another backend's run.
        window = AccessLogWindow(site.access_log, len(site.access_log))
        viewer.open(page, site)
        dimensions = viewer.dimensions(page)
        cell_fits = sweep(page, viewer, site, allowance, window)
        state = viewer.state(page)
        requested_by_backend[site.version][viewer.name] = set(requested)
        yield Recording(
            backend=viewer.name,
            allowance=allowance,
            requested=dict(requested),
            access_log=list(window),
            viewer_state=state,
            dimensions=dimensions,
            cell_fits=cell_fits,
            blocked_requests=list(blocked),
        )
    finally:
        context.close()
