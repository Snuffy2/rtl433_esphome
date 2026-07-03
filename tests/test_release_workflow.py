"""Tests for the release workflow."""

import re
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


def test_release_workflow_commits_and_retags_prereleases() -> None:
    """Prereleases should still move the release tag and commit version updates."""

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    commit_step = re.search(
        r"name:\s+Commit and push version changes.*?name:\s+Update release tag with version changes",
        workflow_text,
        re.DOTALL,
    )
    tag_step = re.search(
        r"name:\s+Update release tag with version changes.*?name:\s+Install dependencies",
        workflow_text,
        re.DOTALL,
    )
    assert commit_step is not None
    assert tag_step is not None
    assert "${{ !github.event.release.prerelease }}" not in commit_step.group(0)
    assert "${{ !github.event.release.prerelease }}" not in tag_step.group(0)


def test_release_workflow_only_updates_latest_for_non_prerelease() -> None:
    """Latest tag updates should be restricted to stable releases."""

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "  - name: Update latest tag" in workflow_text
    assert "${{ !github.event.release.prerelease }}" in workflow_text
    assert (
        re.search(
            r"name:\s+Update latest tag[\s\S]*?if:\s+\${{ !github\.event\.release\.prerelease }}",
            workflow_text,
        )
        is not None
    )
