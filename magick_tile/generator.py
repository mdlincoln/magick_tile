"""
This takes inspiration heavily from https://github.com/zimeon/iiif/blob/master/iiif_static.py
"""

import logging
from typing import Optional
import re
import subprocess
from math import floor, ceil
from tempfile import mkdtemp
from pathlib import Path

from functools import cached_property
from pydantic import BaseModel, Field, HttpUrl
from rich.progress import track

from magick_tile.settings import settings
from magick_tile.manifest import IIIFManifest, TileSize, TileScale


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
        return self.target_dir / "default.jpg"

    def resize(self) -> None:
        """Call imagemagick to convert the cropped fullsized tiles to their scaled-down versions, writing it to the final target folder specified by the user."""
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
    """Method to return a temp directory Path that can be supplied for SourceImage's working_dir field default_factory"""
    return Path(mkdtemp())


class DownsizedVersion(BaseModel):
    downsize_width: int
    source_image: "SourceImage"

    @property
    def target_directory(self) -> Path:
        return self.source_image.target_dir / "full" / f"{self.downsize_width}," / "0"

    @property
    def target_file(self) -> Path:
        return self.target_directory / "default.jpg"

    def convert(self) -> None:
        self.target_directory.mkdir(parents=True, exist_ok=True)
        cmd: list[str | Path] = [
            "convert",
            self.source_image.path,
            "-geometry",
            f"{self.downsize_width}x",
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
    max_area: Optional[int] = None
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    tiles: list[Tile] = []
    working_dir: Path = Field(default_factory=tempdir_path)

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
                f"imagemagick's identify did not return the expected format for {self.path}. Output: '{identify_stdout}'"
            )

    @property
    def minimum_dimension(self) -> int:
        return self.dimensions.smaller

    @property
    def downsizing_levels(self) -> list[int]:
        """
        Compute downsizing levels such that the width of the largest reduced image is smaller than the width of the original image
        """
        return [s for s in settings.BASE_SMALLER_SIZES if s < self.dimensions.width]

    @property
    def scaling_factors(self) -> list[int]:
        """
        Compute scaling factors such that the largest tile made is smaller than the shorter dimension of the input image
        """
        return [
            sf
            for sf in settings.BASE_SCALING_FACTORS
            if sf < ceil(self.minimum_dimension / self.tile_size)
        ]

    def generate_tile_files(self) -> None:
        """Write multizised tile images"""
        for sf in track(self.scaling_factors, description="Tiling image..."):
            cropsize: int = self.tile_size * sf
            cmd: list[str | Path] = [
                "convert",
                self.path,
                "-monitor",
                "-crop",
                f"{cropsize}x{cropsize}",
                "-set",
                "filename:tile",
                "%[fx:page.x],%[fx:page.y],%[fx:w],%[fx:h]",  # rely on Imagemagick to tell us the resulting dimensions for the tiles it makes, which is especially useful on the non-square tiles from the right and bottom edges of images
                "+repage",
                "+adjoin",
                self.working_dir / f"{cropsize},{sf},%[filename:tile].jpg",
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            # Imagemagick will create many files from this single command. Collect the filenames and parse them so that we have the necessary info for the ifnal step of the conversion.
            generated_paths = self.working_dir.glob("*.jpg")
            for gp in generated_paths:
                self.tiles.append(Tile(original_path=gp, source_image=self))

    def resize_tile_files(self) -> None:
        for t in track(self.tiles, description="Sizing and sorting tiles..."):
            t.resize()

    def generate_reduced_versions(self):
        """
        Create smaller derivatives of the full image.
        """
        for ds in self.downsizing_levels:
            DownsizedVersion(downsize_width=ds, source_image=self).convert()

    # @cached_property
    @property
    def manifest(self) -> IIIFManifest:
        """Return manifest"""
        return IIIFManifest(
            id=self.id,
            sizes=[TileSize(width=ds, height="full") for ds in self.downsizing_levels],
            tiles=[TileScale(width=self.tile_size, scaleFactors=self.scaling_factors)],
            width=self.dimensions.width,
            height=self.dimensions.height,
            maxWidth=self.max_width,
            maxHeight=self.max_height,
            maxArea=self.max_area,
        )

    def write_info(self) -> None:
        """
        Write the info.json for this image

        TODO: add ability to list arbitrary endpoint features re https://iiif.io/api/image/2.1/#profile-description
        """
        self.manifest.write_info_file(self.target_dir)

    def convert(self) -> None:
        """
        Four-stage generation:

        1. Use convert's -crop function to write tilesets at each of the scaling factors appropriate for the image (e.g. tiles at 256, 512, 1024 px on a side, etc.) Stores intermediate files to a temporary directory
        """
        self.generate_tile_files()
        """
        2. Use convert's -resize function to reduce the cropped tiles to the specified tile size. These resized tiles are saved to the specified output directory with the right nested directory structure expected of IIIF tiles.
        """
        self.resize_tile_files()
        """
        3. Generate downsized whole-image versions.
        """
        self.generate_reduced_versions()
        """
        4. Write the IIIF image information JSON file
        """
        self.write_info()


Tile.update_forward_refs()
DownsizedVersion.update_forward_refs()
