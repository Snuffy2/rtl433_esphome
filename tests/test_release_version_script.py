"""Tests for release version metadata maintenance."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "update_release_version.py"


def load_release_version_script() -> ModuleType:
    """Load the release version helper as a Python module.

    Returns:
        The loaded release version helper module.

    Raises:
        RuntimeError: If the helper module cannot be loaded from disk.
    """

    spec = importlib.util.spec_from_file_location("update_release_version", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _version_from_file(path: Path) -> str:
    """Extract the repository version string from a version module file.

    Args:
        path: The path to a Python file containing a VERSION constant.

    Returns:
        The parsed repository version string.

    Raises:
        AssertionError: If the VERSION constant is missing.
    """

    match = re.search(r"(?m)^VERSION\s*=\s*['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(f"Could not parse VERSION from {path}")
    return match.group(1)


@pytest.mark.parametrize(
    ("start_version", "new_version", "expected_changed"),
    [
        ("v0.1.9", "v1.2.3", True),
        ("v1.2.3", "v1.2.3", False),
    ],
)
def test_update_release_version_updates_or_reports_unchanged_version_module(
    tmp_path: Path,
    start_version: str,
    new_version: str,
    expected_changed: bool,
) -> None:
    """Release updates should apply changes or remain idempotent."""

    module = load_release_version_script()
    version_path = tmp_path / "rtl433_esphome_version.py"
    version_path.write_text(
        f'"""Standalone repository version metadata."""\n\nVERSION = "{start_version}"\n',
        encoding="utf-8",
    )

    assert module.update_release_version(version_path, new_version) is expected_changed
    assert _version_from_file(version_path) == new_version


def test_update_release_version_errors_if_version_assignment_missing(tmp_path: Path) -> None:
    """Missing VERSION assignments should surface a clear ValueError."""

    module = load_release_version_script()
    version_path = tmp_path / "rtl433_esphome_version.py"
    version_path.write_text('"""No version here."""\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Could not find VERSION assignment"):
        module.update_release_version(version_path, "v1.2.3")


def test_version_from_tag_rejects_non_semver_release_tag() -> None:
    """Reject release tags that are not semantic versions."""

    module = load_release_version_script()

    with pytest.raises(ValueError, match="Release tag is not semver"):
        module.version_from_tag("latest")
