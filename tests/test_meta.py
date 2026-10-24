"""Package metadata checks. The repository targets Python 3.10, so
pyproject.toml is parsed as plain text rather than with the 3.11+ stdlib
tomllib, and no new parsing dependency is added."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


def test_package_version() -> None:
    text = PYPROJECT.read_text()
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    assert match is not None, "pyproject.toml must declare a version string"
    assert match.group(1) == "0.4.0"


def test_readme_markers() -> None:
    """README must document how to operate the tool, and point at the changelog
    for the output contract's history."""
    text = README.read_text()
    assert "--version" in text
    assert "CHANGELOG.md" in text


def test_changelog_documents_the_version_specific_contract() -> None:
    """The version-specific output contract lives in CHANGELOG.md: both canonical
    size-directory forms and both full-size keywords are named there, because
    the README describes a 3.0 tree only."""
    text = CHANGELOG.read_text()
    for marker in ("full/max", "full/full", "`w,`", "`w,h`"):
        assert marker in text, f"CHANGELOG.md must document {marker}"
