"""Tests for GitHub workflow safety and event coverage."""

from pathlib import Path
import re

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PRIVILEGED_WORKFLOWS = [
    WORKFLOW_DIR / "labeler.yml",
    WORKFLOW_DIR / "merge_conflict_labeler.yml",
]
IMMUTABLE_ACTION_REF = re.compile(r"uses:\s+[^@\s]+/[^\s@]+@[0-9a-f]{40}$")
MAJOR_VERSION_ACTION_REF = re.compile(r"uses:\s+[^@\s]+/[^\s@]+@v[0-9]+$")


def test_pull_request_target_workflows_use_approved_action_refs() -> None:
    """Privileged pull_request_target workflows should use approved action refs."""
    for workflow_path in PRIVILEGED_WORKFLOWS:
        workflow_text = workflow_path.read_text()
        assert "pull_request_target:" in workflow_text
        uses_lines = [
            line.strip() for line in workflow_text.splitlines() if line.strip().startswith("uses:")
        ]

        assert uses_lines
        assert all(
            IMMUTABLE_ACTION_REF.fullmatch(line) or MAJOR_VERSION_ACTION_REF.fullmatch(line)
            for line in uses_lines
        )


def test_merge_conflict_labeler_runs_for_initial_pr_states() -> None:
    """Merge conflict labeling should run when PRs are opened or reopened."""
    workflow_text = (WORKFLOW_DIR / "merge_conflict_labeler.yml").read_text()

    assert "types:" in workflow_text
    assert "- opened" in workflow_text
    assert "- reopened" in workflow_text
    assert "- synchronize" in workflow_text


def test_no_workflow_publishes_personal_firmware_release_assets() -> None:
    """Personal local-device YAML should not be published as release firmware."""
    assert not (WORKFLOW_DIR / "build.yml").exists()
    for workflow_path in WORKFLOW_DIR.glob("*.yml"):
        workflow_text = workflow_path.read_text()
        assert "softprops/action-gh-release" not in workflow_text
        assert "package-firmware" not in workflow_text


def test_validation_workflow_runs_lint_and_tests_without_publishing_firmware() -> None:
    """CI should validate code without producing personal firmware artifacts."""
    workflow_text = (WORKFLOW_DIR / "validation.yml").read_text()

    assert "pull_request:" in workflow_text
    assert "push:" in workflow_text
    assert "uv sync --dev" in workflow_text
    assert "./scripts/lint" in workflow_text
    assert "./.venv/bin/pytest" in workflow_text
    assert "esphome compile" not in workflow_text
    assert "upload-artifact" not in workflow_text
