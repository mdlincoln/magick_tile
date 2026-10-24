import json
from pathlib import Path

from typer.testing import CliRunner

from magick_tile.main import app

runner = CliRunner()


def test_app(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_jpg), str(test_output_dir), example_id],
    )
    print(result.stdout)
    assert result.exit_code == 0
    assert (test_output_dir / "info.json").exists()
    assert (test_output_dir / "full" / "1024,602" / "0" / "default.jpg").exists()
    assert (test_output_dir / "full" / "max" / "0" / "default.jpg").exists()
    assert (
        test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.jpg"
    ).exists()
    # Scale factor 1 is generated, so the native-resolution tile exists too.
    assert (test_output_dir / "0,0,512,512" / "512,512" / "0" / "default.jpg").exists()


def test_app_2_1(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_jpg), str(test_output_dir), example_id, "--version", "2.1"],
    )
    print(result.stdout)
    assert result.exit_code == 0
    info = json.loads((test_output_dir / "info.json").read_text())
    assert info["@id"] == example_id
    assert info["profile"] == "http://iiif.io/api/image/2/level0.json"
    assert (test_output_dir / "full" / "full" / "0" / "default.jpg").exists()
    assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()
    # 2.1 keeps the w, size form for region tiles.
    assert (test_output_dir / "0,0,512,512" / "512," / "0" / "default.jpg").exists()


def test_multi_output(test_png: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [
            str(test_png),
            str(test_output_dir),
            example_id,
            "--format",
            "jpg",
            "--format",
            "png",
        ],
    )
    print(result.stdout)
    assert result.exit_code == 0
    assert (test_output_dir / "info.json").exists()
    assert (test_output_dir / "full" / "1024,602" / "0" / "default.jpg").exists()
    assert (test_output_dir / "full" / "1024,602" / "0" / "default.png").exists()
    assert (
        test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.jpg"
    ).exists()
    assert (
        test_output_dir / "0,0,1024,1024" / "512,512" / "0" / "default.png"
    ).exists()


def test_invalid_file(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_output_dir), str(test_output_dir), example_id],
    )
    # typer 0.27 renders usage errors on stderr, with the lowercase parameter
    # name.
    assert "Invalid value for 'source'" in result.stderr
    assert result.exit_code == 2


def test_invalid_output(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_jpg), str(test_jpg), example_id],
    )
    assert "Invalid value for 'output'" in result.stderr
    assert result.exit_code == 2
