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


def _event(branch: str, action: str) -> dict[str, object]:
    """Create a Dependabot pull-request event for the supplied branch and action.

    Args:
        branch: Dependabot branch under authorization.
        action: Pull-request event action.

    Returns:
        The minimal event payload consumed by the helper.
    """

    return {
        "action": action,
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


def _dependabot_commit(sha: str = HEAD_SHA) -> dict[str, object]:
    """Create a verified Dependabot commit API response.

    Args:
        sha: Commit object identifier.

    Returns:
        A direct Dependabot commit response.
    """

    return {
        "author": {"login": "dependabot[bot]"},
        "commit": {"verification": {"verified": True}},
        "parents": [],
        "sha": sha,
    }


def _write_trusted_base(tmp_path: Path, files: tuple[str, ...]) -> Path:
    """Create a trusted-base fixture with exactly the supplied regular files.

    Args:
        tmp_path: Temporary directory allocated to the test.
        files: Repository-relative fixture paths to create.

    Returns:
        The trusted-base fixture directory.
    """

    trusted_base = tmp_path / "trusted-base"
    for path in files:
        fixture = trusted_base / path
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text("fixture\n", encoding="utf-8")
    return trusted_base


def _write_runner(tmp_path: Path) -> Path:
    """Create an ESM runner that calls the helper's public authorization API.

    Args:
        tmp_path: Temporary directory allocated to the test.

    Returns:
        The executable ESM runner path.
    """

    runner = tmp_path / "run-authorizer.mjs"
    runner.write_text(
        "\n".join(
            (
                f"import {{ authorizeDependabotUpdate }} from {AUTHORIZER.as_uri()!r};",
                'import { readFileSync } from "node:fs";',
                "const [eventPath, filesPath, commitsPath, trustedBaseDirectory] = process.argv.slice(2);",
                'const event = JSON.parse(readFileSync(eventPath, "utf8"));',
                'const changedFiles = readFileSync(filesPath, "utf8").split("\\n").filter(Boolean);',
                'const commits = JSON.parse(readFileSync(commitsPath, "utf8")).flat();',
                "try {",
                "  authorizeDependabotUpdate({",
                "    actor: process.env.GITHUB_ACTOR,",
                "    changedFiles,",
                "    commits,",
                "    event,",
                "    trustedBaseDirectory,",
                "  });",
                "} catch (error) {",
                "  console.error(error.message);",
                "  process.exitCode = 1;",
                "}",
            ),
        ),
        encoding="utf-8",
    )
    return runner


def _authorize(
    tmp_path: Path,
    branch: str,
    changed_files: list[str],
    trusted_base_files: tuple[str, ...],
    *,
    actor: str = "dependabot[bot]",
    commits: list[dict[str, object]] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the helper against an isolated trusted base and API-like inputs.

    Args:
        tmp_path: Temporary directory allocated to the test.
        branch: Dependabot branch under authorization.
        changed_files: Pull-request files reported by GitHub.
        trusted_base_files: Regular files present in the trusted base fixture.
        actor: GitHub actor that caused authorization.
        commits: Commit API responses in oldest-to-newest order.

    Returns:
        The authorization process result.
    """

    action = "opened" if actor == "dependabot[bot]" else "synchronize"
    event_path = tmp_path / "event.json"
    files_path = tmp_path / "changed-files"
    commits_path = tmp_path / "commits.json"
    event_path.write_text(json.dumps(_event(branch, action)), encoding="utf-8")
    files_path.write_text("\n".join(changed_files), encoding="utf-8")
    commits_path.write_text(json.dumps([commits or [_dependabot_commit()]]), encoding="utf-8")
    environment = {**os.environ, "GITHUB_ACTOR": actor}
    return subprocess.run(
        [
            "node",
            str(_write_runner(tmp_path)),
            str(event_path),
            str(files_path),
            str(commits_path),
            str(_write_trusted_base(tmp_path, trusted_base_files)),
        ],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
    )


def test_authorizes_uv_lockfile_update_from_uv_trusted_base(tmp_path: Path) -> None:
    """A verified uv update is authorized when its trusted base has uv.lock."""

    result = _authorize(
        tmp_path,
        "dependabot/uv/pytest-9.0.0",
        ["uv.lock"],
        ("uv.lock",),
    )

    assert result.returncode == 0, result.stderr


def test_rejects_npm_update_from_uv_only_trusted_base(tmp_path: Path) -> None:
    """An npm update is refused when its trusted base does not use npm."""

    result = _authorize(
        tmp_path,
        "dependabot/npm_and_yarn/vitest-4.1.11",
        ["package-lock.json"],
        ("uv.lock",),
    )

    assert result.returncode != 0


def test_authorizes_existing_trusted_actions_files(tmp_path: Path) -> None:
    """Actions updates may modify an existing top-level workflow or nested action."""

    for changed_file in (".github/workflows/validation.yml", "actions/release/action.yaml"):
        result = _authorize(
            tmp_path,
            "dependabot/github_actions/actions/checkout-7",
            [changed_file],
            (".github/workflows/validation.yml", "actions/release/action.yaml"),
        )

        assert result.returncode == 0, result.stderr


def test_rejects_invalid_update_branch_history(tmp_path: Path) -> None:
    """A non-web-flow commit cannot be smuggled into an Update branch chain."""

    dependabot_sha = "3" * 40
    invalid_update = {
        "author": {"login": "Snuffy2"},
        "commit": {"verification": {"verified": True}},
        "committer": {"login": "Snuffy2"},
        "parents": [{"sha": dependabot_sha}, {"sha": BASE_SHA}],
        "sha": HEAD_SHA,
    }
    result = _authorize(
        tmp_path,
        "dependabot/uv/pytest-9.0.0",
        ["uv.lock"],
        ("uv.lock",),
        actor="Snuffy2",
        commits=[_dependabot_commit(dependabot_sha), invalid_update],
    )

    assert result.returncode != 0
