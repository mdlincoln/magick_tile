# Vendored OpenLayers assets

`ol-10.11.0.js` and `ol-10.11.0.css` are the upstream distribution build,
vendored so the end-to-end suite runs offline and against a fixed client
version.

| | |
| --- | --- |
| Project | OpenLayers |
| Version | 10.11.0 |
| Upstream URL (JS) | https://cdn.jsdelivr.net/npm/ol@10.11.0/dist/ol.js |
| Upstream URL (CSS) | https://cdn.jsdelivr.net/npm/ol@10.11.0/ol.css |
| License | BSD-2-Clause |
| Size | 1070771 + 6343 bytes |

OpenLayers is © the OpenLayers contributors and is distributed under the
BSD-2-Clause license: https://github.com/openlayers/openlayers/blob/main/LICENSE.md

The full build assigns the global `ol`, so the page needs no bundler. The
stylesheet is the package-root `ol.css`: OpenLayers 10.x ships no `dist/ol.css`.

## Checksums

<!-- sha256:begin -->
ol-10.11.0.js	a4e607e98b56846d543e2131161720845c7a80170d5f00aa2bc8b6c4e0f9194a
ol-10.11.0.css	abc8afd72cc10bd29cc143f443bae4a6804bd3cb3fb262e6b6a6bc6c924ea34f
<!-- sha256:end -->

`tests/test_vendor_provenance.py` checks those digests against the committed
bytes; one line per vendored file, path relative to this directory, digest
separated from the path by a tab.

## Updating

1. Pick the new version and download the same two paths from jsDelivr.
2. Replace the files, keeping the version in their names.
3. Refresh the digests above (`shasum -a 256 <file>`), the table, and the
   references in `../index.html` and `e2e/README.md`.
4. Run `uv run --group e2e pytest e2e` and check the tile requests still match
   what the library writes: a client change in tile URL construction is exactly
   what this suite exists to catch.
