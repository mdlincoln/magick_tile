"""Package metadata checks. The repository targets Python 3.10, so
pyproject.toml is parsed as plain text rather than with the 3.11+ stdlib
tomllib, and no new parsing dependency is added."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"


def test_package_version() -> None:
    text = PYPROJECT.read_text()
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    assert match is not None, "pyproject.toml must declare a version string"
    assert match.group(1) == "0.2.0"


def test_readme_markers() -> None:
    """README must document the IIIF-version-specific output contract."""
    text = README.read_text()
    assert "--version" in text
    assert "full/max" in text
    assert "full/full" in text
    # Region tiles are documented at the w, size form (a documented deviation
    # from 3.0's canonical w,h).
    assert "`w,`" in text
