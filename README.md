# magick-tile

[![PyPi version](https://img.shields.io/pypi/v/magick-tile.svg)](https://pypi.org/project/magick-tile/)
[![pytest](https://github.com/mdlincoln/magick_tile/actions/workflows/pytest.yml/badge.svg)](https://github.com/mdlincoln/magick_tile/actions/workflows/pytest.yml)

This package and command-line utility relies on Imagemagick to efficiently create derivative tiles of a very large image, and structure them into directories compliant with [IIIF Level 0](https://iiif.io/api/image/3.0/compliance/#5-level-0-compliance) specification for static sites.

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
 Usage: magick_tile [OPTIONS] SOURCE OUTPUT IDENTIFIER

 Efficiently create derivative tiles of a very large image, and structure them into
 directories compliant with IIIF Level 0.

╭─ Arguments ──────────────────────────────────────────────────────────────────────╮
│ *    source          FILE       [required]                                       │
│ *    output          DIRECTORY  Destination directory for tiles [required]       │
│ *    identifier      TEXT       Image identifier to be written to final          │
│                                 info.json (e.g.                                  │
│                                 https://example.com/iiif/my_image)               │
│                                 [required]                                       │
╰──────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────╮
│ --tile-size                 INTEGER                   Tile size to produce       │
│                                                       [default: 512]             │
│ --format                    [jpg|tif|png|gif|jp2|pdf  File formats to generate   │
│                             |webp]                    (must be supported by      │
│                                                       Imagemagick's 'convert')   │
│                                                       [default: jpg]             │
│ --install-completion                                  Install completion for the │
│                                                       current shell.             │
│ --show-completion                                     Show completion for the    │
│                                                       current shell, to copy it  │
│                                                       or customize the           │
│                                                       installation.              │
│ --help                                                Show this message and      │
│                                                       exit.                      │
╰──────────────────────────────────────────────────────────────────────────────────╯

```

This will create and populate the specified output directory with tiles from a given image.

N.b. because several of the Imagemagick utilities called here already utilize multiple cores, returns for running this script in parallel diminish rapidly.

---
[Matthew Lincoln](https://matthewlincoln.net)
