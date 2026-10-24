"""Build-artifact checks: the e2e fixture and the vendored viewer bundles must
never ship inside the published distributions.

The harness's own sources are ordinary test code and stay in the sdist; what
must not ship is the 2.7 MB fixture image, the third-party bundles vendored
under ``e2e/viewer/<backend>/vendor/`` for OpenSeadragon, OpenLayers and
Leaflet, and generated directories such as out/ or htmlcov/."""

import fnmatch
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from e2e.requests import IMAGE_SUFFIXES as E2E_IMAGE_SUFFIXES

REPO_ROOT = Path(__file__).parent.parent
# The browser harness's own list, so a format it treats as an image cannot slip
# into a distribution through a narrower set of extensions here.
IMAGE_SUFFIXES = set(E2E_IMAGE_SUFFIXES) | {".tif", ".tiff"}
# sdist members are prefixed with the distribution directory, so the vendor rule
# is matched as a glob with a leading wildcard: one directory per backend.
FORBIDDEN_PATTERNS = ["*/e2e/viewer/*/vendor/*"]
FORBIDDEN_FRAGMENTS = ["e2e/fixtures", "self-portrait", "htmlcov/", "/out/"]

requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv is required to build distributions"
)
requires_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is required to inspect tracked files"
)


@pytest.fixture(scope="session")
def dist_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return out_dir


def wheel_members(dist_dir: Path) -> list[str]:
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {wheels}"
    with zipfile.ZipFile(wheels[0]) as archive:
        return archive.namelist()


def sdist_members(dist_dir: Path) -> list[str]:
    sdists = list(dist_dir.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, found {sdists}"
    with tarfile.open(sdists[0]) as archive:
        return archive.getnames()


@requires_uv
def test_wheel_contains_only_package(dist_dir: Path) -> None:
    members = wheel_members(dist_dir)
    assert members, "the wheel is empty"
    stray = [
        member
        for member in members
        if not (member.startswith("magick_tile/") or ".dist-info/" in member)
    ]
    assert not stray, f"wheel contains files outside the package: {stray}"
    images = [
        member for member in members if Path(member).suffix.lower() in IMAGE_SUFFIXES
    ]
    assert not images, f"wheel contains image assets: {images}"


@requires_uv
def test_sdist_excludes_e2e_assets(dist_dir: Path) -> None:
    members = sdist_members(dist_dir)
    assert members, "the sdist is empty"
    found = [
        member
        for member in members
        if any(fragment in member for fragment in FORBIDDEN_FRAGMENTS)
        or any(fnmatch.fnmatch(member, pattern) for pattern in FORBIDDEN_PATTERNS)
    ]
    assert not found, f"sdist contains harness or generated assets: {found}"


@requires_git
def test_fixture_is_tracked() -> None:
    """The .gitignore negation has to survive the global *.jpg rule, and the
    fixture has to live in one place."""
    tracked = subprocess.run(
        ["git", "ls-files", "e2e/fixtures"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "self-portrait_1937.1.72.jpg" in tracked, (
        "the e2e fixture is not tracked by git"
    )
    assert not (REPO_ROOT / "self-portrait_1937.1.72.jpg").exists(), (
        "a copy of the fixture is still at the repository root"
    )
