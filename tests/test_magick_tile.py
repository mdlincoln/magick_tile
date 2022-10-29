import json
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from pytest_subprocess import FakeProcess
from magick_tile.generator import SourceImage, Tile
from magick_tile.manifest import IIIFManifest, TileScale, TileSize


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


@pytest.fixture
def test_output_dir():
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture()
def test_image() -> Path:
    return Path(__file__).parent.joinpath("complete-usable-accurate.png")


@pytest.fixture
def fake_convert():
    with FakeProcess.context() as nested_process:
        nested_process.register(["convert"])
        yield


class TestImagemagick:
    @pytest.mark.skip
    def test_missing_im(self, fp):
        with pytest.raises(Exception) as ex:
            import magick_tile

    def test_has_im(self, fake_convert):
        import magick_tile

        assert True


@pytest.fixture
def example_source_image(test_output_dir: Path, test_image: Path) -> SourceImage:
    return SourceImage(id="https://example.com/test.jpg", path=test_image, tile_size=64, target_dir=test_output_dir)  # type: ignore


class TestSourceImage:
    def test_dimenions(self, example_source_image: SourceImage):
        assert example_source_image.dimensions.width == 2676
        assert example_source_image.dimensions.height == 1572

    def test_minimum_dimension(self, example_source_image: SourceImage):
        assert example_source_image.minimum_dimension == 1572

    def test_downsizing_levels(self, example_source_image: SourceImage):
        assert example_source_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_source_image: SourceImage):
        assert example_source_image.scaling_factors == [2, 4, 8, 16]

    def test_manifest(self, example_source_image: SourceImage):
        assert example_source_image.manifest.dict(exclude_none=True) == {
            "context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.com/test.jpg",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 2676,
            "height": 1572,
            "preferredFormats": ["jpg"],
            "sizes": [
                {"width": 256, "height": "full"},
                {"width": 512, "height": "full"},
                {"width": 1024, "height": "full"},
                {"width": 2048, "height": "full"},
            ],
            "tiles": [{"width": 64, "scaleFactors": [2, 4, 8, 16]}],
        }


@pytest.fixture
def tile_image() -> Path:
    return Path(__file__).parent.joinpath("tile_image.jpg")


@pytest.fixture()
def example_tile(example_source_image: SourceImage, tile_image: Path) -> Tile:
    return Tile(original_path=tile_image, source_image=example_source_image)


class TestTile:
    def test_parsed_filename(self, example_tile: Tile):
        pass
