"""Update release-managed project metadata from a release tag."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

PEP440_PRERELEASE_ALIASES = {
    "a": "a",
    "alpha": "a",
    "b": "b",
    "beta": "b",
    "rc": "rc",
    "pre": "rc",
}

SEMVER_TAG_PATTERN = re.compile(
    r"^v?"
    r"(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*)"
    r")?"
    r"(?:\+(?P<build_metadata>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)"
    r")?$"
)
VERSION_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<prefix>^VERSION\s*=\s*)"
    r"(?P<quote>['\"])(?P<version>[^'\"]+)(?P=quote)",
    re.MULTILINE,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed command line arguments.
    """

    parser = argparse.ArgumentParser(
        description="Update release-managed project metadata from a semver release tag."
    )
    parser.add_argument("tag", help="Semver release tag, with optional v prefix.")
    parser.add_argument(
        "--version-file",
        type=Path,
        default=Path("rtl433_esphome_version.py"),
        help="Path to the shared version module.",
    )
    return parser.parse_args()


def version_from_tag(tag: str) -> str:
    """Return a package-safe project version string from a release tag.

    Args:
        tag: Release tag to validate and use as the version.

    Returns:
        The normalized release tag in PEP 440 format.

    Raises:
        ValueError: If the tag is not a semver tag with an optional v prefix
            or contains unsupported build metadata.
    """

    match = SEMVER_TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError(f"Release tag is not semver with optional v prefix: {tag}")
    if match.group("build_metadata") is not None:
        raise ValueError(f"Release tag build metadata is not supported: {tag}")

    normalized_prerelease = _normalize_prerelease(match.group("prerelease"))
    return (
        f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}"
        f"{normalized_prerelease}"
    )


def _normalize_prerelease(prerelease: str | None) -> str:
    """Convert a semver prerelease token to a PEP 440-compatible suffix."""

    if prerelease is None:
        return ""

    parts = prerelease.split(".")
    if len(parts) > 2:
        raise ValueError(f"Release tag prerelease format is not supported: {prerelease}")

    if len(parts) == 1 and parts[0].isdigit():
        return f".dev{int(parts[0])}"

    label = parts[0].replace("-", "")
    number = None
    if len(parts) == 2:
        if not parts[1].isdigit():
            raise ValueError(f"Release tag prerelease format is not supported: {prerelease}")
        number = parts[1]
    else:
        match = re.fullmatch(r"([A-Za-z-]+)(\d+)", parts[0])
        if match is not None:
            label = match.group(1)
            number = match.group(2)

    label_normalized = PEP440_PRERELEASE_ALIASES.get(label.lower())
    if label_normalized is None:
        raise ValueError(f"Release prerelease label is not supported: {prerelease}")

    if number is None:
        number = "0"

    return f"{label_normalized}{int(number)}"


def update_release_version(version_path: Path, version: str) -> bool:
    """Update release-managed project metadata.

    Args:
        version_path: Path to the shared version module.
        version: Version string to write.

    Returns:
        True when a file changed, otherwise False.

    Raises:
        ValueError: If the VERSION assignment cannot be found.
    """

    content = version_path.read_text(encoding="utf-8")
    match = VERSION_ASSIGNMENT_PATTERN.search(content)
    if match is None:
        raise ValueError(f"Could not find VERSION assignment in {version_path}")
    if match.group("version") == version:
        return False

    updated = VERSION_ASSIGNMENT_PATTERN.sub(
        rf"\g<prefix>{match.group('quote')}{version}{match.group('quote')}",
        content,
        count=1,
    )
    version_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    """Run the release version updater."""

    args = parse_args()
    try:
        version = version_from_tag(args.tag)
        changed = update_release_version(args.version_file, version)
    except ValueError as err:
        raise SystemExit(str(err)) from err
    if changed:
        print(f"Updated release metadata to {version}")
    else:
        print(f"Release metadata is already {version}")


if __name__ == "__main__":
    main()
