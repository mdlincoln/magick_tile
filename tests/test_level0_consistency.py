"""End-to-end checks that a fully generated tree matches the IIIF Image API
Level 0 contract for its declared version: version-correct info.json payloads,
canonical file locations, pixel dimensions matching every declared size, and
tiles laid out per the region-grid algorithm."""

import json
import math
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, NamedTuple

import pytest

from magick_tile.generator import SourceImage
from magick_tile.settings import IIIFVersions

ASSET_JPG = Path(__file__).parent / "assets" / "complete-usable-accurate.jpg"
IDENTIFIER = "https://example.com/test.jpg"

# Canonical size-directory form for listed sizes: Image API 3.0 §4.8 declares
# canonical sizes as w,h, while 2.1 §5.2 directs clients to request listed
# sizes as w,.
CANONICAL_SIZE_SEGMENT: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "{w},{h}",
    IIIFVersions._2_1: "{w},",
}

# Canonical size-directory form for region tiles: 3.0 §4.8 addresses a tile
# by w,h, while 2.1 §5.2 addresses it by w,.
REGION_TILE_SEGMENT: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "{tile},{tile}",
    IIIFVersions._2_1: "{tile},",
}

# Canonical full-size directory: 3.0 §4.8 uses the "max" keyword; 2.1 §4.2
# used "full".
FULL_SIZE_SEGMENT: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "max",
    IIIFVersions._2_1: "full",
}


class ConvertedTree(NamedTuple):
    version: IIIFVersions
    info: dict
    output_dir: Path


def pixel_dimensions(path: Path) -> tuple[int, int]:
    """Measure a file with imagemagick's identify, independently of the
    library under test."""
    out = subprocess.run(
        ["identify", "-format", "%w %h", str(path)],
        capture_output=True,
        check=True,
    ).stdout.decode()
    width, height = out.split()
    return int(width), int(height)


@pytest.fixture(scope="module", params=["3.0", "2.1"])
def converted_tree(request: pytest.FixtureRequest) -> Iterator[ConvertedTree]:
    """Run one full conversion per API version, shared by every test in this
    module."""
    version = IIIFVersions(request.param)
    with TemporaryDirectory() as out, TemporaryDirectory() as work:
        source = SourceImage(
            id=IDENTIFIER,
            path=ASSET_JPG,
            tile_size=512,
            target_dir=Path(out),
            working_dir=Path(work),
            version=version,
        )
        source.convert()
        info = json.loads((Path(out) / "info.json").read_text())
        yield ConvertedTree(version=version, info=info, output_dir=Path(out))


def size_path(tree: ConvertedTree, size: dict) -> Path:
    segment = CANONICAL_SIZE_SEGMENT[tree.version].format(
        w=size["width"], h=size["height"]
    )
    return tree.output_dir / "full" / segment / "0" / "default.jpg"


class TestLevel0Consistency:
    def test_info_payload_properties(self, converted_tree: ConvertedTree):
        info = converted_tree.info
        if converted_tree.version is IIIFVersions._3_0:
            assert info["@context"] == "http://iiif.io/api/image/3/context.json"
            assert info["id"] == IDENTIFIER
            assert info["type"] == "ImageService3"
            assert info["profile"] == "level0"
            assert info["preferredFormats"] == ["jpg"]
            for forbidden in ("@id", "@type", "extraFormats"):
                assert forbidden not in info
        else:
            assert info["@context"] == "http://iiif.io/api/image/2/context.json"
            assert info["@id"] == IDENTIFIER
            assert info["@type"] == "iiif:Image"
            assert info["profile"] == "http://iiif.io/api/image/2/level0.json"
            for forbidden in ("id", "type", "preferredFormats", "extraFormats"):
                assert forbidden not in info
        assert info["protocol"] == "http://iiif.io/api/image"
        assert isinstance(info["width"], int)
        assert isinstance(info["height"], int)
        assert (info["width"], info["height"]) == (2676, 1572)
        for size in info["sizes"]:
            assert isinstance(size["width"], int)
            assert isinstance(size["height"], int)
        # Viewers derive the pyramid from the largest entry and assume it
        # descends by two to native resolution, so it has to start at 1.
        assert info["tiles"][0]["scaleFactors"][0] == 1

    def test_declared_size_files_exist(self, converted_tree: ConvertedTree):
        for size in converted_tree.info["sizes"]:
            path = size_path(converted_tree, size)
            assert path.exists(), f"missing declared size file {path}"

    def test_sizes_declared_dimensions_match_files(self, converted_tree: ConvertedTree):
        for size in converted_tree.info["sizes"]:
            path = size_path(converted_tree, size)
            assert path.exists(), f"missing declared size file {path}"
            assert pixel_dimensions(path) == (size["width"], size["height"])

    def test_full_size_file_exists_and_matches_dimensions(
        self, converted_tree: ConvertedTree
    ):
        info = converted_tree.info
        path = (
            converted_tree.output_dir
            / "full"
            / FULL_SIZE_SEGMENT[converted_tree.version]
            / "0"
            / "default.jpg"
        )
        assert path.exists(), f"missing full-size file {path}"
        assert pixel_dimensions(path) == (info["width"], info["height"])

    def test_tiles_exist_for_each_scale_factor(self, converted_tree: ConvertedTree):
        """Spot-check tiles against an independent reimplementation of the
        region-grid algorithm from the IIIF Image API implementation notes
        (https://iiif.io/api/image/3.0/implementation/): at each scale factor
        the image is stepped over in crop-sized regions, and every full-crop
        region must exist as a tile resized to the tile size.

        The coarsest level is one level where no full-crop region exists: its
        crop is larger than the image, so its regions are all edge regions. So
        is any level whose crop exceeds one of the image's sides. Those levels
        are checked region by region against the ceil rule instead of being
        skipped, which at the coarsest level means the single whole-image tile.
        """
        info = converted_tree.info
        width, height = info["width"], info["height"]
        for tile_entry in info["tiles"]:
            tile_size = tile_entry["width"]
            full_crop_segment = REGION_TILE_SEGMENT[converted_tree.version].format(
                tile=tile_size
            )
            for scale_factor in tile_entry["scaleFactors"]:
                crop = tile_size * scale_factor
                regions = [
                    (x, y, min(crop, width - x), min(crop, height - y))
                    for x in range(0, width, crop)
                    for y in range(0, height, crop)
                ]
                full_crop = [region for region in regions if region[2:] == (crop, crop)]
                if full_crop:
                    for x, y, w, h in full_crop:
                        path = (
                            converted_tree.output_dir
                            / f"{x},{y},{w},{h}"
                            / full_crop_segment
                            / "0"
                            / "default.jpg"
                        )
                        assert path.exists(), f"missing expected tile {path}"
                    continue
                # No region covers the crop exactly, so every tile of this level
                # is an edge region, addressed by its own scaled dimensions.
                assert regions, f"scale factor {scale_factor} produced no regions"
                for x, y, w, h in regions:
                    segment = CANONICAL_SIZE_SEGMENT[converted_tree.version].format(
                        w=math.ceil(w / scale_factor),
                        h=math.ceil(h / scale_factor),
                    )
                    path = (
                        converted_tree.output_dir
                        / f"{x},{y},{w},{h}"
                        / segment
                        / "0"
                        / "default.jpg"
                    )
                    assert path.exists(), f"missing expected tile {path}"

    def test_coarsest_level_region_tile_exists_and_measures_its_size(
        self, converted_tree: ConvertedTree
    ):
        """The spelling clients that do not canonicalize a whole-image region
        ask for: the entire image as one tile, addressed by region."""
        info = converted_tree.info
        width, height = info["width"], info["height"]
        scale_factor = max(info["tiles"][0]["scaleFactors"])
        expected = (math.ceil(width / scale_factor), math.ceil(height / scale_factor))
        segment = CANONICAL_SIZE_SEGMENT[converted_tree.version].format(
            w=expected[0], h=expected[1]
        )
        path = (
            converted_tree.output_dir
            / f"0,0,{width},{height}"
            / segment
            / "0"
            / "default.jpg"
        )
        assert path.exists(), f"missing whole-image region tile {path}"
        assert pixel_dimensions(path) == expected

    def test_coarsest_level_full_derivative_exists_and_measures_its_size(
        self, converted_tree: ConvertedTree
    ):
        """The spelling OpenSeadragon and OpenLayers ask for: the same
        derivative under the canonical `full` region."""
        info = converted_tree.info
        width, height = info["width"], info["height"]
        scale_factor = max(info["tiles"][0]["scaleFactors"])
        expected = (math.ceil(width / scale_factor), math.ceil(height / scale_factor))
        segment = CANONICAL_SIZE_SEGMENT[converted_tree.version].format(
            w=expected[0], h=expected[1]
        )
        path = converted_tree.output_dir / "full" / segment / "0" / "default.jpg"
        assert path.exists(), f"missing whole-image derivative {path}"
        assert pixel_dimensions(path) == expected

    def test_scale_factors_match_the_tier_derivation(
        self, converted_tree: ConvertedTree
    ):
        """The pyramid's top level is the level where the whole image fits one
        tile, derived here independently of the library's helper.

        A client that ignores ``scaleFactors`` counts tiers as
        ``2 ** max(ceil(log2(w/tile)), ceil(log2(h/tile)), 0)``; the library's
        top has to agree or that client asks for a level nobody wrote.
        """
        info = converted_tree.info
        width, height = info["width"], info["height"]
        tile_size = info["tiles"][0]["width"]

        def ceil_log2_of_tiles(side: int) -> int:
            """Whole powers of two: the smallest k with 2**k >= side / tile."""
            k = 0
            while 2**k * tile_size < side:
                k += 1
            return k

        expected_tier_zero = 2 ** max(
            ceil_log2_of_tiles(width), ceil_log2_of_tiles(height), 0
        )
        assert max(info["tiles"][0]["scaleFactors"]) == expected_tier_zero
