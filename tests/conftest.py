import pytest
from tempfile import TemporaryDirectory
from pathlib import Path


@pytest.fixture
def test_output_dir():
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_working_dir():
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_jpg() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "complete-usable-accurate.jpg"
    assert p.exists()
    return p


@pytest.fixture()
def test_png() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "complete-usable-accurate.png"
    assert p.exists()
    return p


@pytest.fixture
def tile_jpg() -> Path:
    p = Path(__file__).parent.absolute() / "assets" / "256,2,0,0,512,512.jpg"
    assert p.exists()
    return p


@pytest.fixture()
def example_id() -> str:
    return "https://example.com/images/foobar"
