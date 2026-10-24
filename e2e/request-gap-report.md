# Report: requests the generated tree does not satisfy

What the browser suite's three IIIF clients ask for that `magick_tile` does not
write, measured per test and per backend, with the arithmetic behind it. Written
to be used when planning library changes, not as suite documentation — the suite
itself is described in [`README.md`](README.md).

Measured on 2026-10-23 by replaying the suite's own six sweeps (same fixtures,
same 1280×720 viewport, same offline interceptor) and recording every request,
status and level. Raw figures in the tables below are from that run; anything
derived from source instead of observation is labelled as such.

## The generated tree under test

| | |
| --- | --- |
| Fixture | `fixtures/self-portrait_1937.1.72.jpg`, 3202×4096 |
| Tile size | 512 |
| `scaleFactors` | `[1, 2, 4]` |
| Tiles generated | 4 at scale 4, 16 at scale 2, 56 at scale 1 (76 total) |
| Declared `sizes` | 256×327, 512×655, 1024×1310, 2048×2620 |
| Canonical full image | `full/max/…` (3.0), `full/full/…` (2.1) |

## 1. Summary

Every combination, both API versions. "Unique requests" counts distinct image
paths; "out-of-pyramid" counts distinct paths the tree does not contain.

| Version | Client | Unique requests | In pyramid | Out of pyramid | 404s | Client tile errors | Tiles reached |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3.0 | OpenSeadragon 6.1.1 | 76 | 76 | 0 | 0 | 0 | 76/76 |
| 3.0 | OpenLayers 10.11.0 | 76 | 76 | 0 | 0 | 0 | 76/76 |
| 3.0 | leaflet-iiif 3.0.0 | 77 | 76 | **1** | **1** | **2** | 76/76 |
| 2.1 | OpenSeadragon 6.1.1 | 76 | 76 | 0 | 0 | 0 | 76/76 |
| 2.1 | OpenLayers 10.11.0 | 76 | 76 | 0 | 0 | 0 | 76/76 |
| 2.1 | leaflet-iiif 3.0.0 | 77 | 76 | **1** | **1** | **2** | 76/76 |

Everything the library wrote was requested: no generated tile is unreachable by
any client, and every generated tile was requested at every level (4 of 4 at
scale 4, 16 of 16 at scale 2, 56 of 56 at scale 1) in all six combinations.
Dimensions parsed by each client were 3202×4096. No request left the local
server.

## 2. The one 404, per backend and version

**OpenSeadragon — none.** 76 requests, all generated tiles, each exactly once.
Its drawn level lags the requested one at coarse levels (see §5.3), but it never
asks for a file the tree lacks.

**OpenLayers — none.** 76 requests, all generated tiles, each exactly once. The
`full` canonicalization that rewrites a whole-image tile region to
`full/{w},{h}` never triggers, because no level of the pyramid covers the whole
image in a single tile.

**Leaflet — exactly one path, per version:**

| Version | Requested path | Status | Requests | Implied scale |
| --- | --- | --- | --- | --- |
| 3.0 | `/iiif/self-portrait/0,0,3202,4096/401,512/0/default.jpg` | 404 | 2 | 8 |
| 2.1 | `/iiif/self-portrait/0,0,3202,4096/401,/0/default.jpg` | 404 | 2 | 8 |

Region `0,0,3202,4096` is the whole image; the size is `ceil(3202/8)=401` by
`ceil(4096/8)=512`, or the 2.1 width-only form of the same. That is scale 8, one
power of two above the coarsest generated level (scale 4). It is requested twice
per sweep — the sweep fits home at both the start and the end of the grid walk,
and both land on tier 0 — and produces the only two client-side tile errors in
the run. It is the sole entry in the frozen `ALLOWANCES` table
(`e2e/viewers/base.py`).

Both versions agree on everything else: one 404, one path, twice.

## 3. Why the gap exists, and where else it will

Two different rules pick the coarsest level.

**The library** (`magick_tile/generator.py`, `scaling_factors`) emits powers of
two below `ceil(min(width, height) / tile_size)`:

```
k     = ceil(log2(ceil(min(w, h) / tile))) - 1
top   = 2 ** k            # the coarsest generated level
```

so at the top level the image still needs at least two tiles across its shorter
side. For 3202×4096 at tile 512: `ceil(3202/512) = 7`, `k = 2`, top = 4.

**leaflet-iiif** (`leaflet-iiif-3.0.0.js`, `_getInfo`) ignores `scaleFactors`
and counts tiers from the image and the tile:

```
m       = max(ceil(log2(w / tile)), ceil(log2(h / tile)), 0)
tier 0  = 2 ** m          # the level where the whole image fits one tile
```

For 3202×4096: `m = max(ceil(log2 6.25), ceil(log2 8)) = max(3, 3) = 3`, tier 0
= 8.

Because the library sizes the top level from the **shorter** side and
leaflet-iiif from the **longer** one, `2 ** m > 2 ** k` whenever the image is
larger than a single tile — the gap is structural, not a property of this
fixture. Arithmetic from the two formulas above (tile 512):

| Image | Library level list | Library top | leaflet tier 0 | Gap |
| --- | --- | --- | --- | --- |
| 3202×4096 (fixture) | `[1, 2, 4]` | 4 | 8 | ×2 |
| 4096×4096 | `[1, 2, 4]` | 4 | 8 | ×2 |
| 4096×2048 | `[1, 2]` | 2 | 8 | ×4 |
| 2048×2048 | `[1, 2]` | 2 | 4 | ×2 |
| 1024×1024 | `[1]` | 1 | 2 | ×2 |
| 600×400 | `[1]` | 1 | 2 | ×2 |
| 512×512 | `[1]` | 1 | 1 | none |
| 256×256 | `[1]` | 1 | 1 | none |

So: images up to one tile are unaffected; everything larger is missing at least
one whole-image level, and elongated aspect ratios are missing more. The
`scaling_factors` docstring already makes this argument for the *bottom* of the
pyramid ("a pyramid that starts at 2 leaves them requesting tiles that were
never written"); this is the same argument applied to the top.

## 4. What a library change would have to write

Measured, not inferred. A tree was generated, its `info.json` was patched to
declare `scaleFactors: [1, 2, 4, 8]` **without writing the level**, and each
client was asked for the new top level. Both API versions:

| Version | Client | Requested at the new top level | Status |
| --- | --- | --- | --- |
| 3.0 | OpenSeadragon | `/iiif/self-portrait/full/401,512/0/default.jpg` | 404 |
| 3.0 | OpenLayers | `/iiif/self-portrait/full/401,512/0/default.jpg` | 404 |
| 3.0 | leaflet-iiif | `/iiif/self-portrait/0,0,3202,4096/401,512/0/default.jpg` | 404 |
| 2.1 | OpenSeadragon | `/iiif/self-portrait/full/401,/0/default.jpg` | 404 |
| 2.1 | OpenLayers | `/iiif/self-portrait/full/401,/0/default.jpg` | 404 |
| 2.1 | leaflet-iiif | `/iiif/self-portrait/0,0,3202,4096/401,/0/default.jpg` | 404 |

Two consequences for planning:

1. **Two spellings of the same derivative, not one.** OpenSeadragon and
   OpenLayers rewrite a whole-image tile region to `full` and send the size
   only; leaflet-iiif sends the explicit region. A level that is written only as
   a tile file (`0,0,3202,4096/401,512/…`) fixes leaflet and leaves the other
   two 404-ing; writing only `full/401,512/…` does the reverse. Satisfying all
   three means writing both paths for each version's canonical size form.
2. **The 404 would otherwise move rather than disappear.** Today the pyramid's
   top level never covers the whole image, so OpenSeadragon and OpenLayers never
   construct a `full` request. Publishing a whole-image level makes them do so.

Note also that `full/401,512` is not among the declared `sizes` (256, 512, 1024,
2048 widths, all width-driven). It is aspect-correct by the scale-8 rule
(3202/8 = 400.25 → 401, 4096/8 = 512) but is not the same file as any existing
derivative, so it would be a new artifact either way.

## 5. Per-test view

### 5.1 `test_all_requested_tiles_load` — no 404s, no gaps

Owed paths (generated tiles and declared derivatives) all returned 200 with a
non-empty body in all six combinations. The only non-2xx anywhere in the run is
leaflet's allowance path, which this test deliberately excludes and
`test_request_policy` owns. Client-side failures are `[]` for OpenSeadragon and
OpenLayers; leaflet records the two allowed `tileerror` events for the path in
§2.

### 5.2 `test_all_generated_tiles_are_requested` — complete coverage, both versions

| Level | Generated | OpenSeadragon | OpenLayers | leaflet-iiif |
| --- | --- | --- | --- | --- |
| scale 4 | 4 | 4 requested, 4 times | 4 requested, 4 times | 4 requested, 4 times |
| scale 2 | 16 | 16 requested, 16 times | 16 requested, 16 times | 16 requested, 16 times |
| scale 1 | 56 | 56 requested, 56 times | 56 requested, 56 times | 56 requested, 56 times |

No generated tile is missing for any client, and no tile is requested twice
except leaflet's allowance path. Both versions behave identically; only the size
segment of the URLs differs.

### 5.3 `test_every_fit_landed_on_a_generated_level` — one behavioural difference

The sweep fits a cell of `512 × scale_factor` pixels into the viewport and
records the level each client actually draws:

| Client | Asked 4 | Asked 2 | Asked 1 |
| --- | --- | --- | --- |
| OpenSeadragon | drew 2 (×4) | drew 1 (×16) | drew 1 (×56) |
| OpenLayers | drew 4 (×4) | drew 2 (×16) | drew 1 (×56) |
| leaflet-iiif | drew 4 (×4) | drew 2 (×16) | drew 1 (×56) |

OpenSeadragon chooses the level closest to the fitted resolution rather than the
level asked for: a 2048-px cell fitted to 720 px resolves to ~2.84 px/px, and
the closest generated level is scale 2.

All four scale-4 tiles are still requested (once each) even though no recorded
fit drew that level, so those requests come from the client's own level handling
during load rather than from a recorded fit. The practical consequence for the
suite is that OpenSeadragon's coarsest-level coverage does not depend on the
cell fits at all, while scale-1 and scale-2 coverage does. Worth knowing when
changing stride, viewport, or the level list: OpenSeadragon's per-level coverage
is not driven cell-by-cell the way the other two clients' is.

This is a client behaviour, not a gap in the tree.

### 5.4 `test_out_of_pyramid_requests_match_allowance` — the table in §2

Observed set equals the allowance exactly for all six combinations: empty for
OpenSeadragon and OpenLayers, one path for leaflet. Each allowed path 404'd, and
each 404'd path was allowed.

### 5.5 `test_offline` — nothing to report

`blocked_requests` empty for every combination; the request counts in §1 prove
the sweeps were not empty.

### 5.6 `test_declared_sizes_and_full_size_resolve` — files no client reads

The declared derivatives are served but never requested by any client: the four
`sizes` entries and the canonical full image (`full/max`, `full/full`) stay out
of every client's request set in both versions. The suite fetches them directly
with HTTP GETs, which is the only exercise they get. If an update starts writing
a whole-image level (§4), that changes for the first time — clients would begin
requesting a `full/{w},{h}` derivative.

This is not a defect: Level 0 requires declaring sizes, and thumbnails use them.
It does mean that "no client asks for it" is currently normal for every
full-region derivative.

## 6. Options for a library update

| Option | What changes | Suite impact | Risk |
| --- | --- | --- | --- |
| A. Extend the pyramid by one whole-image level | `scaleFactors` gains `2**(k+1)`; write the level as a tile (`0,0,w,h/…`) **and** as `full/{w},{h}` | leaflet's allowance becomes empty; OpenSeadragon and OpenLayers start requesting `full/{w},{h}`, so the allowance table gains that path unless it is written; `test_fit_level` then sees a fourth asked level | Two artifacts per image; a larger `scaleFactors` list changes every client's tier derivation |
| B. Leave the pyramid, document the client limitation | No tree change | none | leaflet-iiif (and any client that derives tiers from image size) keeps 404-ing at its coarsest zoom |
| C. Derive the top level from the longer side | top level becomes `2**m`, i.e. one whole-image tile per image | same as A, plus coverage of the coarsest level becomes a single tile | Changes the level list for every image, not only elongated ones; more visible churn than A |

If A is chosen, the suite's frozen allowance is the acceptance test: after the
change, `test_out_of_pyramid_requests_match_allowance` should demand an empty
set for leaflet, and it will fail loudly if only the tile spelling was written
(OpenLayers and OpenSeadragon would then contribute `full/{w},{h}` to the
out-of-pyramid set). Updating `ALLOWANCES` alone would hide exactly the
regression the table exists to catch.

## 7. Reproducing

The numbers come from replaying the suite's sweeps against a real generated
tree, not from the assertions. To re-measure after any change, run the suite and
read the failures, or replay the sweeps directly:

```
uv sync --group e2e && uv run --group e2e playwright install chromium
uv run --group e2e pytest e2e -v          # 38 tests, 6 sweeps
```

`test_out_of_pyramid_requests_match_allowance` reports the observed set for each
combination in its failure message, so a library change shows up as a diff
between the observed set and the frozen table. For the §4 probe, the procedure
is: generate a tree, edit `iiif/self-portrait/info.json` to add the extra scale
factor without writing the level, serve it, open `viewer/<backend>/index.html`,
and fit the whole image at the new top level.

## 8. Resolution

**Option C was taken** — the top level is derived from the longer side. For the
3202×4096 fixture that is the same level option A would have added, and for the
elongated shapes in §3's table it is the only choice that adds just one level
instead of leaving a gap of more than one power of two.

Two changes in `magick_tile/generator.py`:

1. `scaling_factors_for` ascends powers of two until `2 ** M * tile_size >=
   max(width, height)`, and `SourceImage.scaling_factors` delegates to it. The
   coarsest entry is now the level where the whole image fits in one tile, which
   is the tier-0 scale §3 shows leaflet-iiif deriving.
2. `SourceImage.generate_whole_image_level` writes that level's whole-image
   derivative at `full/{w},{h}/0/` (3.0) or `full/{w},/0/` (2.1), sized
   `ceil(w/2**M)` by `ceil(h/2**M)`. The tile pipeline already writes the
   explicit-region spelling §4 measured leaflet-iiif asking for, so the level now
   exists under both spellings and the static tree needs no redirect.

New level lists for the images in §3 (tile 512):

| Image | Was | Now | Coarsest level |
| --- | --- | --- | --- |
| 3202×4096 (fixture) | `[1, 2, 4]` | `[1, 2, 4, 8]` | 401×512 |
| 4096×4096 | `[1, 2, 4]` | `[1, 2, 4, 8]` | 512×512 |
| 4096×2048 | `[1, 2]` | `[1, 2, 4, 8]` | 512×256 |
| 2048×2048 | `[1, 2]` | `[1, 2, 4]` | 512×512 |
| 1024×1024 | `[1]` | `[1, 2]` | 512×512 |
| 600×400 | `[1]` | `[1, 2]` | 300×200 |
| 512×512 | `[1]` | `[1]` | 512×512 |
| 256×256 | `[1]` | `[1]` | 256×256 |

For the unit asset at 2676×1572 the list goes `[1, 2]` → `[1, 2, 4, 8]` with a
coarsest level of 335×197.

Superseded by this section: §1's tree table and totals (the tree now has four
levels and 77 tiles at this fixture size) and its out-of-pyramid and 404 columns
(both are 0 for every combination), §2 (the 404 it documents is gone, and the
request is now a written file), §4 (its "what a change would have to write" is
what was written), §5.2's per-level counts, §5.4 (the allowance is empty for all
six combinations), §5.6's closing note (clients now request a `full/{w},{h}`
derivative — the coarsest level), §6's option table, which is history rather than
a decision to make, and §7's test count, which is a dated reproduction note.
§3's arithmetic and §5.3's conclusion — OpenSeadragon picks the closest level
rather than the one asked for — still describe the clients; §5.3's measured rows
were taken on the old `[1, 2, 4]` list and no longer name today's levels.
