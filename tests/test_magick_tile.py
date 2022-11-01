import json
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from pytest_subprocess import FakeProcess
from magick_tile.generator import SourceImage, Tile, DownsizedVersion
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


@pytest.fixture
def test_working_dir():
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_jpg() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "complete-usable-accurate.jpg"
    assert p.exists()
    return p


@pytest.fixture()
def test_png() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "complete-usable-accurate.png"
    assert p.exists()
    return p


@pytest.fixture
def tile_jpg() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "256,2,0,0,512,512.jpg"
    assert p.exists()
    return p


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
def example_source_image(
    test_output_dir: Path, test_working_dir: Path, test_jpg: Path
) -> SourceImage:
    return SourceImage(id="https://example.com/test.jpg", path=test_jpg, tile_size=512, target_dir=test_output_dir, working_dir=test_working_dir)  # type: ignore


class TestSourceImage:
    def test_dimenions(self, example_source_image: SourceImage):
        assert example_source_image.dimensions.width == 2676
        assert example_source_image.dimensions.height == 1572

    def test_minimum_dimension(self, example_source_image: SourceImage):
        assert example_source_image.minimum_dimension == 1572

    def test_downsizing_levels(self, example_source_image: SourceImage):
        assert example_source_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_source_image: SourceImage):
        assert example_source_image.scaling_factors == [2]

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
            "tiles": [{"width": 512, "scaleFactors": [2]}],
        }


@pytest.fixture
def example_tile(example_source_image: SourceImage, tile_jpg: Path) -> Tile:
    return Tile(original_path=tile_jpg, source_image=example_source_image)


@pytest.fixture
def example_downsized_version(example_source_image: SourceImage) -> DownsizedVersion:
    return DownsizedVersion(downsize_width=512, source_image=example_source_image)


class TestTile:
    def test_parsed_filename(self, example_tile: Tile):
        assert example_tile.parsed_filename == [256, 2, 0, 0, 512, 512]
        assert example_tile.sf == 2
        assert example_tile.x == 0
        assert example_tile.y == 0
        assert example_tile.w == 512
        assert example_tile.h == 512

    def test_file_w(self, example_tile: Tile):
        assert example_tile.file_w == 256

    def test_file_h(self, example_tile: Tile):
        assert example_tile.file_h == 256

    def test_target_dir(self, example_tile: Tile, test_output_dir: Path):
        assert example_tile.target_dir == test_output_dir / "0,0,512,512" / "256," / "0"

    def test_target_file(self, example_tile: Tile, test_output_dir: Path):
        assert (
            example_tile.target_file
            == test_output_dir / "0,0,512,512" / "256," / "0" / "default.jpg"
        )

    def test_resize(self, example_tile: Tile):
        target_file = example_tile.target_dir / "default.jpg"
        assert not target_file.exists()
        example_tile.resize()
        assert target_file.exists()


class TestDownsizedVersion:
    def test_target_directory(
        self, example_downsized_version: DownsizedVersion, test_output_dir: Path
    ):
        assert (
            example_downsized_version.target_directory
            == test_output_dir / "full" / "512," / "0"
        )
        assert (
            example_downsized_version.target_file
            == test_output_dir / "full" / "512," / "0" / "default.jpg"
        )

    def test_convert(self, example_downsized_version: DownsizedVersion):
        assert not example_downsized_version.target_file.exists()
        example_downsized_version.convert()
        assert example_downsized_version.target_file.exists()


class TestImageProcess:
    def test_generate_tile_files(
        self,
        example_source_image: SourceImage,
        test_working_dir: Path,
    ):
        assert example_source_image.working_dir == test_working_dir
        assert len(list(test_working_dir.glob("*"))) == 0
        example_source_image.generate_tile_files()
        first_image = test_working_dir / "1024,2,0,0,1024,1024.jpg"
        assert first_image.exists()

    def test_resize_tile_files(
        self,
        example_source_image: SourceImage,
        test_output_dir: Path,
    ):
        assert example_source_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_source_image.generate_tile_files()
        example_source_image.resize_tile_files()
        assert len(list(test_output_dir.glob("*"))) > 0
        first_image = test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg"
        assert first_image.exists()

    def test_generate_reduced_versions(
        self, example_source_image: SourceImage, test_output_dir: Path
    ):
        assert example_source_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_source_image.generate_reduced_versions()
        first_image = test_output_dir / "full" / "1024," / "0" / "default.jpg"
        assert first_image.exists()


class TestManifestOutput:
    def test_manifest_output(
        self, example_source_image: SourceImage, test_output_dir: Path
    ):
        info_file_path = test_output_dir / "info.json"
        assert not info_file_path.exists()
        example_source_image.write_info()
        assert info_file_path.exists()
        with open(info_file_path, "r") as infof:
            reread_obj = json.load(infof)
            assert reread_obj["id"] == example_source_image.id


class TestCompleteOutput:
    def test_all_outputs(
        self, example_source_image: SourceImage, test_output_dir: Path
    ):
        assert len(list(test_output_dir.glob("*"))) == 0
        example_source_image.convert()
        info_file_path = test_output_dir / "info.json"
        assert info_file_path.exists()
        assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()
        assert (
            test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg"
        ).exists()
