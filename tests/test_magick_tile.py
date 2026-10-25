import json
import subprocess
from math import ceil
from pathlib import Path

import pytest

from pytest_subprocess import FakeProcess
from magick_tile.generator import (
    DownsizedVersion,
    SourceImage,
    Tile,
    declared_size_segments,
    scaling_factors_for,
    whole_image_segment,
    whole_image_size,
)
from magick_tile.manifest import IIIFManifest, IIIFManifest_3_0, TileScale, TileSize
from magick_tile.settings import IIIFFormats, IIIFVersions

# Aspect-correct half-up heights for the 2676x1572 fixture image, keyed by
# downsized width (e.g. 1024 x 1572 / 2676 = 601.54 -> 602).
EXPECTED_SIZES = [
    {"width": 256, "height": 150},
    {"width": 512, "height": 301},
    {"width": 1024, "height": 602},
    {"width": 2048, "height": 1203},
]


def pixel_dimensions(path: Path) -> tuple[int, int]:
    """Measure a file with imagemagick's identify, independently of the
    library under test."""
    written = subprocess.run(
        ["identify", "-format", "%w %h", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return int(written[0]), int(written[1])


class TestScalingFactors:
    """The pyramid's level list, checked without ImageMagick or an asset.

    Each row asserts both directions: the top level covers the whole image in
    one tile, and the level below it does not. An image at or below one tile has
    no level below, so its criterion is that the list is exactly [1].
    """

    @pytest.mark.parametrize(
        "width, height, expected",
        [
            (3202, 4096, [1, 2, 4, 8]),  # e2e fixture: longer side exactly 8 tiles
            (2676, 1572, [1, 2, 4, 8]),
            (4096, 2048, [1, 2, 4, 8]),  # elongated: would otherwise stop at 2
            (400, 3200, [1, 2, 4, 8]),  # tall
            (2048, 2048, [1, 2, 4]),
            (1024, 1024, [1, 2]),
            (600, 400, [1, 2]),
            (900, 200, [1, 2]),  # wide
            (512, 512, [1]),
            (300, 200, [1]),
            (256, 256, [1]),
        ],
    )
    def test_scaling_factors_for_dimensions(
        self, width: int, height: int, expected: list[int]
    ) -> None:
        tile_size = 512
        factors = scaling_factors_for(width, height, tile_size)
        assert factors == expected
        assert factors == [1 << exponent for exponent in range(len(factors))]

        top = factors[-1]
        assert top * tile_size >= max(width, height)
        if len(factors) > 1:
            assert (top // 2) * tile_size < max(width, height)


class TestWholeImageArithmetic:
    """The coarsest level's size and its collision rule.

    The collision cannot be reproduced from the repository's images — neither
    the unit asset (2676x1572) nor the e2e fixture (3202x4096) gives a coarsest
    width that is also a declared width — so it is pinned arithmetically here
    and executed through ImageMagick in
    ``TestImageProcess.test_whole_image_level_skips_a_declared_size_end_to_end``.
    """

    @pytest.mark.parametrize(
        "width, height, expected",
        [
            # 4096 / 8 = 512 exactly; half-up would wrongly give 513.
            (3202, 4096, (401, 512)),
            (2676, 1572, (335, 197)),
            (4096, 3011, (512, 377)),
            (512, 512, (512, 512)),
        ],
    )
    def test_whole_image_size(
        self, width: int, height: int, expected: tuple[int, int]
    ) -> None:
        assert whole_image_size(width, height, 512) == expected

    def test_whole_image_level_yields_to_a_declared_size(self) -> None:
        declared_widths = [256, 512, 1024, 2048]

        # 2.1's size segment is width-only, so the coarsest level of a
        # 4096x3011 image and the declared size 512 share a directory while
        # disagreeing about the height. The declared file must keep its own.
        two_one_declared = declared_size_segments(
            IIIFVersions._2_1, 4096, 3011, declared_widths
        )
        assert "512," in two_one_declared
        assert whole_image_segment(4096, 3011, 512, IIIFVersions._2_1) in (
            two_one_declared
        )

        # 3.0's segment carries the height, so 512,377 is a directory of its
        # own and has to be written even though 512,376 is declared.
        three_oh_declared = declared_size_segments(
            IIIFVersions._3_0, 4096, 3011, declared_widths
        )
        assert "512,376" in three_oh_declared
        assert whole_image_segment(4096, 3011, 512, IIIFVersions._3_0) == "512,377"
        assert whole_image_segment(4096, 3011, 512, IIIFVersions._3_0) not in (
            three_oh_declared
        )

        # A 4096x2048 image's coarsest level is exactly the declared size 512
        # in 3.0, at the same geometry: a benign collision, still skipped.
        assert whole_image_segment(4096, 2048, 512, IIIFVersions._3_0) == "512,256"
        assert whole_image_segment(4096, 2048, 512, IIIFVersions._3_0) in (
            declared_size_segments(IIIFVersions._3_0, 4096, 2048, declared_widths)
        )


@pytest.fixture
def example_manifest_object(example_id: str) -> IIIFManifest:
    # Hand-built fixture: 512 x 4000 / 6000 = 341.33 -> 341. The half-up
    # formula itself is exercised via TestSourceImage.test_manifest.
    return IIIFManifest_3_0(
        id=example_id,
        sizes=[TileSize(width=512, height=341)],
        tiles=[TileScale(width=512, scaleFactors=[4, 2])],
        width=6000,
        height=4000,
    )


class TestManifest:
    def test_manifest(self, example_manifest_object: IIIFManifest, example_id: str):
        # Compare parsed payloads rather than raw strings: key order follows the
        # model's field order, which is not part of the IIIF response contract.
        assert json.loads(
            example_manifest_object.model_dump_json(by_alias=True, exclude_none=True)
        ) == {
            "@context": "http://iiif.io/api/image/3/context.json",
            "id": example_id,
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 6000,
            "height": 4000,
            "sizes": [{"width": 512, "height": 341}],
            "tiles": [{"width": 512, "scaleFactors": [4, 2]}],
        }


@pytest.fixture
def fake_convert():
    # FakeProcess implements the context-manager protocol at runtime, but its
    # __exit__ signature is not modeled in a way ty accepts.
    with FakeProcess.context() as nested_process:  # ty: ignore[invalid-context-manager]
        nested_process.register(["convert"])
        yield


class TestImagemagick:
    @pytest.mark.skip
    def test_missing_im(self, fp):
        with pytest.raises(Exception):
            import magick_tile  # noqa: F401 — import runs the ImageMagick check

    def test_has_im(self, fake_convert):
        import magick_tile  # noqa: F401 — import runs the ImageMagick check

        assert True


@pytest.fixture
def example_jpg_image(
    test_output_dir: Path, test_working_dir: Path, test_jpg: Path
) -> SourceImage:
    return SourceImage(
        id="https://example.com/test.jpg",
        path=test_jpg,
        tile_size=512,
        target_dir=test_output_dir,
        working_dir=test_working_dir,
    )


@pytest.fixture
def example_png_image(
    test_output_dir: Path, test_working_dir: Path, test_png: Path
) -> SourceImage:
    return SourceImage(
        id="https://example.com/test.png",
        path=test_png,
        tile_size=512,
        formats=["jpg", "png"],
        target_dir=test_output_dir,
        working_dir=test_working_dir,
    )


@pytest.fixture
def example_2_1_image(
    test_output_dir: Path, test_working_dir: Path, test_jpg: Path
) -> SourceImage:
    return SourceImage(
        id="https://example.com/test.jpg",
        path=test_jpg,
        tile_size=512,
        target_dir=test_output_dir,
        working_dir=test_working_dir,
        version=IIIFVersions._2_1,
    )


@pytest.fixture
def example_png_2_1_image(
    test_output_dir: Path, test_working_dir: Path, test_png: Path
) -> SourceImage:
    return SourceImage(
        id="https://example.com/test.png",
        path=test_png,
        tile_size=512,
        formats=["jpg", "png"],
        target_dir=test_output_dir,
        working_dir=test_working_dir,
        version=IIIFVersions._2_1,
    )


class TestSourceImage:
    def test_dimenions(self, example_jpg_image: SourceImage):
        assert example_jpg_image.dimensions.width == 2676
        assert example_jpg_image.dimensions.height == 1572

    def test_suffix(
        self, example_jpg_image: SourceImage, example_png_image: SourceImage
    ):
        assert example_jpg_image.format == "jpg"
        assert example_png_image.format == "png"

    def test_downsizing_levels(self, example_jpg_image: SourceImage):
        assert example_jpg_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_jpg_image: SourceImage):
        assert example_jpg_image.scaling_factors == [1, 2, 4, 8]

    def test_downsized_height(self, example_jpg_image: SourceImage):
        assert [
            example_jpg_image.downsized_height(width)
            for width in [256, 512, 1024, 2048]
        ] == [150, 301, 602, 1203]

    def test_manifest(self, example_jpg_image: SourceImage):
        assert example_jpg_image.manifest.model_dump(
            mode="json", exclude_none=True
        ) == {
            "context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.com/test.jpg",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 2676,
            "height": 1572,
            "preferredFormats": ["jpg"],
            "sizes": EXPECTED_SIZES,
            "tiles": [{"width": 512, "scaleFactors": [1, 2, 4, 8]}],
        }


class TestPngImage:
    def test_dimenions(self, example_png_image: SourceImage):
        assert example_png_image.dimensions.width == 2676
        assert example_png_image.dimensions.height == 1572

    def test_downsizing_levels(self, example_png_image: SourceImage):
        assert example_png_image.downsizing_levels == [256, 512, 1024, 2048]

    def test_scaling_factors(self, example_png_image: SourceImage):
        assert example_png_image.scaling_factors == [1, 2, 4, 8]

    def test_manifest(self, example_png_image: SourceImage):
        assert example_png_image.manifest.model_dump(
            mode="json", exclude_none=True
        ) == {
            "context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.com/test.png",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": 2676,
            "height": 1572,
            "preferredFormats": ["jpg", "png"],
            "extraFormats": ["png"],
            "sizes": EXPECTED_SIZES,
            "tiles": [{"width": 512, "scaleFactors": [1, 2, 4, 8]}],
        }


class TestVersionPayloads:
    def test_manifest_3_0_extra_formats(self, example_png_image: SourceImage):
        payload = json.loads(
            example_png_image.manifest.model_dump_json(by_alias=True, exclude_none=True)
        )
        # extraFormats lists only formats beyond the level0-required jpg,
        # while preferredFormats lists everything the tree serves.
        assert payload["extraFormats"] == ["png"]
        assert payload["preferredFormats"] == ["jpg", "png"]

    def test_manifest_2_1_payload(self, example_2_1_image: SourceImage):
        payload = json.loads(
            example_2_1_image.manifest.model_dump_json(by_alias=True, exclude_none=True)
        )
        assert payload["@context"] == "http://iiif.io/api/image/2/context.json"
        assert payload["@id"] == "https://example.com/test.jpg"
        assert payload["@type"] == "iiif:Image"
        assert payload["protocol"] == "http://iiif.io/api/image"
        assert payload["profile"] == "http://iiif.io/api/image/2/level0.json"
        assert payload["width"] == 2676
        assert payload["height"] == 1572
        assert payload["sizes"] == EXPECTED_SIZES
        # 2.x has neither preferredFormats nor 3.0's unqualified "type" key.
        assert "preferredFormats" not in payload
        assert "type" not in payload
        assert "extraFormats" not in payload

    def test_manifest_2_1_extra_formats(self, example_png_2_1_image: SourceImage):
        payload = json.loads(
            example_png_2_1_image.manifest.model_dump_json(
                by_alias=True, exclude_none=True
            )
        )
        assert payload["profile"] == [
            "http://iiif.io/api/image/2/level0.json",
            {"formats": ["png"]},
        ]
        assert "extraFormats" not in payload


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


@pytest.fixture
def example_downsized_2_1(example_2_1_image: SourceImage) -> DownsizedVersion:
    return DownsizedVersion(downsize_width=512, source_image=example_2_1_image)


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
        assert (
            example_tile.target_dir == test_output_dir / "0,0,512,512" / "256,256" / "0"
        )

    def test_target_file(self, example_tile: Tile, test_output_dir: Path):
        assert (
            example_tile.target_file
            == test_output_dir / "0,0,512,512" / "256,256" / "0" / "default.jpg"
        )

    def test_resize(self, example_tile: Tile):
        target_file = example_tile.target_dir / "default.jpg"
        assert not target_file.exists()
        example_tile.resize()
        assert target_file.exists()


class TestRegionTileSizeSegment:
    def test_region_tile_size_segment_is_version_correct(
        self,
        example_jpg_image: SourceImage,
        example_2_1_image: SourceImage,
        test_working_dir: Path,
    ):
        # 1000x600 region scaled by 2 writes a 500x300 file. 3.0 addresses it as
        # w,h; 2.1 addresses it as w,.
        original_path = test_working_dir / "1024,2,0,0,1000,600.jpg"
        three_oh = Tile(original_path=original_path, source_image=example_jpg_image)
        two_one = Tile(original_path=original_path, source_image=example_2_1_image)
        assert three_oh.size_path_segment == "500,300"
        assert two_one.size_path_segment == "500,"
        assert three_oh.target_dir == (
            example_jpg_image.target_dir / "0,0,1000,600" / "500,300" / "0"
        )
        assert two_one.target_dir == (
            example_2_1_image.target_dir / "0,0,1000,600" / "500," / "0"
        )

    def test_edge_tile_height_rounds_up(
        self, example_jpg_image: SourceImage, test_working_dir: Path
    ):
        # 975 / 2 = 487.5. Clients request the scaled edge height rounded up, so
        # the file has to be addressed as 488.
        original_path = test_working_dir / "1024,2,0,0,1024,975.jpg"
        edge_tile = Tile(original_path=original_path, source_image=example_jpg_image)
        assert edge_tile.file_h == 488
        assert edge_tile.size_path_segment == "512,488"

    def test_resize_writes_declared_dimensions(self, test_working_dir: Path):
        """The written file's pixels match the size directory that addresses
        it, even when the scaled dimensions do not share the region's aspect
        ratio."""
        source = SourceImage(
            id="https://example.com/test.jpg",
            path=test_working_dir / "source.jpg",
            tile_size=512,
            target_dir=test_working_dir / "out",
            working_dir=test_working_dir,
        )
        # 245x184 at scale factor 4 lies between 61x46 and 62x46, so an
        # aspect-preserving resize would write 61x46 into a 62,46 directory.
        original_path = test_working_dir / "245,4,0,0,245,184.jpg"
        subprocess.run(
            ["convert", "-size", "245x184", "xc:white", str(original_path)],
            check=True,
            capture_output=True,
        )
        tile = Tile(original_path=original_path, source_image=source)
        assert tile.size_path_segment == "62,46"
        tile.resize()
        written = subprocess.run(
            ["identify", "-format", "%w %h", str(tile.target_file)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert tuple(int(value) for value in written) == (62, 46)


class TestDownsizedVersion:
    def test_target_directory(
        self, example_downsized_version: DownsizedVersion, test_output_dir: Path
    ):
        assert example_downsized_version.downsize_height == 301
        # 3.0 canonical size form is w,h (Image API 3.0 §4.8).
        assert (
            example_downsized_version.target_directory
            == test_output_dir / "full" / "512,301" / "0"
        )
        assert (
            example_downsized_version.target_file
            == test_output_dir / "full" / "512,301" / "0" / "default.jpg"
        )

    def test_convert(self, example_downsized_version: DownsizedVersion):
        assert not example_downsized_version.target_file.exists()
        example_downsized_version.convert()
        assert example_downsized_version.target_file.exists()


class TestDownsizedVersion21:
    def test_target_directory(
        self, example_downsized_2_1: DownsizedVersion, test_output_dir: Path
    ):
        # 2.1 §5.2 canonical size form for listed sizes is w,.
        assert (
            example_downsized_2_1.target_directory
            == test_output_dir / "full" / "512," / "0"
        )
        assert (
            example_downsized_2_1.target_file
            == test_output_dir / "full" / "512," / "0" / "default.jpg"
        )

    def test_convert(self, example_downsized_2_1: DownsizedVersion):
        assert not example_downsized_2_1.target_file.exists()
        example_downsized_2_1.convert()
        assert example_downsized_2_1.target_file.exists()


class TestPngDownsizedVersion:
    def test_target_directory(
        self, example_downsized_png: DownsizedVersion, test_output_dir: Path
    ):
        assert (
            example_downsized_png.target_directory
            == test_output_dir / "full" / "512,301" / "0"
        )
        assert (
            example_downsized_png.target_file
            == test_output_dir / "full" / "512,301" / "0" / "default.png"
        )

    def test_convert(self, example_downsized_png: DownsizedVersion):
        assert not example_downsized_png.target_file.exists()
        example_downsized_png.convert()
        assert example_downsized_png.target_file.exists()


class TestImageProcess:
    def test_generate_tile_files(
        self,
        example_jpg_image: SourceImage,
        test_working_dir: Path,
    ):
        assert example_jpg_image.working_dir == test_working_dir
        assert len(list(test_working_dir.glob("*"))) == 0
        example_jpg_image.generate_tile_files()
        assert (test_working_dir / "1024,2,0,0,1024,1024.jpg").exists()

    def test_tiles_are_not_duplicated_across_scale_factors(
        self, example_jpg_image: SourceImage
    ):
        dims = example_jpg_image.dimensions
        example_jpg_image.generate_tile_files()
        tile_size = example_jpg_image.tile_size
        expected = sum(
            ceil(dims.width / (tile_size * sf)) * ceil(dims.height / (tile_size * sf))
            for sf in example_jpg_image.scaling_factors
        )
        # Every level's crops are collected once: an unscoped glob in the
        # working directory would re-add earlier levels' tiles.
        assert len({t.original_path for t in example_jpg_image.tiles}) == expected
        assert len(example_jpg_image.tiles) == expected

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
            test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.jpg"
        ).exists()

    def test_generate_reduced_versions(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        assert example_jpg_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.generate_reduced_versions()
        assert (test_output_dir / "full" / "1024,602" / "0" / "default.jpg").exists()

    def test_generate_full_size(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.generate_full_size()
        assert (test_output_dir / "full" / "max" / "0" / "default.jpg").exists()

    def test_generate_whole_image_level(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        """The coarsest level of the 2676x1572 asset is 335x197: the `full`
        spelling of the level's single whole-image tile."""
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.generate_whole_image_level()
        target = test_output_dir / "full" / "335,197" / "0" / "default.jpg"
        assert target.exists()
        assert pixel_dimensions(target) == (335, 197)

    def test_generate_whole_image_level_2_1(
        self, example_2_1_image: SourceImage, test_output_dir: Path
    ):
        assert len(list(test_output_dir.glob("*"))) == 0
        example_2_1_image.generate_whole_image_level()
        target = test_output_dir / "full" / "335," / "0" / "default.jpg"
        assert target.exists()
        assert pixel_dimensions(target) == (335, 197)

    def test_whole_image_level_skips_a_declared_size_end_to_end(
        self, test_working_dir: Path
    ):
        """A colliding segment leaves the declared file at its declared size.

        4096x3011 at tile 512 has a coarsest level of 512x377, while 2.1's
        width-only declared size 512 is 512x376 — the same directory. The
        declared pass runs first, so the skip is what keeps its dimensions.
        """
        source = self._colliding_source(test_working_dir, IIIFVersions._2_1)

        source.generate_reduced_versions()
        declared = test_working_dir / "out" / "full" / "512," / "0" / "default.jpg"
        assert declared.exists()
        assert pixel_dimensions(declared) == (512, 376)

        source.generate_whole_image_level()
        assert pixel_dimensions(declared) == (512, 376)

    def test_whole_image_level_is_written_beside_a_same_width_declared_size(
        self, test_working_dir: Path
    ):
        """3.0's segment carries the height, so the same-image collision is not
        one: 512,377 is a directory of its own and has to be written next to the
        declared 512,376. A skip keyed on the width alone would drop a file two
        clients request."""
        source = self._colliding_source(test_working_dir, IIIFVersions._3_0)

        source.generate_reduced_versions()
        declared = test_working_dir / "out" / "full" / "512,376" / "0" / "default.jpg"
        assert pixel_dimensions(declared) == (512, 376)

        source.generate_whole_image_level()
        level = test_working_dir / "out" / "full" / "512,377" / "0" / "default.jpg"
        assert level.exists()
        assert pixel_dimensions(level) == (512, 377)
        # The declared thumbnail is untouched by the extra write.
        assert pixel_dimensions(declared) == (512, 376)

    def test_collision_leaves_the_region_spelling_at_the_levels_size(
        self, test_working_dir: Path
    ):
        """The documented consequence of skipping in 2.1: the tile pipeline still
        writes the whole image at the level's own size, so the explicit-region
        client gets 512x377 while the width-only `full` directory keeps the
        declared 512x376."""
        source = self._colliding_source(test_working_dir, IIIFVersions._2_1)
        source.generate_reduced_versions()
        source.generate_tile_files()
        source.resize_tile_files()
        source.generate_whole_image_level()

        region = (
            test_working_dir / "out" / "0,0,4096,3011" / "512," / "0" / "default.jpg"
        )
        assert region.exists()
        assert pixel_dimensions(region) == (512, 377)
        assert pixel_dimensions(
            test_working_dir / "out" / "full" / "512," / "0" / "default.jpg"
        ) == (512, 376)

    @staticmethod
    def _colliding_source(test_working_dir: Path, version: IIIFVersions) -> SourceImage:
        """A 4096x3011 white source at tile 512, whose coarsest level is 512x377
        and whose declared size 512 is 512x376."""
        source_path = test_working_dir / "source.jpg"
        subprocess.run(
            ["convert", "-size", "4096x3011", "xc:white", str(source_path)],
            check=True,
            capture_output=True,
        )
        source = SourceImage(
            id="https://example.com/test.jpg",
            path=source_path,
            tile_size=512,
            target_dir=test_working_dir / "out",
            working_dir=test_working_dir,
            version=version,
        )
        assert source.whole_image_level_size == (512, 377)
        return source


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
            test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.jpg"
        ).exists()
        assert (
            test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.png"
        ).exists()

    def test_generate_reduced_versions(
        self, example_png_image: SourceImage, test_output_dir: Path
    ):
        assert example_png_image.target_dir == test_output_dir
        assert len(list(test_output_dir.glob("*"))) == 0
        example_png_image.generate_reduced_versions()
        assert (test_output_dir / "full" / "1024,602" / "0" / "default.png").exists()
        assert (test_output_dir / "full" / "1024,602" / "0" / "default.jpg").exists()


class TestManifestOutput:
    def test_manifest_output(
        self, example_jpg_image: SourceImage, test_output_dir: Path
    ):
        info_file_path = test_output_dir / "info.json"
        assert not info_file_path.exists()
        example_jpg_image.write_info()
        assert info_file_path.exists()
        with open(info_file_path, encoding="utf-8") as infof:
            reread_obj = json.load(infof)
            # HttpUrl is not a str subclass in pydantic v2, so compare the
            # serialized form.
            assert reread_obj["id"] == str(example_jpg_image.id)


class TestCompleteOutput:
    def test_all_outputs(self, example_jpg_image: SourceImage, test_output_dir: Path):
        assert len(list(test_output_dir.glob("*"))) == 0
        example_jpg_image.convert()
        info_file_path = test_output_dir / "info.json"
        assert info_file_path.exists()
        assert (test_output_dir / "full" / "1024,602" / "0" / "default.jpg").exists()
        assert (test_output_dir / "full" / "max" / "0" / "default.jpg").exists()
        # The coarsest level, under both spellings: region tile from the tile
        # pipeline, `full` derivative from the whole-image writer.
        assert (test_output_dir / "full" / "335,197" / "0" / "default.jpg").exists()
        assert (
            test_output_dir / "0,0,2676,1572" / "335,197" / "0" / "default.jpg"
        ).exists()
        assert (
            test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.jpg"
        ).exists()


class TestConstraintGuard:
    def test_full_size_rejects_constraints(
        self, test_jpg: Path, test_output_dir: Path, test_working_dir: Path
    ):
        constrained = SourceImage(
            id="https://example.com/test.jpg",
            path=test_jpg,
            tile_size=512,
            target_dir=test_output_dir,
            working_dir=test_working_dir,
            max_width=1000,
        )
        with pytest.raises(NotImplementedError):
            constrained.convert()
        # The guard fires before any subprocess runs: no partial output tree,
        # not even a stray tile directory.
        assert list(test_output_dir.glob("*")) == []
        assert not (test_output_dir / "info.json").exists()
        assert not (test_output_dir / "full").exists()
