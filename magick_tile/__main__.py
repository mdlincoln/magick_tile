import typer
from pathlib import Path

from magick_tile import generator
from pydantic import HttpUrl

app = typer.Typer()


@app.command()
def convert(
    source: Path = typer.Argument(...),
    output: Path = typer.Argument(..., help="Destination directory for tiles"),
    identifier: HttpUrl = typer.Argument(
        ...,
        help="Image identifier to be written to final info.json (e.g. https://example.com/iiif/my_image)",
    ),
    tile_size: int = typer.Argument(default=512, help="Tile size to produce"),
):
    """
    IIIF Image API Level-0 static file generator.
    """

    si = generator.SourceImage(
        id=identifier, path=source, tile_size=tile_size, target_dir=output
    )
    si.convert()
