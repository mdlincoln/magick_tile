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

`--version` selects the IIIF Image API version that the output tree and its `info.json` target. Both versions are written as **Level 0** static trees: the `info.json` declares `level0` compliance, and the unscaled full-size image is written at the version's canonical location.

For a 2676×1572 source image generated with `--version 3.0` (the default):

```
<output>/
├── info.json
├── full/
│   ├── max/0/default.jpg        # unscaled full image: full/max/ for 3.0
│   ├── 256,150/0/default.jpg    # 3.0 canonical size dirs are w,h
│   ├── 512,301/0/default.jpg
│   ├── 1024,602/0/default.jpg
│   └── 2048,1203/0/default.jpg
└── 0,0,1024,1024/
    └── 512,/0/default.jpg       # region tiles
```

- **Version 3.0** (default): downsized full images live at `full/{w},{h}/0/` (the canonical `w,h` size form of Image API 3.0), and the unscaled full image at `full/max/0/`.
- **Version 2.1**: downsized full images live at `full/{w},/0/` (2.1's canonical `w,` form for listed sizes), and the unscaled full image at `full/full/0/` (2.1's `full` keyword, renamed `max` in 3.0).
- **Region tiles** are always served at the `w,` size form (`{x},{y},{w},{h}/{tile},/0/default.jpg`) for both versions. This is a documented deviation from 3.0's canonical `w,h` tile form, matching the reference implementation [zimeon/iiif](https://github.com/zimeon/iiif/blob/master/iiif_static.py) and the size form requested by OpenSeadragon ≥ 1.2.1.
- **Formats beyond jpg** are declared in `info.json`: 3.0 payloads list them in `extraFormats` (with everything generated in `preferredFormats`), and 2.1 payloads append a `{"formats": [...]}` description object to the `level0` profile URI.
- **jpg must be included in `--format` for a certifiable tree**: the compliance tables of both Image API 2.1 and 3.0 require jpg support at every compliance level, so a run whose `--format` values exclude jpg produces a tree that no compliance level can certify.
- **Breaking changes in 0.2.0**: 3.0 trees now write canonical `w,h` size directories (previously `w,`) and gain a `full/max/0/` full-size image; 2.1 payloads changed shape (`@type` is now emitted, and `profile` declares `level0` instead of `level1`, widening to a list when formats beyond jpg are generated). Re-generate existing trees when upgrading.

Before a release you can spot-check a generated `info.json` against the official IIIF Image API validator at https://iiif.io/api/image/validator/.

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

Bump `version` in `pyproject.toml`, then build and upload:

```
uv build      # sdist + wheel, written to dist/
uv publish    # upload to PyPI
```

`uv publish` takes credentials from `UV_PUBLISH_TOKEN` or `--token`; a PyPI API token
scoped to this project is the simplest credential to use.

---
[Matthew Lincoln](https://matthewlincoln.net)
