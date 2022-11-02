from enum import Enum

from pydantic import BaseSettings


def power2(start: int, end: int) -> list[int]:
    return [2**pow for pow in range(start, end)]


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
    BASE_SCALING_FACTORS: list[int] = power2(1, 9)
    BASE_SMALLER_SIZES: list[int] = power2(8, 16)


settings = Settings()
