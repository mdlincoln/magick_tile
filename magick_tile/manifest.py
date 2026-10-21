from typing import Literal, Optional, Type, ClassVar
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl

from magick_tile.settings import IIIFFormats, IIIFVersions


class TileScale(BaseModel):
    width: int
    scaleFactors: list[int]


class TileSize(BaseModel):
    width: Literal["max"] | int
    height: Literal["max"] | int


class IIIFManifest(BaseModel):
    """Shared model for all versions of the IIIF Image API Info payload"""

    id: str
    protocol: str = "http://iiif.io/api/image"
    width: int
    height: int
    sizes: Optional[list[TileSize]] = None
    tiles: Optional[list[TileScale]] = None
    preferredFormats: Optional[list[IIIFFormats]] = [IIIFFormats.jpg]
    maxWidth: Optional[int] = None
    maxHeight: Optional[int] = None
    maxArea: Optional[int] = None
    rights: Optional[str] = None

    def write_info_file(self, output_dir: Path) -> None:
        """Write json serialization to info.json at the specified output directory."""
        output_file = output_dir / "info.json"
        output_file.write_text(self.json(by_alias=True, exclude_none=True, indent=2))

    # TODO: sizes getter and setter
    # 2.1 uses "full" for height
    # 3.0 uses "max" for height


class IIIFManifest_2_1(IIIFManifest):
    context: str = Field(
        default="http://iiif.io/api/image/2/context.json", alias="@context"
    )
    id: HttpUrl = Field(..., alias="@id")
    type: Literal["iiif:Image"] = "iiif:Image"
    profile: Literal["http://iiif.io/api/image/2/level1.json"] = (
        "http://iiif.io/api/image/2/level1.json"
    )
    sizes: Optional[list]

    class Config:
        # "id" carries the "@id" alias for JSON output, but SourceImage.manifest
        # builds this model by field name, so accept both spellings.
        allow_population_by_field_name = True


class IIIFManifest_3_0(IIIFManifest):
    context: str = Field(
        default="http://iiif.io/api/image/3/context.json", alias="@context"
    )
    id: HttpUrl
    type: Literal["ImageService3"] = "ImageService3"
    profile: str = "level0"


def IIIFManifestSelector(
    version: IIIFVersions = IIIFVersions._3_0,
) -> Type[IIIFManifest_2_1] | Type[IIIFManifest_3_0]:
    """Return manifest class for given version"""
    if version is IIIFVersions._2_1:
        return IIIFManifest_2_1
    if version is IIIFVersions._3_0:
        return IIIFManifest_3_0
    raise NotImplementedError
