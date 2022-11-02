from typing import Literal, Optional
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class TileScale(BaseModel):
    width: int
    scaleFactors: list[int]


class TileSize(BaseModel):
    width: Literal["full"] | int
    height: Literal["full"] | int


class IIIFManifest(BaseModel):
    context: str = Field(
        default="http://iiif.io/api/image/3/context.json", alias="@context"
    )
    id: HttpUrl
    type: Literal["ImageService3"] = "ImageService3"
    protocol: str = "http://iiif.io/api/image"
    profile: str = "level0"
    width: int
    height: int
    preferredFormats: Optional[list[str]] = ["jpg"]
    sizes: Optional[list[TileSize]] = None
    tiles: Optional[list[TileScale]] = None
    maxWidth: Optional[int] = None
    maxHeight: Optional[int] = None
    maxArea: Optional[int] = None
    rights: Optional[str] = None

    def write_info_file(self, output_dir: Path) -> None:
        """Write json serialization to info.json at the specified output directory."""
        output_file = output_dir / "info.json"
        output_file.write_text(self.json(by_alias=True, exclude_none=True, indent=2))
