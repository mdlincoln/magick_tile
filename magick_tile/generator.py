"""
This takes inspiration heavily from
https://github.com/zimeon/iiif/blob/master/iiif_static.py
"""

import logging
from typing import Optional
import re
import subprocess
from math import ceil
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
            # Rounds up like file_w: a scaled edge height is usually fractional,
            # and clients compute the requested height as ceil(h / sf).
            ceil(self.h / self.sf)
            if self.h < self.source_image.tile_size * self.sf
            else self.source_image.tile_size
        )

    @property
    def size_path_segment(self) -> str:
        """Size directory in the canonical form for the configured version.

        Image API 3.0 §4.8 gives canonical tile sizes as w,h; 2.1 §5.2 uses w,.
        Clients build the request from these forms, so a mismatch means the
        file on disk is never asked for.
        """
        return SIZE_SEGMENT_BY_VERSION[self.source_image.version].format(
            w=self.file_w, h=self.file_h
        )

    @property
    def target_dir(self) -> Path:
        return (
            self.source_image.target_dir
            / f"{self.x},{self.y},{self.w},{self.h}"
            / self.size_path_segment
            / "0"
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
            # Force the exact dimensions the size directory declares. Plain
            # -resize preserves the source aspect ratio, which for an edge tile
            # can land a pixel away from ceil(w / sf) by ceil(h / sf).
            f"{self.file_w}x{self.file_h}!",
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

# Canonical size-directory form for the configured version, holding a width as
# {w} and a height as {h}. Image API 3.0 §4.8 addresses a size as w,h; 2.1 §5.2
# addresses it as w,. The library needs this mapping for region tiles, for the
# declared sizes and for the coarsest level's whole-image derivative, so it
# lives here once rather than inline at each of those uses.
SIZE_SEGMENT_BY_VERSION: dict[IIIFVersions, str] = {
    IIIFVersions._3_0: "{w},{h}",
    IIIFVersions._2_1: "{w},",
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
        return SIZE_SEGMENT_BY_VERSION[self.source_image.version].format(
            w=self.downsize_width, h=self.downsize_height
        )

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


def scaling_factors_for(width: int, height: int, tile_size: int) -> list[int]:
    """Powers of two from 1 up to the level that fits the whole image in one tile.

    The top level is derived from the longer side, so `2 ** M * tile_size` is
    the first level at or above `max(width, height)`. Integer arithmetic only:
    a `log2` would let the result drift from `2 ** M` through float rounding,
    and the boundary case (`top * tile_size == max(width, height)` exactly) is a
    real one — a 4096 px side at tile 512 must stop at 8, not 16.
    """
    top = 1
    while top * tile_size < max(width, height):
        top *= 2
    return [1 << exponent for exponent in range(top.bit_length())]


def whole_image_size(width: int, height: int, tile_size: int) -> tuple[int, int]:
    """Pixel size of the coarsest level's single tile.

    Both dimensions round up, matching how a client computes the size of a
    whole-image region at that scale factor. Note this is not the aspect-correct
    half-up rule `downsized_height_for` applies: for 3202x4096 at scale 8 the
    client asks for 512, while half-up would give 513.
    """
    top = max(scaling_factors_for(width, height, tile_size))
    return ceil(width / top), ceil(height / top)


def downsized_widths_for(width: int) -> list[int]:
    """Declared `sizes` widths for an image of this width.

    Every width is a power of two below the image's own width, so the largest
    reduced image is always smaller than the original.
    """
    downsized_widths: list[int] = []
    current_factor: int = settings.MINIMUMUM_DOWNSIZE_EXP
    while (2**current_factor) < width:
        downsized_widths.append(2**current_factor)
        current_factor += 1
    return downsized_widths


def downsized_height_for(width: int, height: int, downsize_width: int) -> int:
    """Aspect-correct height for one declared width, rounded half up."""
    return int(downsize_width * height / width + 0.5)


def declared_size_segments(
    version: IIIFVersions, width: int, height: int, downsize_widths: list[int]
) -> set[str]:
    """Size directories the declared `sizes` pass writes, in this version's form."""
    form = SIZE_SEGMENT_BY_VERSION[version]
    return {
        form.format(w=ds, h=downsized_height_for(width, height, ds))
        for ds in downsize_widths
    }


def whole_image_segment(
    width: int, height: int, tile_size: int, version: IIIFVersions
) -> str:
    """Size directory for the coarsest level's whole-image derivative."""
    w, h = whole_image_size(width, height, tile_size)
    return SIZE_SEGMENT_BY_VERSION[version].format(w=w, h=h)


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
    def downsizing_levels(self) -> list[int]:
        """
        Compute downsizing levels such that the width of the largest reduced
        image is smaller than the width of the original image
        """
        return downsized_widths_for(self.dimensions.width)

    @property
    def scaling_factors(self) -> list[int]:
        """
        Compute scaling factors such that the coarsest level is the level where
        the whole image fits in a single tile.

        That top level is sized from the longer side: at `2 ** M` the whole
        image fits one tile, which is the tier-0 scale of clients that count
        tiers from the image dimensions and the tile size instead of reading
        `scaleFactors`. Sizing from the shorter side instead stops one level
        short of it, so those clients ask for a level that was never written.

        The list starts at 1 and ascends by powers of two. Viewers derive the
        whole pyramid from its largest entry and assume it descends by two down
        to native resolution, so a pyramid that starts at 2 leaves them
        requesting tiles that were never written.
        """
        dims = self.dimensions
        return scaling_factors_for(dims.width, dims.height, self.tile_size)

    @property
    def whole_image_level_size(self) -> tuple[int, int]:
        """Pixel size of the coarsest level's single whole-image tile."""
        dims = self.dimensions
        return whole_image_size(dims.width, dims.height, self.tile_size)

    def downsized_height(self, downsize_width: int) -> int:
        """Aspect-correct height for a downsized width, rounded half up."""
        dims = self.dimensions
        return downsized_height_for(dims.width, dims.height, downsize_width)

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
            # necessary info for the final step of the conversion. The glob is
            # scoped to this crop size: an unscoped match would pick up every
            # earlier level's tiles too and resize them again.
            generated_paths = self.working_dir.glob(f"{cropsize},{sf},*.{img_format}")
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

    def generate_whole_image_level(self) -> None:
        """
        Write the coarsest level's whole-image derivative.

        Once the pyramid's top level is the level where the whole image fits in
        one tile, every client requests that level as a whole-image region. They
        do not agree on how to spell it. OpenSeadragon and OpenLayers rewrite a
        whole-image tile region to the canonical `full` region and send the size
        only (`full/{w},{h}/0/`), while leaflet-iiif sends the explicit region
        of the tile it would have loaded (`0,0,{W},{H}/{w},{h}/0/`). A dynamic
        IIIF server redirects the explicit region to `full`, because that is the
        canonical form for the whole image in both API versions; a static tree
        cannot redirect, so it writes both paths. The tile pipeline already
        writes the region spelling, so this method writes the `full` one.

        A skip covers the one case where those two spellings collide with a
        declared size. 2.1's size segment is width-only, so for 4096x3011 at
        tile 512 the level's segment is `512,` and the declared size 512's
        segment is `512,` too — one directory, two heights: the level is 512x377
        and the thumbnail is 512x376. Overwriting the thumbnail would break the
        declared dimensions, so the declared file stays as it is: the URL still
        resolves, and a width-only segment makes no height promise to the client.
        3.0's segment carries the height, so a collision there means the declared
        file already has the level's dimensions and skipping only avoids writing
        the same file twice.

        The disagreement a skip leaves in a 2.1 tree is small by construction: a
        colliding coarsest width is at most one tile, while the declared widths
        are the powers of two from 256 upwards, and the two rules round the same
        aspect ratio differently — by a pixel or two, in either direction.

        This assumes the declared sizes were written, as `convert()` does before
        calling it; called standalone on a colliding shape it writes nothing. An
        image at or below one tile is written like any other, which duplicates
        `full/max` (or `full/full`) at small sizes: one duplicate file buys
        uniform behaviour and keeps the small-image path exercised.
        """
        self.reject_size_constraints()
        dims = self.dimensions
        whole_width, whole_height = whole_image_size(
            dims.width, dims.height, self.tile_size
        )
        segment = whole_image_segment(
            dims.width, dims.height, self.tile_size, self.version
        )
        if segment in declared_size_segments(
            self.version, dims.width, dims.height, self.downsizing_levels
        ):
            return
        target_directory = self.target_dir / "full" / segment / "0"
        target_directory.mkdir(parents=True, exist_ok=True)
        for img_format in self.formats:
            cmd: list[str | Path] = [
                "convert",
                self.path,
                "-geometry",
                # Force exact pixel dimensions so the file matches the size
                # directory that addresses it, as the declared sizes do.
                f"{whole_width}x{whole_height}!",
                target_directory / f"default.{img_format.value}",
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
            # Construct from field names: the 2.1 payload serializes @id,
            # @context and @type through output aliases, and model_validate
            # accepts field names via populate_by_name. ty cannot model
            # pydantic's alias rules for keyword construction.
            payload: dict[str, object] = {
                "id": self.id,
                "sizes": sizes,
                "tiles": tiles,
                "width": dims.width,
                "height": dims.height,
                "maxWidth": self.max_width,
                "maxHeight": self.max_height,
                "maxArea": self.max_area,
            }
            extra_formats = [f.value for f in self.formats if f is not IIIFFormats.jpg]
            if extra_formats:
                # 2.1 §5.2: declare formats beyond the level0-required jpg in
                # a profile description object appended to the level URI.
                payload["profile"] = [
                    LEVEL0_PROFILE_2_1,
                    {"formats": extra_formats},
                ]
            return IIIFManifest_2_1.model_validate(payload)
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
        Six-stage generation:

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
        5. Write the coarsest level's whole-image derivative at its `full` URI,
        the spelling the clients that canonicalize a whole-image region send.
        """
        self.generate_whole_image_level()
        """
        6. Write the IIIF image information JSON file
        """
        self.write_info()


Tile.model_rebuild()
DownsizedVersion.model_rebuild()
