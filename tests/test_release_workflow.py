"""Tests for the release workflow."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _release_workflow_steps() -> list[dict[str, Any]]:
    """Load the release workflow steps.

    Returns:
        The release job workflow steps.
    """

    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["release"]["steps"]
    if not isinstance(steps, list):
        raise AssertionError("Release workflow steps should be a list")
    return steps


def _release_workflow_step(name: str) -> dict[str, Any]:
    """Find a named release workflow step.

    Args:
        name: The workflow step name.

    Returns:
        The matching release workflow step.
    """

    for step in _release_workflow_steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"Missing release workflow step: {name}")


def test_release_workflow_cache_key_tracks_version_source() -> None:
    """Release workflow cache key should include the version source file."""

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert (
        "${{ runner.os }}-release-esphome-pio-${{ github.event.release.tag_name }}-${{ "
        "hashFiles('pyproject.toml', 'rtl433-esphome-heltec-lora-32-v2.yaml', "
        "'components/rtl433_native/__init__.py', 'rtl433_esphome_version.py') }}"
    ) in workflow_text


def test_release_workflow_skips_version_commit_and_retag_for_prerelease() -> None:
    """Prereleases should not publish version commits or retarget release tags."""

    prerelease_guard = "${{ !github.event.release.prerelease }}"
    guarded_steps = [
        "Commit and push version changes",
        "Update release tag with version changes commit",
    ]

    for step_name in guarded_steps:
        assert _release_workflow_step(step_name).get("if") == prerelease_guard
