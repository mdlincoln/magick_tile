from enum import Enum

from pydantic import BaseSettings


class IIIFFormats(str, Enum):
    jpg = "jpg"
    tif = "tif"
    png = "png"
    gif = "gif"
    jp2 = "jp2"
    pdf = "pdf"
    webp = "webp"


class IIIFVersions(str, Enum):
    _3_0 = "3.0"
    # _2_1 = "2.1" Not yet implemented


class IIIFFullSize(str, Enum):
    _2 = "max"
    _3 = "max"


class Settings(BaseSettings):
    MINIMUMUM_DOWNSIZE_EXP: int = 8


settings = Settings()
