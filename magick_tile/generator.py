"""
This takes inspiration heavily from
https://github.com/zimeon/iiif/blob/master/iiif_static.py
"""

import logging
from typing import Optional
import re
import subprocess
from math import floor, ceil
from tempfile import mkdtemp
from pathlib import Path
from itertools import product

from pydantic import BaseModel, Field, HttpUrl
from rich.progress import track

from magick_tile.settings import (
    settings,
    IIIFFormats,
    IIIFFullSize,
    IIIFVersions,
)
from magick_tile.manifest import (
    LEVEL0_PROFILE_2_1,
    IIIFManifest,
    IIIFManifest_2_1,
    IIIFManifest_3_0,
    TileScale,
    TileSize,
)


class Dimensions(BaseModel):
    width: int
    height: int

    @property
    def smaller(self) -> int:
        return min(self.width, self.height)


class Tile(BaseModel):
    original_path: Path
    source_image: "SourceImage"

    # @cached_property
    @property
    def parsed_filename(self) -> list[int]:
        return [int(i) for i in self.original_path.stem.split(",")]

    @property
    def format(self) -> IIIFFormats:
        return IIIFFormats[self.original_path.suffix.lstrip(".")]

    @property
    def sf(self) -> int:
        return self.parsed_filename[1]

    @property
    def x(self) -> int:
        return self.parsed_filename[2]

    @property
    def y(self) -> int:
        return self.parsed_filename[3]

    @property
    def w(self) -> int:
        return self.parsed_filename[4]

    @property
    def h(self) -> int:
        return self.parsed_filename[5]

    @property
    def file_w(self) -> int:
        return (
            ceil(self.w / self.sf)
            if self.w < self.source_image.tile_size * self.sf
            else self.source_image.tile_size
        )

    @property
    def file_h(self) -> int:
        return (
            floor(self.h / self.sf)
            if self.h < self.source_image.tile_size * self.sf
            else self.source_image.tile_size
        )

    @property
    def target_dir(self) -> Path:
        return (
            self.source_image.target_dir
            / f"{self.x},{self.y},{self.w},{self.h}"
            / f"{self.file_w},/0"
        )

    @property
    def target_file(self) -> Path:
        return self.target_dir / f"default.{self.format.value}"

    def resize(self) -> None:
        """Call imagemagick to convert the cropped fullsized tiles to their
        scaled-down versions, writing it to the final target folder specified
        by the user."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        cmd: list[str | Path] = [
            "convert",
            self.original_path,
            "-resize",
            f"{self.file_w}x{self.file_h}",
            self.target_file,
        ]
        logging.debug(f"Resize command: {cmd}")
        subprocess.run(cmd, capture_output=True, check=True)


def tempdir_path() -> Path:
    """Method to return a temp directory Path that can be supplied for
    SourceImage's working_dir field default_factory"""
    return Path(mkdtemp())


# Image API 2.1 §4.2 writes the unscaled full image at the "full" size keyword;
# 3.0 §4.8 replaced that keyword with "max".
FULL_SIZE_BY_VERSION: dict[IIIFVersions, IIIFFullSize] = {
    IIIFVersions._2_1: IIIFFullSize._2,
    IIIFVersions._3_0: IIIFFullSize._3,
}


class DownsizedVersion(BaseModel):
    downsize_width: int
    source_image: "SourceImage"
    format: IIIFFormats = IIIFFormats.jpg

    @property
    def downsize_height(self) -> int:
        """Aspect-correct height for this downsized width, rounded half-up."""
        return self.source_image.downsized_height(self.downsize_width)

    @property
    def size_path_segment(self) -> str:
        """Size directory in the canonical form for the configured version.

        Image API 3.0 §4.8 gives canonical listed sizes as w,h, while 2.1 §5.2
        directs clients to request listed sizes as w,.
        """
        if self.source_image.version is IIIFVersions._2_1:
            return f"{self.downsize_width},"
        return f"{self.downsize_width},{self.downsize_height}"

    @property
    def target_directory(self) -> Path:
        return self.source_image.target_dir / "full" / self.size_path_segment / "0"

    @property
    def target_file(self) -> Path:
        return self.target_directory / f"default.{self.format.value}"

    def convert(self) -> None:
        self.target_directory.mkdir(parents=True, exist_ok=True)
        cmd: list[str | Path] = [
            "convert",
            self.source_image.path,
            "-geometry",
            # Force exact pixel dimensions so each written file matches the
            # w,h pair declared in info.json's sizes array.
            f"{self.downsize_width}x{self.downsize_height}!",
            self.target_file,
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            check=True,
        )


class SourceImage(BaseModel):
    id: HttpUrl
    path: Path
    tile_size: int
    target_dir: Path
    formats: list[IIIFFormats] = [IIIFFormats.jpg]
    max_area: Optional[int] = None
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    tiles: list[Tile] = []
    working_dir: Path = Field(default_factory=tempdir_path)
    version: IIIFVersions = IIIFVersions._3_0

    # @cached_property
    @property
    def dimensions(self) -> Dimensions:
        """
        Get the dimensions of the image according to imagemagick
        """
        subprocess_capture = subprocess.run(
            ["identify", "-ping", self.path], capture_output=True
        )
        identify_stdout = subprocess_capture.stdout.decode("utf-8")
        dims = re.search(r"(\d+)x(\d+)", identify_stdout)
        if dims is not None:
            groups = dims.groups()
            return Dimensions(width=int(groups[0]), height=int(groups[1]))
        else:
            raise Exception(
                "imagemagick's identify did not return the expected format "
                f"for {self.path}. Output: '{identify_stdout}'"
            )

    @property
    def format(self) -> IIIFFormats:
        return IIIFFormats[self.path.suffix.lstrip(".")]

    @property
    def minimum_dimension(self) -> int:
        return self.dimensions.smaller

    @property
    def downsizing_levels(self) -> list[int]:
        """
        Compute downsizing levels such that the width of the largest reduced
        image is smaller than the width of the original image
        """
        downsized_widths: list[int] = []
        current_factor: int = settings.MINIMUMUM_DOWNSIZE_EXP
        while (2**current_factor) < self.dimensions.width:
            downsized_widths.append(2**current_factor)
            current_factor += 1
        return downsized_widths

    @property
    def scaling_factors(self) -> list[int]:
        """
        Compute scaling factors such that the largest tile made is smaller
        than the shorter dimension of the input image
        """
        scaling_widths: list[int] = []
        current_scaling_factor = 1
        while (2**current_scaling_factor) < ceil(
            self.minimum_dimension / self.tile_size
        ):
            scaling_widths.append(2**current_scaling_factor)
            current_scaling_factor += 1
        return scaling_widths

    def downsized_height(self, downsize_width: int) -> int:
        """Aspect-correct height for a downsized width, rounded half up."""
        dims = self.dimensions
        return int(downsize_width * dims.height / dims.width + 0.5)

    def reject_size_constraints(self) -> None:
        """
        Fail fast when max_width/max_height/max_area are set: writing a
        constraint-correct full/max (or full/full) derivative is not
        implemented, and silently ignoring the limits would overstate the
        tree's capabilities in info.json.
        """
        constraints: dict[str, Optional[int]] = {
            "max_width": self.max_width,
            "max_height": self.max_height,
            "max_area": self.max_area,
        }
        active = [name for name, value in constraints.items() if value is not None]
        if active:
            raise NotImplementedError(
                "magick_tile cannot generate size-constrained IIIF trees: "
                + ", ".join(active)
                + " is set. Unset max_width/max_height/max_area, or pre-scale "
                "the source image before generating tiles."
            )

    def generate_tile_files(self) -> None:
        """Write multizised tile images"""
        for sf, img_format in track(
            product(self.scaling_factors, self.formats),
            description="Tiling image...",
            total=(len(self.scaling_factors) * len(self.formats)),
        ):
            cropsize: int = self.tile_size * sf
            cmd: list[str | Path] = [
                "convert",
                self.path,
                "-monitor",
                "-crop",
                f"{cropsize}x{cropsize}",
                # Rely on imagemagick to tell us the resulting dimensions for
                # the tiles it makes, which is especially useful on the
                # non-square tiles from the right and bottom edges of images.
                "-set",
                "filename:tile",
                "%[fx:page.x],%[fx:page.y],%[fx:w],%[fx:h]",
                "+repage",
                "+adjoin",
                self.working_dir / f"{cropsize},{sf},%[filename:tile].{img_format}",
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            # Imagemagick will create many files from this single command.
            # Collect the filenames and parse them so that we have the
            # necessary info for the final step of the conversion.
            generated_paths = self.working_dir.glob(f"*.{img_format}")
            for gp in generated_paths:
                self.tiles.append(Tile(original_path=gp, source_image=self))

    def resize_tile_files(self) -> None:
        for t in track(self.tiles, description="Sizing and sorting tiles..."):
            t.resize()

    def generate_reduced_versions(self) -> None:
        """
        Create smaller derivatives of the full image.
        """
        for ds, img_format in track(
            product(self.downsizing_levels, self.formats),
            total=(len(self.downsizing_levels) * len(self.formats)),
            description="Reduced sizes...",
        ):
            DownsizedVersion(
                downsize_width=ds, source_image=self, format=img_format
            ).convert()

    def generate_full_size(self) -> None:
        """
        Write the unscaled full image at the canonical URI for the configured
        API version: full/max/0/ for 3.0, full/full/0/ for 2.1.
        """
        self.reject_size_constraints()
        full_size_dir = (
            self.target_dir / "full" / FULL_SIZE_BY_VERSION[self.version].value / "0"
        )
        full_size_dir.mkdir(parents=True, exist_ok=True)
        dims = self.dimensions
        for img_format in self.formats:
            cmd: list[str | Path] = [
                "convert",
                self.path,
                "-geometry",
                # Unconstrained full images are identity resizes; forcing
                # exact dimensions guarantees the written file matches
                # info.json's width and height.
                f"{dims.width}x{dims.height}!",
                full_size_dir / f"default.{img_format.value}",
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, check=True)

    @property
    def manifest(self) -> IIIFManifest:
        """Return the info payload shaped for the configured API version."""
        dims = self.dimensions
        sizes = [
            TileSize(width=ds, height=self.downsized_height(ds))
            for ds in self.downsizing_levels
        ]
        tiles = [TileScale(width=self.tile_size, scaleFactors=self.scaling_factors)]
        if self.version is IIIFVersions._2_1:
            extra_formats = [f.value for f in self.formats if f is not IIIFFormats.jpg]
            if extra_formats:
                # 2.1 §5.2: declare formats beyond the level0-required jpg in
                # a profile description object appended to the level URI.
                return IIIFManifest_2_1(
                    id=self.id,
                    sizes=sizes,
                    tiles=tiles,
                    profile=[
                        LEVEL0_PROFILE_2_1,
                        {"formats": extra_formats},
                    ],
                    width=dims.width,
                    height=dims.height,
                    maxWidth=self.max_width,
                    maxHeight=self.max_height,
                    maxArea=self.max_area,
                )
            return IIIFManifest_2_1(
                id=self.id,
                sizes=sizes,
                tiles=tiles,
                width=dims.width,
                height=dims.height,
                maxWidth=self.max_width,
                maxHeight=self.max_height,
                maxArea=self.max_area,
            )
        return IIIFManifest_3_0(
            id=self.id,
            sizes=sizes,
            tiles=tiles,
            preferredFormats=self.formats,
            # 3.0 §5.5: extraFormats lists formats beyond the level0-required
            # jpg, while preferredFormats lists everything the tree serves.
            extraFormats=[f for f in self.formats if f is not IIIFFormats.jpg] or None,
            width=dims.width,
            height=dims.height,
            maxWidth=self.max_width,
            maxHeight=self.max_height,
            maxArea=self.max_area,
        )

    def write_info(self) -> None:
        """
        Write the info.json for this image

        TODO: add ability to list arbitrary endpoint features re
        https://iiif.io/api/image/2.1/#profile-description
        """
        self.manifest.write_info_file(self.target_dir)

    def convert(self) -> None:
        """
        Five-stage generation:

        1. Use convert's -crop function to write tilesets at each of the
        scaling factors appropriate for the image (e.g. tiles at 256, 512,
        1024 px on a side, etc.) Stores intermediate files to a temporary
        directory
        """
        # Fail fast on unimplemented size constraints before any subprocess
        # runs, so a rejected run cannot leave a partial output tree behind.
        self.reject_size_constraints()
        self.generate_tile_files()
        """
        2. Use convert's -resize function to reduce the cropped tiles to the
        specified tile size. These resized tiles are saved to the specified
        output directory with the right nested directory structure expected
        of IIIF tiles.
        """
        self.resize_tile_files()
        """
        3. Generate downsized whole-image versions.
        """
        self.generate_reduced_versions()
        """
        4. Write the unscaled full image at the version's canonical full URI.
        """
        self.generate_full_size()
        """
        5. Write the IIIF image information JSON file
        """
        self.write_info()


Tile.update_forward_refs()
DownsizedVersion.update_forward_refs()
