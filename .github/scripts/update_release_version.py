"""Update release-managed project metadata from a release tag."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

RELEASE_TAG_PATTERN = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?(?:\.(0|[1-9][0-9]*))?"
    r"(?:-(?:0|[1-9][0-9]*|[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
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
        description="Update release-managed project metadata from a supported release tag."
    )
    parser.add_argument(
        "tag", help="Two-, three-, or four-part release tag, with optional v prefix."
    )
    parser.add_argument(
        "--version-file",
        type=Path,
        default=Path("rtl433_esphome_version.py"),
        help="Path to the shared version module.",
    )
    return parser.parse_args()


def version_from_tag(tag: str) -> str:
    """Return a project version string from a supported release tag.

    Args:
        tag: Release tag to validate and use as the version.

    Returns:
        The unchanged release tag.

    Raises:
        ValueError: If the tag has an unsupported two-, three-, or four-part
            release version with an optional v prefix.
    """

    if RELEASE_TAG_PATTERN.fullmatch(tag) is None:
        raise ValueError(
            "Release tag must use a two-, three-, or four-part version with an optional v prefix: "
            f"{tag}"
        )
    return tag


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

    try:
        content = version_path.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError(f"Could not read version file: {version_path}") from err
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
    try:
        version_path.write_text(updated, encoding="utf-8")
    except OSError as err:
        raise ValueError(f"Could not write version file: {version_path}") from err
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
