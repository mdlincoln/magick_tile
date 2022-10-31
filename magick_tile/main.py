import typer
from pathlib import Path

from magick_tile import generator

app = typer.Typer()


@app.command()
def convert(
    source: Path = typer.Argument(...),
    output: Path = typer.Argument(..., help="Destination directory for tiles"),
    identifier: str = typer.Argument(
        ...,
        help="Image identifier to be written to final info.json (e.g. https://example.com/iiif/my_image)",
    ),
    tile_size: int = typer.Option(default=512, help="Tile size to produce"),
):
    """
    IIIF Image API Level-0 static file generator.
    """

    si = generator.SourceImage(
        id=identifier, path=source, tile_size=tile_size, target_dir=output  # type: ignore
    )
    si.convert()
