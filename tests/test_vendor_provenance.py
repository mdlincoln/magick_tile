"""Every vendored viewer bundle matches the digest recorded beside it.

The browser suite stays offline because those third-party bytes are committed,
and a swapped, truncated or locally edited file would otherwise surface only as
a mysterious client failure. Hashing needs neither Playwright nor any ``e2e``
import, so this check belongs in the default unit run.
"""

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VENDOR_READMES = sorted(REPO_ROOT.glob("e2e/viewer/*/vendor/README.md"))
DIGEST_BLOCK = re.compile(r"<!-- sha256:begin -->(.*?)<!-- sha256:end -->", re.DOTALL)


def recorded_digests(readme: Path) -> dict[str, str]:
    """The ``path<TAB>sha256`` lines of a vendor README's checksum block."""
    match = DIGEST_BLOCK.search(readme.read_text())
    assert match, f"{readme.relative_to(REPO_ROOT)} has no sha256 block"
    digests: dict[str, str] = {}
    for line in match.group(1).splitlines():
        entry = line.strip()
        if not entry:
            continue
        name, separator, digest = entry.partition("\t")
        assert separator and digest, (
            f"{readme.relative_to(REPO_ROOT)} has a malformed checksum line: {entry!r}"
        )
        digests[name] = digest
    return digests


def test_vendored_files_match_recorded_checksums() -> None:
    assert VENDOR_READMES, "no vendored viewer bundles were found"
    problems: list[str] = []
    for readme in VENDOR_READMES:
        vendor_dir = readme.parent
        digests = recorded_digests(readme)
        assert digests, f"{readme.relative_to(REPO_ROOT)} records no checksums"

        for name, digest in sorted(digests.items()):
            path = vendor_dir / name
            if not path.is_file():
                problems.append(
                    f"{path.relative_to(REPO_ROOT)} is recorded but missing"
                )
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != digest:
                problems.append(
                    f"{path.relative_to(REPO_ROOT)} has sha256 {actual}, "
                    f"recorded {digest}"
                )

        # A vendored file nobody recorded is just as unverified as a mismatch.
        for path in sorted(vendor_dir.iterdir()):
            if path.is_dir() or path.name == readme.name:
                continue
            if path.name not in digests:
                problems.append(
                    f"{path.relative_to(REPO_ROOT)} is vendored but not recorded"
                )

    assert not problems, "\n".join(problems)
