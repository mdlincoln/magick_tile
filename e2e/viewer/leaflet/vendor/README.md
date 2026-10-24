# Vendored Leaflet assets

`leaflet-1.9.4.js`, `leaflet-1.9.4.css` and `leaflet-iiif-3.0.0.js` are the
upstream distribution builds, vendored so the end-to-end suite runs offline and
against fixed client versions.

| | |
| --- | --- |
| Project | Leaflet |
| Version | 1.9.4 |
| Upstream URL (JS) | https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js |
| Upstream URL (CSS) | https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css |
| License | BSD-2-Clause |
| Project | leaflet-iiif |
| Version | 3.0.0 |
| Upstream URL | https://cdn.jsdelivr.net/npm/leaflet-iiif@3.0.0/leaflet-iiif.js |
| License | MIT |
| Size | 147552 + 14806 + 9480 bytes |

Leaflet is © Volodymyr Agafonkin and contributors, BSD-2-Clause:
https://github.com/Leaflet/Leaflet/blob/main/LICENSE
leaflet-iiif is © Jack Reed, MIT:
https://github.com/mejackreed/Leaflet-IIIF/blob/master/LICENSE

`leaflet.css` references control images (`layers.png`, `layers-2x.png`,
`marker-icon.png`) that are intentionally absent: `../index.html` disables the
zoom and attribution controls and the plugin draws no markers, so nothing
requests them.

## Checksums

<!-- sha256:begin -->
leaflet-1.9.4.js	db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a
leaflet-1.9.4.css	a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6
leaflet-iiif-3.0.0.js	3910f668c74903c81f9f2fd1a1cb40cd3151b54cfffe8144b5bfa560cf5cd8f3
<!-- sha256:end -->

`tests/test_vendor_provenance.py` checks those digests against the committed
bytes; one line per vendored file, path relative to this directory, digest
separated from the path by a tab.

## Updating

1. Pick the new versions and download the same paths from jsDelivr.
2. Replace the files, keeping the versions in their names.
3. Refresh the digests above (`shasum -a 256 <file>`), the table, and the
   references in `../index.html` and `e2e/README.md`.
4. Run `uv run --group e2e pytest e2e` and check the tile requests still match
   what the library writes: a plugin change in tile URL construction is exactly
   what this suite exists to catch, and leaflet-iiif's tier count is the client
   side of the level agreement `e2e/viewers/base.py`'s `ALLOWANCES` pins (it is
   empty: the pyramid's top level is the tier-0 scale this plugin derives).
5. Check `../index.html` still finds what it binds to the plugin: the tier
   arithmetic reads `layer.maxNativeZoom`, `layer.x`/`layer.y`, and the startup
   barrier awaits `layer._infoPromise`. A rename in any of those fails the page
   loudly (`openFailed`) rather than racing, but the page needs updating.
