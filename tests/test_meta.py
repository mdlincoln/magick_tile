"""Package metadata checks. pyproject.toml is read with the stdlib tomllib, so
the checks inspect declared metadata rather than matching on file text."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


def test_package_version() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["version"] == "0.5.0"


def test_readme_markers() -> None:
    """README must document how to operate the tool, and point at the changelog
    for the output contract's history."""
    text = README.read_text(encoding="utf-8")
    assert "--version" in text
    assert "CHANGELOG.md" in text


def test_changelog_documents_the_version_specific_contract() -> None:
    """The version-specific output contract lives in CHANGELOG.md: both canonical
    size-directory forms and both full-size keywords are named there, because
    the README describes a 3.0 tree only."""
    text = CHANGELOG.read_text(encoding="utf-8")
    for marker in ("full/max", "full/full", "`w,`", "`w,h`"):
        assert marker in text, f"CHANGELOG.md must document {marker}"
