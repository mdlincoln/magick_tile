# Vendored viewer assets

`openseadragon-6.1.1.min.js` is the upstream distribution build, vendored so the
end-to-end suite runs offline and against a fixed client version.

| | |
| --- | --- |
| Project | OpenSeadragon |
| Version | 6.1.1 |
| Upstream URL | https://cdn.jsdelivr.net/npm/openseadragon@6.1.1/build/openseadragon/openseadragon.min.js |
| SHA-256 | `14d587cd3ee7c4861f1a41077ce642029364a21029956ba635bd8fb1202cf9ad` |
| License | BSD-3-Clause |
| Size | 352735 bytes |

OpenSeadragon is © the OpenSeadragon contributors and is distributed under the
BSD-3-Clause license: https://github.com/openseadragon/openseadragon/blob/master/LICENSE.txt

Only the JavaScript bundle is vendored. Navigators and navigation controls are
disabled in `../index.html`, so the `images/` folder the default build expects is
not needed.

## Checksums

<!-- sha256:begin -->
openseadragon-6.1.1.min.js	14d587cd3ee7c4861f1a41077ce642029364a21029956ba635bd8fb1202cf9ad
<!-- sha256:end -->

`tests/test_vendor_provenance.py` checks those digests against the committed
bytes; one line per vendored file, path relative to this directory, digest
separated from the path by a tab.

## Updating

1. Pick the new version and download the same path from jsDelivr.
2. Replace the file, keeping the version in its name.
3. Refresh the SHA-256 (`shasum -a 256 <file>`) and the version references in
   this file, in `../index.html`, and in `e2e/README.md`.
4. Run `uv run --group e2e pytest e2e` and check the tile requests still match
   what the library writes: a client change in tile URL construction is exactly
   what this suite exists to catch.
