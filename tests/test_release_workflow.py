"""Tests for the release workflow."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_cache_key_tracks_version_source() -> None:
    """Release workflow cache key should include the version source file."""

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert (
        "${{ runner.os }}-release-esphome-pio-${{ github.event.release.tag_name }}-${{ "
        "hashFiles('pyproject.toml', 'rtl433-esphome-heltec-lora-32-v2.yaml', "
        "'components/rtl433_native/__init__.py', 'rtl433_esphome_version.py') }}"
    ) in workflow_text
