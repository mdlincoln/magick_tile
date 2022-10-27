import pytest
from pytest_subprocess import FakeProcess


@pytest.fixture
def fake_convert():
    with FakeProcess.context() as nested_process:
        nested_process.register(["convert"])
        yield


class TestImagemagick:
    def test_missing_im(self):
        with pytest.raises(Exception) as ex:
            import magick_tile

    def test_has_im(self, fake_convert):
        import magick_tile

        assert True
