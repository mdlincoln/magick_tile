import json
from pathlib import Path

import pytest

from pytest_subprocess import FakeProcess
from magick_tile.generator import SourceImage, Tile, DownsizedVersion
from magick_tile.manifest import IIIFManifest, TileScale, TileSize
from magick_tile.settings import IIIFFormats


@pytest.fixture
def example_manifest_object(example_id: str) -> IIIFManifest:
    return IIIFManifest(
        id=example_id,  # type: ignore
        sizes=[TileSize(width=512, height="max")],
        tiles=[TileScale(width=512, scaleFactors=[4, 2])],
        width=6000,
        height=4000,
    )


class TestManifest:
    def test_manifest(self, example_manifest_object: IIIFManifest, example_id: str):
        assert example_manifest_object.json(
            by_alias=True, exclude_none=True
        ) == json.dumps(
            {
                "@context": "http://iiif.io/api/image/3/context.json",
                "id": example_id,
                "type": "ImageService3",
                "protocol": "http://iiif.io/api/image",
                "profile": "level0",
                "width": 6000,
                "height": 4000,
                "preferredFormats": ["jpg"],
                "sizes": [{"width": 512, "height": "max"}],
                "tiles": [{"width": 512, "scaleFactors": [4, 2]}],
            }
        )


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
def example_jpg_image(
    test_output_dir: Path, test_working_dir: Path, test_jpg: Path
) -> SourceImage:
    return SourceImage(id="https://example.com/test.jpg", path=test_jpg, tile_size=512, target_dir=test_output_dir, working_dir=test_working_dir)  # type: ignore


@pytest.fixture
def example_png_image(
    test_output_dir: Path, test_working_dir: Path, test_png: Path
) -> SourceImage:
    return SourceImage(id="https://example.com/test.png", path=test_png, tile_size=512, formats=["jpg", "png"], target_dir=test_output_dir, working_dir=test_working_dir)  # type: ignore


class TestSourceImage:
    def test_dimenions(self, example_jpg_image: SourceImage):
        assert example_jpg_image.dimensions.width == 2676
        assert example_jpg_image.dimensions.height == 1572

    def test_suffix(
        self, example_jpg_image: SourceImage, example_png_image: SourceImage
    ):
        assert example_jpg_image.format == "jpg"
        assert example_png_image.format == "png"

    def test_minimum_dimension(self, example_jpg_image: SourceImage):
        assert example_jpg_image.minimum_dimension == 1572

    def test_downsizing_levels(self, example_jpg_image: SourceImage):
        assert example_jpg_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_jpg_image: SourceImage):
        assert example_jpg_image.scaling_factors == [2]

    def test_manifest(self, example_jpg_image: SourceImage):
        assert example_jpg_image.manifest.dict(exclude_none=True) == {
            "context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.com/test.jpg",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 2676,
            "height": 1572,
            "preferredFormats": ["jpg"],
            "sizes": [
                {"width": 256, "height": "max"},
                {"width": 512, "height": "max"},
                {"width": 1024, "height": "max"},
                {"width": 2048, "height": "max"},
            ],
            "tiles": [{"width": 512, "scaleFactors": [2]}],
        }


class TestPngImage:
    def test_dimenions(self, example_png_image: SourceImage):
        assert example_png_image.dimensions.width == 2676
        assert example_png_image.dimensions.height == 1572

    def test_minimum_dimension(self, example_png_image: SourceImage):
        assert example_png_image.minimum_dimension == 1572

    def test_downsizing_levels(self, example_png_image: SourceImage):
        assert example_png_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_png_image: SourceImage):
        assert example_png_image.scaling_factors == [2]

    def test_manifest(self, example_png_image: SourceImage):
        assert example_png_image.manifest.dict(exclude_none=True) == {
            "context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.com/test.png",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 2676,
            "height": 1572,
            "preferredFormats": ["jpg", "png"],
            "sizes": [
                {"width": 256, "height": "max"},
                {"width": 512, "height": "max"},
                {"width": 1024, "height": "max"},
                {"width": 2048, "height": "max"},
            ],
            "tiles": [{"width": 512, "scaleFactors": [2]}],
        }


@pytest.fixture
def example_tile(example_jpg_image: SourceImage, tile_jpg: Path) -> Tile:
    return Tile(original_path=tile_jpg, source_image=example_jpg_image)


@pytest.fixture
def example_downsized_version(example_jpg_image: SourceImage) -> DownsizedVersion:
    return DownsizedVersion(downsize_width=512, source_image=example_jpg_image)


@pytest.fixture
def example_downsized_png(example_png_image: SourceImage) -> DownsizedVersion:
    return DownsizedVersion(
        downsize_width=512, source_image=example_png_image, format=IIIFFormats.png
    )


class TestTile:
    def test_parsed_filename(self, example_tile: Tile):
        assert example_tile.parsed_filename == [256, 2, 0, 0, 512, 512]
        assert example_tile.sf == 2
        assert example_tile.x == 0
        assert example_tile.y == 0
        assert example_tile.w == 512
        assert example_tile.h == 512

    def test_format(self, example_tile: Tile):
        assert example_tile.format == IIIFFormats.jpg

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


class TestPngDownsizedVersion:
    def test_target_directory(
        self, example_downsized_png: DownsizedVersion, test_output_dir: Path
    ):
        assert (
            example_downsized_png.target_directory
            == test_output_dir / "full" / "512," / "0"
        )
        assert (
            example_downsized_png.target_file
            == test_output_dir / "full" / "512," / "0" / "default.png"
        )

    def test_convert(self, example_downsized_version: DownsizedVersion):
        assert not example_downsized_version.target_file.exists()
        example_downsized_version.convert()
        assert example_downsized_version.target_file.exists()


class TestImageProcess:
    def test_generate_tile_files(
        self,
        example_jpg_image: SourceImage,
        test_working_dir: Path,
    ):
        assert example_jpg_image.working_dir == test_working_dir
        assert len(list(test_working_dir.glob("*"))) == 0
        example_jpg_image.generate_tile_files()
        (test_working_dir / "1024,2,0,0,1024,1024.jpg").exists()

    def test_resize_tile_files(
        self,
        example_jpg_image: SourceImage,
        test_output_dir: Path,
    ):
        assert example_jpg_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.generate_tile_files()
        example_jpg_image.resize_tile_files()
        assert len(list(test_output_dir.glob("*"))) > 0
        assert (
            test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg"
        ).exists()

    def test_generate_reduced_versions(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        assert example_jpg_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.generate_reduced_versions()
        assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()


class TestMultiFormatProcess:
    def test_generate_tile_files(
        self,
        example_png_image: SourceImage,
        test_working_dir: Path,
    ):
        assert example_png_image.working_dir == test_working_dir
        assert len(list(test_working_dir.glob("*"))) == 0
        example_png_image.generate_tile_files()
        assert (test_working_dir / "1024,2,0,0,1024,1024.jpg").exists()
        assert (test_working_dir / "1024,2,0,0,1024,1024.png").exists()

    def test_resize_tile_files(
        self,
        example_png_image: SourceImage,
        test_output_dir: Path,
    ):
        assert example_png_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_png_image.generate_tile_files()
        example_png_image.resize_tile_files()
        assert len(list(test_output_dir.glob("*"))) > 0
        assert (
            test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg"
        ).exists()
        assert (
            test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.png"
        ).exists()

    def test_generate_reduced_versions(
        self, example_png_image: SourceImage, test_output_dir: Path
    ):
        assert example_png_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_png_image.generate_reduced_versions()
        assert (test_output_dir / "full" / "1024," / "0" / "default.png").exists()
        assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()


class TestManifestOutput:
    def test_manifest_output(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        info_file_path = test_output_dir / "info.json"
        assert not info_file_path.exists()
        example_jpg_image.write_info()
        assert info_file_path.exists()
        with open(info_file_path, "r") as infof:
            reread_obj = json.load(infof)
            assert reread_obj["id"] == example_jpg_image.id


class TestCompleteOutput:
    def test_all_outputs(self, example_jpg_image: SourceImage, test_output_dir: Path):
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.convert()
        info_file_path = test_output_dir / "info.json"
        assert info_file_path.exists()
        assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()
        assert (
            test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg"
        ).exists()
