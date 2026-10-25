from enum import StrEnum

from pydantic_settings import BaseSettings


class IIIFFormats(StrEnum):
    jpg = "jpg"
    tif = "tif"
    png = "png"
    gif = "gif"
    jp2 = "jp2"
    pdf = "pdf"
    webp = "webp"


class IIIFVersions(StrEnum):
    _3_0 = "3.0"
    _2_1 = "2.1"


class IIIFFullSize(StrEnum):
    # 2.1 §4.2 names the unscaled full image "full"; 3.0 §4.8 replaced that
    # size keyword with "max".
    _2 = "full"
    _3 = "max"


class Settings(BaseSettings):
    MINIMUMUM_DOWNSIZE_EXP: int = 8


settings = Settings()
