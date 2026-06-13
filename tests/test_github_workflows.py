"""Tests for GitHub workflow safety and event coverage."""

from pathlib import Path
import re

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PRIVILEGED_WORKFLOWS = [
    WORKFLOW_DIR / "labeler.yml",
    WORKFLOW_DIR / "merge_conflict_labeler.yml",
]
PINNED_ACTION_REF = re.compile(r"uses:\s+[^@\s]+/[^\s@]+@[0-9a-f]{40}$")


def test_pull_request_target_workflows_pin_third_party_actions() -> None:
    """Privileged pull_request_target workflows should use immutable action refs."""
    for workflow_path in PRIVILEGED_WORKFLOWS:
        workflow_text = workflow_path.read_text()
        assert "pull_request_target:" in workflow_text
        uses_lines = [
            line.strip() for line in workflow_text.splitlines() if line.strip().startswith("uses:")
        ]

        assert uses_lines
        assert all(PINNED_ACTION_REF.fullmatch(line) for line in uses_lines)


def test_merge_conflict_labeler_runs_for_initial_pr_states() -> None:
    """Merge conflict labeling should run when PRs are opened or reopened."""
    workflow_text = (WORKFLOW_DIR / "merge_conflict_labeler.yml").read_text()

    assert "types: [opened, reopened, synchronize]" in workflow_text
