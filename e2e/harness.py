"""Viewer-agnostic plumbing for the browser end-to-end suite: generate a real
IIIF tree, serve it over HTTP, and inventory both what exists on disk and what a
client requested.

The clients themselves live in ``e2e/viewers``, one module per backend, and the
pure request-classification helpers live in ``e2e/requests``. Playwright is
imported for type checking only, so this module stays importable without the
``e2e`` dependency group, and nothing in ``magick_tile`` imports it.
"""

from __future__ import annotations

import http.server
import shutil
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from magick_tile.generator import SourceImage
from magick_tile.settings import IIIFVersions

from e2e.requests import TILE_SOURCE_PATH

if TYPE_CHECKING:
    from playwright.sync_api import ViewportSize

    from e2e.requests import AccessLog
    from e2e.viewers.base import ViewerState

HERE = Path(__file__).parent
FIXTURE_IMAGE = HERE / "fixtures" / "self-portrait_1937.1.72.jpg"
# One directory per backend; ``build_site`` copies the whole tree, so every
# backend page is served at ``/<backend>/index.html``.
VIEWER_DIR = HERE / "viewer"

TILE_SIZE = 512

VIEWPORT: ViewportSize = {"width": 1280, "height": 720}


@dataclass(frozen=True)
class Site:
    """One generated, served tile tree plus the record of what was requested."""

    version: IIIFVersions
    base_url: str
    site_root: Path
    # The server's own log, still being appended to while sweeps run.
    access_log: list[tuple[str, int]]
    source: SourceImage
    info: dict[str, Any]

    @property
    def tile_source_url(self) -> str:
        return f"/{TILE_SOURCE_PATH}/info.json"


@dataclass(frozen=True)
class Recording:
    """What one sweep observed: image responses, the access log, viewer state."""

    # Backend name and the requests that backend is allowed to miss.
    backend: str
    allowance: frozenset[str]
    # Normalized path -> (HTTP status, body length in bytes).
    requested: dict[str, tuple[int, int]]
    # Only the window this sweep produced, so one backend's tolerated failure
    # cannot decide another backend's run.
    access_log: AccessLog
    viewer_state: ViewerState
    dimensions: tuple[int, int]
    # (scale factor asked for, level the viewer drew) for every cell fit.
    cell_fits: list[tuple[int, float]]
    # Requests the offline interceptor refused because they left the server.
    blocked_requests: list[str]

    @property
    def requested_paths(self) -> set[str]:
        return set(self.requested)


class AccessLogWindow:
    """A live window onto one sweep's tail of the shared access log.

    Every sweep appends to the same server log, so each one reads only what it
    produced. That window has to read through to the log: a slice taken before
    the sweep runs is a copy, and the entries would never appear in it.
    """

    def __init__(self, log: list[tuple[str, int]], start: int) -> None:
        self._log = log
        self._start = start

    def _entries(self) -> list[tuple[str, int]]:
        # A snapshot, so the server thread appending mid-iteration is harmless.
        return self._log[self._start :]

    def __iter__(self) -> Iterator[tuple[str, int]]:
        return iter(self._entries())

    def __len__(self) -> int:
        return len(self._entries())


class StaticSiteServer:
    """Local static file server for the generated tree, with an access log.

    The socket is bound in the constructor so callers know the port before
    ``start()``: the tile URLs the viewer requests are built from the ``id``
    written into ``info.json``, and that id embeds the port.
    """

    def __init__(self, site_root: Path) -> None:
        self.site_root = site_root
        self.access_log: list[tuple[str, int]] = []
        access_log = self.access_log
        site_root_string = str(site_root)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, directory=site_root_string, **kwargs)

            def log_request(self, code: int | str = "-", size: int | str = "-"):
                if isinstance(code, int):
                    # Query strings are dropped so a logged path is comparable
                    # with the normalized paths the assertions use.
                    access_log.append((self.path.split("?", 1)[0], code))

            def log_message(self, format: str, *args) -> None:
                # The default writes to stderr on every request; the access log
                # list is the only record the tests need.
                pass

        # Port 0 asks the OS for a free port, and the threading variant keeps
        # the viewer's parallel tile requests from serializing.
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # shutdown() only returns while serve_forever() is running, so it is
        # skipped when the server was bound but never started.
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def build_site(site_root: Path, base_url: str, version: IIIFVersions) -> SourceImage:
    """Generate the tile tree for ``version`` under ``site_root``, alongside a
    copy of every viewer page so page and tiles share an origin."""
    shutil.copytree(VIEWER_DIR, site_root, dirs_exist_ok=True)
    source = SourceImage(
        # Must match the base of the URLs the viewer requests: clients build
        # tile URLs from this id, not from the URL info.json was fetched from.
        id=f"{base_url}/{TILE_SOURCE_PATH}",
        path=FIXTURE_IMAGE,
        tile_size=TILE_SIZE,
        target_dir=site_root / TILE_SOURCE_PATH,
        version=version,
    )
    source.convert()
    return source
