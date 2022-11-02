import typer
from pathlib import Path

from magick_tile import generator, settings

app = typer.Typer()


@app.command()
def convert(
    source: Path = typer.Argument(
        ...,
        show_default=False,
        file_okay=True,
        dir_okay=False,
        readable=True,
        exists=True,
    ),
    output: Path = typer.Argument(
        ...,
        show_default=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Destination directory for tiles",
    ),
    identifier: str = typer.Argument(
        ...,
        show_default=False,
        help="Image identifier to be written to final info.json (e.g. https://example.com/iiif/my_image)",
    ),
    tile_size: int = typer.Option(default=512, help="Tile size to produce"),
    format: list[settings.IIIFFormats] = typer.Option(
        default=["jpg"],
        help="File formats to generate (must be supported by Imagemagick's 'convert')",
    ),
    version: settings.IIIFVersions = typer.Option(
        default="3.0", help="IIIF Image API version"
    ),
):
    """
    Efficiently create derivative tiles of a very large image, and structure them into directories compliant with IIIF Level 0.
    """

    si = generator.SourceImage(
        id=identifier, path=source, tile_size=tile_size, target_dir=output, formats=format, version=version  # type: ignore
    )
    si.convert()
