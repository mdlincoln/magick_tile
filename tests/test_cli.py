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
    assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()
    assert (test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg").exists()


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
    assert (test_output_dir / "full" / "1024," / "0" / "default.jpg").exists()
    assert (test_output_dir / "full" / "1024," / "0" / "default.png").exists()
    assert (test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.jpg").exists()
    assert (test_output_dir / "0,0,1024,1024" / "512," / "0" / "default.png").exists()


def test_invalid_file(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_output_dir), str(test_output_dir), example_id],
    )
    assert "Invalid value for 'SOURCE'" in result.stdout
    assert result.exit_code == 2


def test_invalid_output(test_jpg: Path, test_output_dir: Path, example_id: str):
    result = runner.invoke(
        app,
        [str(test_jpg), str(test_jpg), example_id],
    )
    assert "Invalid value for 'OUTPUT'" in result.stdout
    assert result.exit_code == 2
