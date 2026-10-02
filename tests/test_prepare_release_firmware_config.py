"""Tests for the local release firmware profile."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCRIPT = REPO_ROOT / ".github" / "scripts" / "prepare_release_firmware_config.py"


def load_script(path: Path, name: str) -> ModuleType:
    """Load a repository helper without putting its directory on sys.path.

    Args:
        path: Helper module path.
        name: Isolated module name.

    Returns:
        Imported helper module.
    """

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_release_profile_selects_checked_out_components(tmp_path: Path) -> None:
    """The release build profile must use local candidate sources, not a moving tag."""

    config = load_script(CONFIG_SCRIPT, "prepare_release_firmware_config")
    components = tmp_path / "components"
    components.mkdir()
    destination = tmp_path / "release.yaml"

    config.prepare_config(
        REPO_ROOT / "rtl433-esphome-heltec-lora-32-v2.yaml",
        destination,
        components,
    )

    output = destination.read_text(encoding="utf-8")
    assert "type: local" in output
    assert f"path: {components.resolve()}" in output
    assert "type: git" not in output
