"""Tests for release version metadata maintenance."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_update_release_version_updates_version_module(tmp_path: Path) -> None:
    """Release version updates should maintain the shared version module."""

    module = load_release_version_script()
    version_path = tmp_path / "components" / "rtl433_native" / "version.py"
    version_path.parent.mkdir(parents=True)
    version_path.write_text(
        '"""Shared project version metadata."""\n\nVERSION = "v0.1.9"\n',
        encoding="utf-8",
    )

    changed = module.update_release_version(version_path, "v1.2.3")

    assert changed
    assert version_path.read_text(encoding="utf-8") == (
        '"""Shared project version metadata."""\n\nVERSION = "v1.2.3"\n'
    )


def test_update_release_version_reports_unchanged_version_module(tmp_path: Path) -> None:
    """Release version updates should be idempotent."""

    module = load_release_version_script()
    version_path = tmp_path / "components" / "rtl433_native" / "version.py"
    version_path.parent.mkdir(parents=True)
    version_path.write_text(
        '"""Shared project version metadata."""\n\nVERSION = "v1.2.3"\n',
        encoding="utf-8",
    )

    assert not module.update_release_version(version_path, "v1.2.3")
