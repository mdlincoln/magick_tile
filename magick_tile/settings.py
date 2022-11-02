from pydantic import BaseSettings


def power2(start: int, end: int) -> list[int]:
    return [2**pow for pow in range(start, end)]


class Settings(BaseSettings):
    BASE_SCALING_FACTORS: list[int] = power2(1, 9)
    BASE_SMALLER_SIZES: list[int] = power2(8, 16)


settings = Settings()
