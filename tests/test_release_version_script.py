"""Tests for release version metadata maintenance."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path
import sys
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = REPO_ROOT / "rtl433_esphome_version.py"
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "update_release_version.py"


def load_release_version_script() -> ModuleType:
    """Load the release version helper as a Python module.

    Returns:
        The loaded release version helper module.
    """

    spec = importlib.util.spec_from_file_location("update_release_version", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _version_from_file(path: Path) -> str:
    """Extract the repository version string from a version module file."""

    match = re.search(r"(?m)^VERSION\s*=\s*['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(f"Could not parse VERSION from {path}")
    return match.group(1)


def test_update_release_version_updates_version_module(tmp_path: Path) -> None:
    """Release version updates should maintain the shared version module."""

    module = load_release_version_script()
    version_path = tmp_path / "rtl433_esphome_version.py"
    version_path.write_text(
        '"""Standalone repository version metadata."""\n\nVERSION = "v0.1.9"\n',
        encoding="utf-8",
    )

    changed = module.update_release_version(version_path, module.version_from_tag("v1.2.3"))

    assert changed
    assert _version_from_file(version_path) == "1.2.3"


def test_version_from_tag_normalizes_version() -> None:
    """Semver tags should be normalized to valid PEP 440 versions."""

    module = load_release_version_script()

    assert module.version_from_tag("v1.2.3") == "1.2.3"
    assert module.version_from_tag("v1.2.3-rc.1") == "1.2.3rc1"


def test_version_from_tag_rejects_build_metadata() -> None:
    """Build metadata should not generate invalid package versions."""

    module = load_release_version_script()

    with pytest.raises(ValueError, match="build metadata"):
        module.version_from_tag("v1.2.3+abc.1")


def test_update_release_version_reports_unchanged_version_module(tmp_path: Path) -> None:
    """Release version updates should be idempotent."""

    module = load_release_version_script()
    version_path = tmp_path / "rtl433_esphome_version.py"
    version_path.write_text(
        '"""Standalone repository version metadata."""\n\nVERSION = "1.2.3"\n',
        encoding="utf-8",
    )

    assert not module.update_release_version(version_path, module.version_from_tag("v1.2.3"))


def test_standalone_version_import_isolated() -> None:
    """Standalone version module should import with repo root only and no site packages."""

    code = """
import os
import sys

sys.path[:] = [os.environ["REPO_ROOT"]]
import rtl433_esphome_version

print(rtl433_esphome_version.VERSION)
"""
    env = os.environ.copy()
    env["REPO_ROOT"] = str(REPO_ROOT)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == _version_from_file(VERSION_PATH)
