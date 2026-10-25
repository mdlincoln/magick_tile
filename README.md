# magick-tile

[![PyPi version](https://img.shields.io/pypi/v/magick-tile.svg)](https://pypi.org/project/magick-tile/)
[![pytest](https://github.com/mdlincoln/magick_tile/actions/workflows/pytest.yml/badge.svg)](https://github.com/mdlincoln/magick_tile/actions/workflows/pytest.yml)

This package and command-line utility relies on Imagemagick to efficiently create derivative tiles of a very large image, and structure them into directories compliant with [IIIF Level 0](https://iiif.io/api/image/3.0/compliance/#5-level-0-compliance) specification for static sites, targeting either Image API 3.0 or 2.1.

This takes inspiration heavily from https://github.com/zimeon/iiif/blob/master/iiif_static.py, but uses ImageMagick rather than Pillow in order to speed up generation at the expense of a less flexible treatment of images.

## Prerequisites

- Python > 3.9
- [Imagemagick](https://imagemagick.org/index.php) must be available on your path

## Installation

```
pip install magick-tile
```

## Run

```
 Usage: magick_tile [OPTIONS] {source} {output} {identifier}

 Efficiently create derivative tiles of a very large image, and structure them
 into directories compliant with IIIF Level 0.

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    source          <file>       [required]                                 │
│ *    output          <directory>  Destination directory for tiles [required] │
│ *    identifier      <str>        Image identifier to be written to final    │
│                                   info.json (e.g.                            │
│                                   https://example.com/iiif/my_image)         │
│                                   [required]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --tile-size                 <int>                   Tile size to produce     │
│                                                     [default: 512]           │
│ --format                    <jpg|tif|png|gif|jp2|p  File formats to generate │
│                             df|webp>                (must be supported by    │
│                                                     Imagemagick's 'convert') │
│                                                     [default: jpg]           │
│ --version                   <3.0|2.1>               IIIF Image API version   │
│                                                     [default: 3.0]           │
│ --install-completion                                Install completion for   │
│                                                     the current shell.       │
│ --show-completion                                   Show completion for the  │
│                                                     current shell, to copy   │
│                                                     it or customize the      │
│                                                     installation.            │
│ --help                                              Show this message and    │
│                                                     exit.                    │
╰──────────────────────────────────────────────────────────────────────────────╯

```

This will create and populate the specified output directory with tiles from a given image.

N.b. because several of the Imagemagick utilities called here already utilize multiple cores, returns for running this script in parallel diminish rapidly.

## Output layout & IIIF versions

`--version` selects the IIIF Image API version that the output tree and its `info.json` target: `3.0` (the default) or `2.1`. Both are written as **Level 0** static trees: the `info.json` declares `level0` compliance, and the unscaled full-size image is written at the version's canonical location.

For a 2676×1572 source image generated with `--version 3.0`:

```
<output>/
├── info.json
├── full/
│   ├── max/0/default.jpg        # unscaled full image
│   ├── 256,150/0/default.jpg    # declared sizes: aspect-correct thumbnails
│   ├── 512,301/0/default.jpg
│   ├── 1024,602/0/default.jpg
│   ├── 2048,1203/0/default.jpg
│   └── 335,197/0/default.jpg    # coarsest level: the whole image in one tile
├── 0,0,512,512/
│   └── 512,512/0/default.jpg    # native-resolution tile (scale factor 1)
├── 0,0,1024,1024/
│   └── 512,512/0/default.jpg    # scale factor 2 tile, 512 px on a side too
├── 0,0,2048,1572/
│   └── 512,393/0/default.jpg    # scale factor 4
└── 0,0,2676,1572/
    └── 335,197/0/default.jpg    # scale factor 8: one tile, the whole image
```

- **Region tiles** live at `{x},{y},{w},{h}/{size}/0/default.jpg`: the region, then `{size}`, the dimensions the written file actually has. Edge tiles round the scaled dimension up, so a 975 px tall region at scale factor 2 is addressed as `512,488`, not `512,487`.
- **`sizes`** in `info.json` lists the declared thumbnails as `w,h` pairs, and each of them is written under `full/`.
- **Scale factors** start at 1 and ascend by powers of two, up to the level where the whole image fits in a single tile. Scale factor 1 is the native-resolution level; each larger factor is a complete coarser level of the pyramid.
- **The coarsest level is written twice.** At that level the whole image is one tile, and clients name it two ways: the canonical `full/{w},{h}/0/` region, or the explicit `0,0,{W},{H}/{w},{h}/0/` region naming the tile they would have loaded. A static tree cannot redirect one to the other, so both files are written.
- **Formats beyond jpg** are declared in `info.json`: 3.0 payloads list them in `extraFormats`, with everything the tree serves in `preferredFormats`.
- **jpg must be included in `--format` for a certifiable tree**: the compliance tables of both Image API 2.1 and 3.0 require jpg support at every compliance level, so a run whose `--format` values exclude jpg produces a tree that no compliance level can certify.

Version 2.1 trees use their own size-directory and full-size naming and a 2.1-specific `info.json` payload. [CHANGELOG.md](CHANGELOG.md) records those differences and every breaking change to the output contract, including which past releases require regenerating a tree.

Before a release you can spot-check a generated `info.json` against the official IIIF Image API validator at https://iiif.io/api/image/validator/.

## End-to-end tests

The unit suite exercises the generator directly. A separate browser suite in
[`e2e/`](e2e/README.md) closes the loop: it generates a real tile tree from a
13 MP fixture, serves it from a local static server, and drives it with three
independent IIIF clients under Playwright — OpenSeadragon 6.1.1, OpenLayers
10.11.0 and Leaflet 1.9.4 with leaflet-iiif 3.0.0. Each client walks the whole
image at every generated scale factor, and the suite asserts that every tile it
requests is a file the library wrote (and that every file it wrote is
requested). It runs for both API versions:

```
uv sync --group e2e
uv run --group e2e playwright install chromium
uv run --group e2e pytest e2e
```

`uv run pytest` on its own still collects only `tests/`.

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/). `uv.lock` pins the exact
versions used locally and in CI, so run project commands through `uv run` rather than
activating an environment by hand.

```
uv sync                    # create .venv and install runtime + dev dependencies
uv run pytest              # run the test suite
uv run ty check            # type check
uv run ruff check          # lint
uv run ruff format         # format
uv run pre-commit install  # enforce ruff and ty on every commit
```

`.pre-commit-config.yaml` runs ruff's linter, ruff's formatter and ty on staged
files. The ruff and ty versions are pinned twice — in the `dev` dependency group
(for `uv run`) and as hook revs in the pre-commit config — so bump both together.
CI runs the same hooks across every file, which means skipping them locally with
`--no-verify` still fails the build.

To change a dependency, edit `pyproject.toml` (`dependencies` or a group under
`[dependency-groups]`) and run `uv lock`. CI installs with `uv sync --locked`, so a
`pyproject.toml` change without a matching lock update fails the build.

## Releasing

Record the release in `CHANGELOG.md` under an `## X.Y.Z` heading, bump `version` in
`pyproject.toml` to match, and merge to `master`. Then create a GitHub Release with a
matching `vX.Y.Z` tag.

`.github/workflows/publish.yml` runs on stable releases: it re-runs the test suite
against the tagged commit, checks that the tag matches `pyproject.toml`, and uploads
the sdist and wheel to PyPI via Trusted Publishing. That requires a Trusted Publisher
registered on PyPI for this repository, naming workflow `publish.yml` and environment
`pypi`; without it the upload step fails. No API token is stored in the repository,
and pre-releases do not publish.

---
[Matthew Lincoln](https://matthewlincoln.net)
