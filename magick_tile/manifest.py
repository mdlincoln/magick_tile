from typing import Final, Literal, Optional
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl

from magick_tile.settings import IIIFFormats


class TileScale(BaseModel):
    width: int
    scaleFactors: list[int]


class TileSize(BaseModel):
    width: int
    height: int


class IIIFManifest(BaseModel):
    """Shared model for all versions of the IIIF Image API Info payload"""

    id: HttpUrl
    protocol: str = "http://iiif.io/api/image"
    width: int
    height: int
    sizes: Optional[list[TileSize]] = None
    tiles: Optional[list[TileScale]] = None
    # preferredFormats is an Image API 3.0 property (§5.5); 2.1 payloads must
    # not carry it. The 3.0 construction always passes it explicitly, so the
    # None default only ensures 2.1 serialization drops the key entirely
    # under exclude_none=True.
    preferredFormats: Optional[list[IIIFFormats]] = None
    maxWidth: Optional[int] = None
    maxHeight: Optional[int] = None
    maxArea: Optional[int] = None
    rights: Optional[str] = None

    def write_info_file(self, output_dir: Path) -> None:
        """Write json serialization to info.json at the specified output directory."""
        output_file = output_dir / "info.json"
        output_file.write_text(self.json(by_alias=True, exclude_none=True, indent=2))


LEVEL0_PROFILE_2_1: Final = "http://iiif.io/api/image/2/level0.json"


class IIIFManifest_2_1(IIIFManifest):
    context: str = Field(
        default="http://iiif.io/api/image/2/context.json", alias="@context"
    )
    id: HttpUrl = Field(..., alias="@id")
    # 2.1 §5.2 names this property "@type" (and makes it optional); emitting
    # the alias keeps 2.1 payloads free of 3.0's unqualified "type" key.
    type: Literal["iiif:Image"] = Field(default="iiif:Image", alias="@type")
    # Either the bare level0 URI, or the list form [level0, {"formats": [...]}]
    # used to declare formats beyond the level0-required jpg (2.1 §5.2).
    profile: Literal["http://iiif.io/api/image/2/level0.json"] | list = (
        LEVEL0_PROFILE_2_1
    )

    class Config:
        # "id"/"type" carry the "@id"/"@type" aliases for JSON output, but
        # SourceImage.manifest builds this model by field name, so accept both
        # spellings.
        allow_population_by_field_name = True


class IIIFManifest_3_0(IIIFManifest):
    context: str = Field(
        default="http://iiif.io/api/image/3/context.json", alias="@context"
    )
    type: Literal["ImageService3"] = "ImageService3"
    profile: str = "level0"
    extraFormats: Optional[list[IIIFFormats]] = None
