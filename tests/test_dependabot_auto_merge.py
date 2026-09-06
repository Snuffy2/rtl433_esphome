"""Behavioral tests for the trusted Dependabot authorization helper."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZER = REPO_ROOT / ".github" / "scripts" / "dependabot-auto-merge.mjs"
HEAD_SHA = "1" * 40
BASE_SHA = "2" * 40


def _event(branch: str) -> dict[str, object]:
    """Create a verified direct-Dependabot pull request event.

    Args:
        branch: Dependabot branch under authorization.

    Returns:
        The minimal event payload the helper consumes.
    """

    return {
        "action": "opened",
        "repository": {
            "default_branch": "main",
            "fork": False,
            "full_name": "Snuffy2/rtl433_esphome",
        },
        "pull_request": {
            "base": {"ref": "main", "sha": BASE_SHA},
            "head": {
                "ref": branch,
                "repo": {"full_name": "Snuffy2/rtl433_esphome"},
                "sha": HEAD_SHA,
            },
            "user": {"login": "dependabot[bot]"},
        },
    }


def _dependabot_commit() -> dict[str, object]:
    """Create the verified direct commit required by the authorization contract.

    Returns:
        A GitHub commit API response with Dependabot provenance.
    """

    return {
        "author": {"login": "dependabot[bot]"},
        "commit": {"verification": {"verified": True}},
        "parents": [],
        "sha": HEAD_SHA,
    }


def _authorize(
    tmp_path: Path,
    branch: str,
    changed_files: list[str],
    *,
    action: str = "opened",
    actor: str = "dependabot[bot]",
    commits: list[dict[str, object]] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the helper against a direct Dependabot update.

    Args:
        tmp_path: Temporary directory for API-like input files.
        branch: Dependabot branch to authorize.
        changed_files: Pull-request files reported by GitHub.
        action: Pull-request action that caused authorization.
        actor: GitHub actor that caused authorization.
        commits: Commit API responses in oldest-to-newest order.

    Returns:
        The authorization process result.
    """

    event_path = tmp_path / "event.json"
    files_path = tmp_path / "changed-files"
    commits_path = tmp_path / "commits.json"
    event = _event(branch)
    event["action"] = action
    event_path.write_text(json.dumps(event), encoding="utf-8")
    files_path.write_text("\n".join(changed_files), encoding="utf-8")
    commits_path.write_text(json.dumps([commits or [_dependabot_commit()]]), encoding="utf-8")
    environment = {**os.environ, "GITHUB_ACTOR": actor}
    return subprocess.run(
        ["node", str(AUTHORIZER), str(event_path), str(files_path), str(commits_path)],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
    )


def test_authorizes_a_verified_uv_lockfile_update(tmp_path: Path) -> None:
    """A verified uv update may change only the lockfile."""

    result = _authorize(tmp_path, "dependabot/uv/pytest-9.0.0", ["uv.lock"])

    assert result.returncode == 0, result.stderr


def test_rejects_uv_update_that_changes_project_metadata(tmp_path: Path) -> None:
    """A uv update containing project metadata must not receive auto-merge authority."""

    result = _authorize(
        tmp_path,
        "dependabot/uv/pytest-9.0.0",
        ["pyproject.toml", "uv.lock"],
    )

    assert result.returncode != 0


def test_authorizes_an_existing_top_level_actions_workflow(tmp_path: Path) -> None:
    """Actions updates may target an existing workflow trusted from the base checkout."""

    result = _authorize(
        tmp_path,
        "dependabot/github_actions/actions/checkout-7",
        [".github/workflows/validation.yml"],
    )

    assert result.returncode == 0, result.stderr


def test_rejects_an_actions_manifest_absent_from_the_trusted_base(tmp_path: Path) -> None:
    """Actions updates cannot introduce a new root action manifest."""

    result = _authorize(
        tmp_path,
        "dependabot/github_actions/actions/checkout-7",
        ["action.yml"],
    )

    assert result.returncode != 0


def test_authorizes_a_verified_github_update_branch_merge(tmp_path: Path) -> None:
    """A GitHub Update branch merge must preserve verified Dependabot history."""

    dependabot_sha = "3" * 40
    dependabot_commit = _dependabot_commit()
    dependabot_commit["sha"] = dependabot_sha
    update_commit = {
        "author": {"login": "Snuffy2"},
        "commit": {"verification": {"verified": True}},
        "committer": {"login": "web-flow"},
        "parents": [{"sha": dependabot_sha}, {"sha": BASE_SHA}],
        "sha": HEAD_SHA,
    }

    result = _authorize(
        tmp_path,
        "dependabot/uv/pytest-9.0.0",
        ["uv.lock"],
        action="synchronize",
        actor="Snuffy2",
        commits=[dependabot_commit, update_commit],
    )

    assert result.returncode == 0, result.stderr
