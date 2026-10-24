"""Pure path and access-log helpers for the browser end-to-end suite.

Everything here works on primitives — paths, URLs and access-log entries — and
takes no ``Site``: nothing in this module imports the harness or Playwright, so
the default unit run can test these functions without the ``e2e`` dependency
group, and the harness can import this module without an import cycle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Protocol
from urllib.parse import unquote, urlparse

from magick_tile.settings import IIIFVersions

# Path prefix (relative to the site root) of the generated image service.
TILE_SOURCE_PATH = "iiif/self-portrait"

# Canonical full-size directory: Image API 3.0 §4.8 uses "max"; 2.1 §4.2 used
# "full".
FULL_SIZE_SEGMENT: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "max",
    IIIFVersions._2_1: "full",
}

# Canonical size-directory form for the full-image derivatives: 3.0 §4.8
# declares canonical sizes as w,h, while 2.1 §5.2 uses w,.
DECLARED_SIZE_SEGMENT: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "{w},{h}",
    IIIFVersions._2_1: "{w},",
}

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".gif", ".jp2", ".webp")


# An access log as the static server records it: request path and status code.
# A protocol rather than a list so a sweep can read a live window onto the
# server's shared log instead of a copy taken before the sweep ran.
class AccessLog(Protocol):
    def __iter__(self) -> Iterator[tuple[str, int]]: ...

    def __len__(self) -> int: ...


@dataclass(frozen=True)
class RequestClassification:
    """Requested paths, split by what the generated tree says they are.

    ``in_pyramid`` paths are generated region tiles, ``declared`` paths are the
    full-image derivatives ``info.json`` advertises, and ``out_of_pyramid`` is
    everything else — the bucket a client asking for a level or region the
    generator never wrote lands in.
    """

    in_pyramid: frozenset[str]
    declared: frozenset[str]
    out_of_pyramid: frozenset[str]

    @property
    def requested(self) -> frozenset[str]:
        return self.in_pyramid | self.declared | self.out_of_pyramid


def normalize(url: str) -> str:
    """Reduce a URL to the path the static server serves it from."""
    return unquote(urlparse(url).path)


def is_image_url(base_url: str, url: str) -> bool:
    """True for an image file under the tile-source prefix."""
    return url.startswith(f"{base_url}/{TILE_SOURCE_PATH}/") and url.lower().endswith(
        IMAGE_SUFFIXES
    )


def is_region_segment(segment: str) -> bool:
    """True for ``{x,y,w,h}`` region directories, false for ``full``."""
    parts = segment.split(",")
    return len(parts) == 4 and all(part.isdigit() for part in parts)


def region_tile_paths(site_root: Path) -> set[str]:
    """Every region tile file on disk, as normalized paths.

    Reads the generated tree rather than the library's bookkeeping, so it is an
    independent inventory of what a viewer is entitled to ask for.
    """
    tiles: set[str] = set()
    for path in (site_root / TILE_SOURCE_PATH).rglob("default.*"):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative = path.relative_to(site_root)
        # iiif/self-portrait/{region}/{size}/0/default.jpg
        if not is_region_segment(relative.parts[2]):
            continue
        tiles.add(f"/{relative.as_posix()}")
    return tiles


def read_info(site_root: Path) -> dict:
    """The generated image service's info.json payload."""
    return json.loads((site_root / TILE_SOURCE_PATH / "info.json").read_text())


def declared_image_urls(
    site_root: Path, base_url: str, version: IIIFVersions
) -> set[str]:
    """URLs info.json declares that no tiled request exercises: the declared
    full-image sizes and the unscaled full image."""
    info = read_info(site_root)
    urls = {
        f"{base_url}/{TILE_SOURCE_PATH}/full/{FULL_SIZE_SEGMENT[version]}/0/default.jpg"
    }
    for size in info["sizes"]:
        segment = DECLARED_SIZE_SEGMENT[version].format(
            w=size["width"], h=size["height"]
        )
        urls.add(f"{base_url}/{TILE_SOURCE_PATH}/full/{segment}/0/default.jpg")
    return urls


def whole_image_key(path: str, width: int, height: int) -> str:
    """The whole image in a size directory, whichever region spelling names it.

    ``full/{size}/0/default.jpg`` and ``0,0,{width},{height}/{size}/0/default.jpg``
    are two spellings of one derivative, not two files a client may pick
    between. Image API 3.0 §4.4 makes ``full`` the canonical region form for the
    whole image in both API versions, so a dynamic server redirects the explicit
    region to it; a static tree cannot redirect and writes both paths instead.
    Clients do not canonicalize consistently, so the suite has to treat a
    request for either spelling as a request for the same level.

    §4.8 is what makes the size directory comparable: the same requested
    ``{w},{h}`` (3.0) or ``{w},`` (2.1) segment appears in both spellings.

    Only a region naming the whole image is rewritten. A partial region, a
    declared ``sizes`` derivative, or ``full/max`` keeps its own path, because
    those are genuinely different files.
    """
    parts = path.split("/")
    if len(parts) < 4:
        return path
    region = parts[-4]
    if region == "full" or region == f"0,0,{width},{height}":
        parts[-4] = "full"
        return "/".join(parts)
    return path


def image_requests(access_log: AccessLog) -> list[tuple[str, int]]:
    """Access-log entries for generated image files under the tile prefix."""
    prefix = f"/{TILE_SOURCE_PATH}/"
    return [
        (path, status)
        for path, status in access_log
        if path.startswith(prefix) and path.lower().endswith(IMAGE_SUFFIXES)
    ]


def failing_paths(access_log: AccessLog) -> dict[str, int]:
    """Image requests that did not return 2xx, as ``path -> status``.

    Restricted to the tile prefix on purpose: a missing ``favicon.ico`` or a
    stylesheet's control image must never be able to abort a sweep. A path
    requested more than once keeps its last status.
    """
    return {
        path: status
        for path, status in image_requests(access_log)
        if not 200 <= status < 300
    }


def disallowed_failures(
    access_log: AccessLog, allowance: frozenset[str]
) -> dict[str, int]:
    """Failed image requests minus the paths the suite deliberately tolerates."""
    return {
        path: status
        for path, status in failing_paths(access_log).items()
        if path not in allowance
    }


def tile_grid(width: int, height: int, step: int) -> list[tuple[int, int, int, int]]:
    """Tile-aligned cells covering the whole image at ``step`` resolution."""
    return [
        (x, y, min(step, width - x), min(step, height - y))
        for x in range(0, width, step)
        for y in range(0, height, step)
    ]


def classify_requests(
    recorded: Iterable[str],
    on_disk: Iterable[str],
    declared: Iterable[str],
    *,
    width: int | None = None,
    height: int | None = None,
) -> RequestClassification:
    """Partition requested paths into generated, declared and out-of-pyramid.

    ``recorded`` is any iterable of requested paths (a ``Recording.requested``
    mapping works, since iterating it yields paths) and ``declared`` may hold
    absolute URLs, which are normalized here.

    ``width`` and ``height`` opt into the whole-image equivalence of
    :func:`whole_image_key`: a request for either spelling of the coarsest
    level's single derivative is then judged against the tree as a whole. The
    buckets keep holding the paths as recorded — never the keys — so a caller
    that looks up a recorded path's status still finds it, and a request for a
    spelling the tree lacks stays visible as the 404 it is.
    """

    def key_for(path: str) -> str:
        if width is None or height is None:
            return path
        return whole_image_key(path, width, height)

    generated = {key_for(normalize(path)) for path in on_disk}
    advertised = {key_for(normalize(url)) for url in declared}
    in_pyramid: set[str] = set()
    declared_paths: set[str] = set()
    out_of_pyramid: set[str] = set()
    for path in {normalize(path) for path in recorded}:
        key = key_for(path)
        if key in generated:
            in_pyramid.add(path)
        elif key in advertised:
            declared_paths.add(path)
        else:
            out_of_pyramid.add(path)
    return RequestClassification(
        in_pyramid=frozenset(in_pyramid),
        declared=frozenset(declared_paths),
        out_of_pyramid=frozenset(out_of_pyramid),
    )


def classify_requested(
    recorded: Iterable[str],
    site_root: Path,
    base_url: str,
    version: IIIFVersions,
) -> RequestClassification:
    """Partition requested paths against one generated tree and its info.json."""
    info = read_info(site_root)
    return classify_requests(
        recorded,
        region_tile_paths(site_root),
        declared_image_urls(site_root, base_url, version),
        width=info["width"],
        height=info["height"],
    )
