# Browser end-to-end tests

These tests check a generated tree the way a reader reaches it: through a IIIF
client. Each run generates a real tile tree from
`fixtures/self-portrait_1937.1.72.jpg` (3202×4096), serves it from a local static
server, and drives three independent clients over it in Chromium. Each client
walks the whole image at every generated scale factor, and the tests compare what
it requested with what the library wrote.

## Prerequisites

- [ImageMagick](https://imagemagick.org/index.php) on your path (`convert`,
  `identify`)
- `uv`
- Chromium for Playwright, installed once per machine:
  `uv run --group e2e playwright install chromium`

## Run

```
uv sync --group e2e
uv run --group e2e playwright install chromium
uv run --group e2e pytest e2e -v
```

The run covers six combinations — both API versions (3.0 and 2.1) against each
of the three viewers — and each combination gets one sweep, built once per
session. It is offline: the viewers are vendored under
`viewer/<backend>/vendor/`, the image is committed in `fixtures/`, and the tile
server is local. Only the one-time `playwright install` needs the network.

The suite is deliberately outside the default test run: `pyproject.toml` sets
`testpaths = ["tests"]`, so `uv run pytest` stays unit-only, and passing `e2e` as
an explicit path overrides it. The pure request helpers in `requests.py` are the
exception — `tests/test_request_classification.py` covers them without a
browser.

## Viewers

| Backend | Vendored bundle | What it proves | Page |
| --- | --- | --- | --- |
| OpenSeadragon 6.1.1 | `openseadragon-6.1.1.min.js` (352 KB) | The reference client: a deep-zoom engine driven from `tiles` and `scaleFactors` | `viewer/openseadragon/index.html` |
| OpenLayers 10.11.0 | `ol-10.11.0.js` + `ol-10.11.0.css` (1.07 MB) | A second pyramid: `ol.source.IIIF` derives the tile grid from `info.json`, requests only declared scale factors, and clamps edge tiles with the same `ceil` rule the generator uses | `viewer/openlayers/index.html` |
| Leaflet 1.9.4 + leaflet-iiif 3.0.0 | `leaflet-1.9.4.js` + `.css`, `leaflet-iiif-3.0.0.js` (172 KB) | A client that ignores `scaleFactors` and counts tiers from the image and tile size — its coarsest tier is the pyramid's top level, and the home fit exercises that level under the explicit-region spelling | `viewer/leaflet/index.html` |

All three expose the same `window.__viewer` contract (opened, failures, idle
state, dimensions, current level), so the adapters in `viewers/` share one state
shape and the tests never reach into library internals.

## What is asserted

- **Every requested tile loads.** Each image response for a generated tile or a
  declared derivative is HTTP 200 with a non-empty body, no viewer recorded an
  open failure, and the server's access log holds no failed request for an
  in-pyramid path.
- **Every generated tile is requested.** The tile files on disk are a subset of
  the URLs Playwright's response listener saw, and each generated scale factor
  was requested at least once. This catches a layout the library writes but no
  client asks for, and a pyramid level no client reaches.
- **Declared full-image URLs resolve.** Every `sizes` entry in `info.json` and
  the unscaled full-size image return 200 with a body.
- **Nothing outside the pyramid is invented.** Out-of-pyramid requests must
  equal the frozen allowance exactly — it is empty for every combination — and
  any path it did allow would have to have failed with a 404.
- **The coarsest level resolves under both spellings.** The tree holds both
  files, each spelling a client requested returned 200 with a body, and across
  the three backends both spellings are requested.
- **Every fit lands on a generated level.** The level a viewer actually drew is
  checked against the pyramid; the two backends whose level the sweep sets
  assert the stronger equality at the fit itself.
- **Nothing reaches the network.** A route handler aborts any request that is
  not to the local tile server — host and port both have to match — and the
  test also requires that the sweep made image requests at all.

The sweep fits one tile-aligned cell at a time rather than panning blindly, so
coverage is deterministic: at each scale factor every cell of the tile grid is
fitted in turn, and the viewer requests exactly the tiles of that cell.

## The frozen allowance

`leaflet-iiif` 3.0.0 does not read `scaleFactors`. It computes

```
maxNativeZoom = max(ceilLog2(3202 / 512), ceilLog2(4096 / 512), 0) = 3
tier 0 scale  = 2 ** (maxNativeZoom - 0) = 8
```

and walks tiers as `scale = 2 ** (maxNativeZoom - zoom)`. That is the level where
the whole image fits in a single tile, and it is the pyramid's top level:
`scaleFactors` is `[1, 2, 4, 8]`, because the longer side — 4096 — is eight tiles
of 512. The only view in which the whole image fits a 720 px viewport therefore
asks for the image as one tile at scale 8, size `ceil(3202/8)` × `ceil(4096/8)`,
and that file is written:

| API | leaflet-iiif requests | OpenSeadragon and OpenLayers request |
| --- | --- | --- |
| 3.0 | `/iiif/self-portrait/0,0,3202,4096/401,512/0/default.jpg` | `/iiif/self-portrait/full/401,512/0/default.jpg` |
| 2.1 | `/iiif/self-portrait/0,0,3202,4096/401,/0/default.jpg` | `/iiif/self-portrait/full/401,/0/default.jpg` |

The two columns are one derivative written under both spellings: Image API 3.0
§4.4 makes `full` the canonical region form, so the clients that canonicalize a
whole-image region ask for that, while leaflet-iiif sends the explicit region.
A dynamic server would redirect one to the other; a static tree writes both.

`viewers/base.py`'s `ALLOWANCES` is the single copy of the requests a backend is
allowed to make that the tree does not satisfy, and it is **empty for all six
combinations** — the assertion, not the absence of one. The sweep's control flow
reads it (so a tolerated 404 would not abort a sweep) and
`test_request_policy.py` reads it, so a newly invented URL fails as loudly as an
allowance entry that stopped being requested. The table stays as that pin.

[`request-gap-report.md`](request-gap-report.md) works through the measurement
that led here: the arithmetic behind the gap, how it varied with image shape, the
file spellings each client demands, and what the tests saw before the library
changed. Its Resolution section records what was done.

## Why these three

- **Diva.js** was excluded: its 7.0.0 rewrite delegates rendering to
  OpenSeadragon, so it would only re-test the reference backend.
- **`ow-leaflet-iiif`** 1.0.7 emits the 2.1 size form (`512,`) for square tiles
  even against a 3.0 service, so its URLs are wrong for reasons unrelated to the
  tree.
- **MapLibre, deck.gl** cannot drive a pregenerated pyramid without inventing
  region requests.
- **Micrio** was offered and not selected.

## Layout

- `requests.py` — pure path/access-log helpers (bucket requests, tile grid,
  failing paths); no Playwright, no harness import.
- `harness.py` — the static server, the generated site, and the recording shape.
- `viewers/base.py` — the `ViewerBackend` protocol, the settle poll, the sweep,
  and `ALLOWANCES`.
- `viewers/<backend>.py` — one adapter per client, paired with the page under
  `viewer/<backend>/`.

## Fixture and vendor policy

- `fixtures/self-portrait_1937.1.72.jpg` is a 2.7 MB public-domain scan,
  committed with a `.gitignore` negation because the repository ignores `*.jpg`
  globally. Small binaries that make the suite hermetic are committed; anything
  above roughly 5 MB should go in Git LFS instead.
- The three bundles total ~1.6 MB of third-party code, vendored so runs stay
  offline and pinned to a known client version. Each `viewer/<backend>/vendor/`
  has a `README.md` with the version, upstream URL, license and a sha256 block;
  `tests/test_vendor_provenance.py` fails if a digest or a vendored file
  disagrees with the block.
- Neither the fixture nor any vendored bundle ships in the built package: the
  wheel only contains `magick_tile/`, and the sdist excludes `e2e/fixtures` and
  `e2e/viewer/*/vendor` (`tests/test_packaging.py` checks both).
