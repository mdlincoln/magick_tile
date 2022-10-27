import json

from magick_tile.generator import IIIFManifest, TileScale, TileSize
import pytest


@pytest.fixture
def example_manifest_object() -> IIIFManifest:
    return IIIFManifest(
        id="https://example.com/images/foobar",  # type: ignore
        sizes=[TileSize(width=512, height="full")],
        tiles=[TileScale(width=512, scaleFactors=[4, 2])],
        width=6000,
        height=4000,
    )


class TestManifest:
    def test_manifest(self, example_manifest_object: IIIFManifest):
        assert example_manifest_object.json(
            by_alias=True, exclude_none=True
        ) == json.dumps(
            {
                "@context": "http://iiif.io/api/image/3/context.json",
                "id": "https://example.com/images/foobar",
                "type": "ImageService3",
                "protocol": "http://iiif.io/api/image",
                "profile": "level0",
                "width": 6000,
                "height": 4000,
                "preferredFormats": ["jpg"],
                "sizes": [{"width": 512, "height": "full"}],
                "tiles": [{"width": 512, "scaleFactors": [4, 2]}],
            }
        )
