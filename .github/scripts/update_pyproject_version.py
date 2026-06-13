"""Update the project version in pyproject.toml from a release tag."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

SEMVER_TAG_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
PROJECT_SECTION_PATTERN = re.compile(
    r"(?P<prefix>^\[project\]\n(?:(?!^\[).)*?^version\s*=\s*)"
    r"(?P<quote>['\"])(?P<version>[^'\"]+)(?P=quote)",
    re.MULTILINE | re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed command line arguments.
    """

    parser = argparse.ArgumentParser(
        description="Update [project].version in pyproject.toml from a semver release tag."
    )
    parser.add_argument("tag", help="Semver release tag, with optional v prefix.")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml.",
    )
    return parser.parse_args()


def version_from_tag(tag: str) -> str:
    """Return a pyproject version string from a semver release tag.

    Args:
        tag: Release tag to validate and use as the version.

    Returns:
        The unchanged release tag.

    Raises:
        ValueError: If the tag is not a semver tag with an optional v prefix.
    """

    if SEMVER_TAG_PATTERN.fullmatch(tag) is None:
        raise ValueError(f"Release tag is not semver with optional v prefix: {tag}")
    return tag


def update_pyproject_version(pyproject_path: Path, version: str) -> bool:
    """Update the project version in pyproject.toml.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        version: Version string to write.

    Returns:
        True when the file changed, otherwise False.

    Raises:
        ValueError: If the project version field cannot be found.
    """

    content = pyproject_path.read_text(encoding="utf-8")
    match = PROJECT_SECTION_PATTERN.search(content)
    if match is None:
        raise ValueError(f"Could not find [project].version in {pyproject_path}")
    if match.group("version") == version:
        return False

    updated = PROJECT_SECTION_PATTERN.sub(
        rf"\g<prefix>{match.group('quote')}{version}{match.group('quote')}",
        content,
        count=1,
    )
    pyproject_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    """Run the pyproject version updater."""

    args = parse_args()
    try:
        version = version_from_tag(args.tag)
        changed = update_pyproject_version(args.pyproject, version)
    except ValueError as err:
        raise SystemExit(str(err)) from err
    if changed:
        print(f"Updated {args.pyproject} project version to {version}")
    else:
        print(f"{args.pyproject} project version is already {version}")


if __name__ == "__main__":
    main()
