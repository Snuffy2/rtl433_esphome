"""Behavioral and workflow-contract tests for Dependabot authorization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZER = REPO_ROOT / ".github" / "scripts" / "dependabot-auto-merge.mjs"
AUTO_MERGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml"
VALIDATION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validation.yml"
HEAD_SHA = "1" * 40
BASE_SHA = "2" * 40
DEPENDABOT_SHA = "3" * 40
INTERMEDIATE_SHA = "4" * 40
INTERMEDIATE_BASE_SHA = "5" * 40


def _event(branch: str, action: str = "reopened") -> dict[str, object]:
    """Create a valid minimal Dependabot pull-request event.

    Args:
        branch: Dependabot branch under authorization.
        action: Pull-request event action.

    Returns:
        The event payload consumed by the helper.
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


def _dependabot_commit(sha: str = HEAD_SHA, verified: bool = True) -> dict[str, object]:
    """Create a Dependabot commit response.

    Args:
        sha: Commit object identifier.
        verified: Whether GitHub reports a verified commit signature.

    Returns:
        The API-like commit response.
    """

    return {
        "author": {"login": "dependabot[bot]"},
        "commit": {"verification": {"verified": verified}},
        "parents": [],
        "sha": sha,
    }


def _update_commit(sha: str, previous: str, base: str) -> dict[str, object]:
    """Create a verified GitHub Update branch merge response.

    Args:
        sha: Merge commit identifier.
        previous: Trusted first-parent commit identifier.
        base: Base branch second-parent identifier.

    Returns:
        The API-like web-flow merge response.
    """

    return {
        "author": {"login": "Snuffy2"},
        "commit": {"verification": {"verified": True}},
        "committer": {"login": "web-flow"},
        "parents": [{"sha": previous}, {"sha": base}],
        "sha": sha,
    }


def _proof(parent: str, status: str = "ahead") -> dict[str, object]:
    """Create compare API ancestry evidence.

    Args:
        parent: Merge commit second-parent identifier.
        status: GitHub compare relationship.

    Returns:
        The minimized evidence checked by the helper.
    """

    return {
        "ahead_by": 0 if status == "identical" else 1,
        "base_commit": parent,
        "base_sha": BASE_SHA,
        "behind_by": 0,
        "head_commit": BASE_SHA,
        "merge_base_commit": parent,
        "parent_sha": parent,
        "status": status,
    }


def _update_chain() -> list[dict[str, object]]:
    """Create a Dependabot branch updated twice from progressively newer bases.

    Returns:
        Commit responses ordered from trusted root to PR head.
    """

    return [
        _dependabot_commit(DEPENDABOT_SHA),
        _update_commit(INTERMEDIATE_SHA, DEPENDABOT_SHA, INTERMEDIATE_BASE_SHA),
        _update_commit(HEAD_SHA, INTERMEDIATE_SHA, BASE_SHA),
    ]


def _proofs() -> list[dict[str, object]]:
    """Create valid compare evidence for every merge in the update chain.

    Returns:
        Per-merge ancestry evidence in commit order.
    """

    return [_proof(INTERMEDIATE_BASE_SHA), _proof(BASE_SHA, "identical")]


def _mapping(value: object) -> dict[str, object]:
    """Narrow one parsed value to a mapping.

    Args:
        value: Value to narrow.

    Returns:
        The value as a mapping.
    """

    assert isinstance(value, dict)
    return value


def _run(
    tmp_path: Path,
    *,
    actor: str = "dependabot[bot]",
    action: str = "reopened",
    changed_files: list[str] | None = None,
    commits: list[dict[str, object]] | None = None,
    proofs: list[dict[str, object]] | None = None,
    event: dict[str, object] | None = None,
    trusted_files: tuple[str, ...] = ("uv.lock",),
) -> subprocess.CompletedProcess[str]:
    """Execute the exported authorizer with isolated API fixtures.

    Args:
        tmp_path: Test temporary directory.
        actor: Trigger actor, deliberately not trusted by the authorizer.
        action: Pull-request event action.
        changed_files: GitHub-reported changed files.
        commits: GitHub-reported commits in history order.
        proofs: Compare API evidence for update merges.
        event: Optional replacement event fixture.
        trusted_files: Files present in the trusted base checkout.

    Returns:
        The completed Node process.
    """

    base = tmp_path / "base"
    for file in trusted_files:
        target = base / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    event_path = tmp_path / "event.json"
    files_path = tmp_path / "files"
    commits_path = tmp_path / "commits.json"
    proofs_path = tmp_path / "proofs.json"
    runner = tmp_path / "runner.mjs"
    event_path.write_text(
        json.dumps(event or _event("dependabot/uv/pytest", action)), encoding="utf-8"
    )
    files_path.write_text("\n".join(changed_files or ["uv.lock"]), encoding="utf-8")
    commits_path.write_text(json.dumps([commits or [_dependabot_commit()]]), encoding="utf-8")
    proofs_path.write_text(json.dumps(proofs or []), encoding="utf-8")
    runner.write_text(
        "\n".join(
            (
                f"import {{ authorizeDependabotUpdate }} from {AUTHORIZER.as_uri()!r};",
                'import { readFileSync } from "node:fs";',
                "const [eventPath, filesPath, commitsPath, proofsPath, base] = process.argv.slice(2);",
                'const event = JSON.parse(readFileSync(eventPath, "utf8"));',
                'const changedFiles = readFileSync(filesPath, "utf8").split("\\n").filter(Boolean);',
                'const commits = JSON.parse(readFileSync(commitsPath, "utf8")).flat();',
                'const ancestryProofs = JSON.parse(readFileSync(proofsPath, "utf8"));',
                "try { authorizeDependabotUpdate({ ancestryProofs, changedFiles, commits, event, trustedBaseDirectory: base }); }",
                "catch (error) { console.error(error.message); process.exitCode = 1; }",
            ),
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "node",
            str(runner),
            str(event_path),
            str(files_path),
            str(commits_path),
            str(proofs_path),
            str(base),
        ],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "GITHUB_ACTOR": actor},
        text=True,
    )


def test_authorizes_reopened_direct_update_and_update_branch_history(tmp_path: Path) -> None:
    """Reopened direct and GitHub Update branch histories are eligible from evidence."""

    direct = _run(tmp_path)
    updated = _run(tmp_path, actor="Snuffy2", commits=_update_chain(), proofs=_proofs())

    assert direct.returncode == 0, direct.stderr
    assert updated.returncode == 0, updated.stderr


def test_authorization_does_not_depend_on_trigger_actor_or_action(tmp_path: Path) -> None:
    """Trigger metadata cannot change authorization of identical trusted PR history."""

    for actor, action in (
        ("dependabot[bot]", "opened"),
        ("Snuffy2", "synchronize"),
        ("untrusted-user", "reopened"),
    ):
        result = _run(tmp_path, actor=actor, action=action)

        assert result.returncode == 0, result.stderr


def test_rejects_incomplete_or_invalid_ancestry_evidence(tmp_path: Path) -> None:
    """Absent, mismatched, diverged, or malformed ancestry evidence fails closed."""

    invalid_sets: tuple[list[dict[str, object]], ...] = (
        [],
        [{}, _proof(BASE_SHA, "identical")],
        [_proof(INTERMEDIATE_BASE_SHA), _proof("9" * 40)],
        [_proof(INTERMEDIATE_BASE_SHA, "diverged"), _proof(BASE_SHA, "identical")],
        [{**_proof(INTERMEDIATE_BASE_SHA), "head_commit": "8" * 40}, _proof(BASE_SHA, "identical")],
    )
    for evidence in invalid_sets:
        result = _run(tmp_path, commits=_update_chain(), proofs=evidence)

        assert result.returncode != 0


def test_rejects_untrusted_history_provenance_and_scope(tmp_path: Path) -> None:
    """Signature, web-flow history, repository provenance, and scope stay mandatory."""

    untrusted_event = _event("dependabot/uv/pytest")
    untrusted_event["pull_request"] = {
        **_mapping(untrusted_event["pull_request"]),
        "head": {
            "ref": "dependabot/uv/pytest",
            "repo": {"full_name": "fork/rtl433_esphome"},
            "sha": HEAD_SHA,
        },
    }
    for kwargs in (
        {"commits": [_dependabot_commit(verified=False)]},
        {"event": untrusted_event},
        {"changed_files": ["README.md"]},
    ):
        result = _run(tmp_path, **kwargs)

        assert result.returncode != 0


def test_rejects_non_web_flow_merge_in_an_update_branch(tmp_path: Path) -> None:
    """A verified merge by any committer other than web-flow is refused."""

    invalid_merge = _update_commit(HEAD_SHA, DEPENDABOT_SHA, BASE_SHA)
    invalid_merge["committer"] = {"login": "Snuffy2"}
    result = _run(
        tmp_path,
        commits=[_dependabot_commit(DEPENDABOT_SHA), invalid_merge],
        proofs=[_proof(BASE_SHA, "identical")],
    )

    assert result.returncode != 0


def test_preserves_trusted_base_ecosystem_policy(tmp_path: Path) -> None:
    """Actions dependency files must already exist in the trusted base checkout."""

    allowed = _run(
        tmp_path,
        changed_files=[".github/workflows/validation.yml"],
        trusted_files=(".github/workflows/validation.yml",),
        event=_event("dependabot/github_actions/actions/checkout-7"),
    )
    denied = _run(
        tmp_path,
        changed_files=["action.yml"],
        trusted_files=(".github/workflows/validation.yml",),
        event=_event("dependabot/github_actions/example/action"),
    )

    assert allowed.returncode == 0, allowed.stderr
    assert denied.returncode != 0


def _workflow(path: Path) -> dict[str, object]:
    """Parse a workflow for semantic contract assertions.

    Args:
        path: YAML workflow file.

    Returns:
        Parsed top-level workflow mapping.
    """

    return _mapping(yaml.safe_load(path.read_text(encoding="utf-8")))


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    """Get parsed workflow steps.

    Args:
        job: Parsed job mapping.

    Returns:
        Parsed step mappings in workflow order.
    """

    raw_steps = job["steps"]
    assert isinstance(raw_steps, list)
    return [_mapping(step) for step in raw_steps]


def _authorization_step(steps: list[dict[str, object]]) -> dict[str, object]:
    """Find the helper-invoking step.

    Args:
        steps: Parsed job steps.

    Returns:
        The authorization step.
    """

    for step in steps:
        if "dependabot-auto-merge.mjs" in str(step.get("run", "")):
            return step
    raise AssertionError("No authorization step found.")


def _authorization_job(
    jobs: dict[str, object],
) -> tuple[str, dict[str, object]]:
    """Find the unique job that invokes the authorization helper.

    Args:
        jobs: Parsed workflow jobs.

    Returns:
        The authorization job identifier and mapping.
    """

    candidates = [
        (name, _mapping(job))
        for name, job in jobs.items()
        if any(
            "dependabot-auto-merge.mjs" in str(step.get("run", ""))
            for step in _steps(_mapping(job))
        )
    ]
    assert len(candidates) == 1
    return candidates[0]


def _requires_eligibility(condition: object) -> None:
    """Assert a condition has all trusted Dependabot eligibility requirements.

    Args:
        condition: Parsed GitHub Actions condition.
    """

    assert isinstance(condition, str)
    for requirement in (
        "github.event.repository.fork == false",
        "github.event.pull_request.user.login == 'dependabot[bot]'",
        "github.event.pull_request.head.repo.full_name == github.repository",
        "github.event.pull_request.base.ref == github.event.repository.default_branch",
    ):
        assert requirement in condition


def _requires_author_only_dependabot_gate(condition: object) -> None:
    """Assert the authorizer runs solely for Dependabot-authored pull requests.

    Args:
        condition: Parsed GitHub Actions condition.
    """

    assert isinstance(condition, str)
    assert "github.event.pull_request.user.login == 'dependabot[bot]'" in condition
    assert set(re.findall(r"github\\.[A-Za-z_.]+", condition)) <= {
        "github.event_name",
        "github.event.pull_request.user.login",
    }


def _requires_dependabot_authored_pull_request(condition: object) -> None:
    """Assert normal CI runs trusted-base authorization for every Dependabot PR.

    Args:
        condition: Parsed GitHub Actions condition.
    """

    _requires_author_only_dependabot_gate(condition)
    assert isinstance(condition, str)
    assert "github.event_name == 'pull_request'" in condition


def _is_major_action_pin(step: dict[str, object]) -> bool:
    """Return whether a step uses an action pinned to a semantic major release.

    Args:
        step: Parsed workflow step.

    Returns:
        Whether the step uses a major-version action pin.
    """

    uses = step.get("uses")
    return isinstance(uses, str) and re.fullmatch(r"[^@]+@v\d+(?:\.\d+){0,2}", uses) is not None


def _assert_read_only_authorization(job: dict[str, object]) -> None:
    """Assert trusted checkout and authoritative API data flow before authorization.

    Args:
        job: Parsed authorization-capable job.
    """

    steps = _steps(job)
    authorization = _authorization_step(steps)
    authorization_index = steps.index(authorization)
    trusted_checkout = next(
        step
        for step in steps[:authorization_index]
        if _is_major_action_pin(step)
        and str(step.get("uses", "")).startswith("actions/checkout@")
        and _mapping(step["with"]).get("ref") == "${{ github.event.pull_request.base.sha }}"
    )
    assert _mapping(trusted_checkout["with"]).get("persist-credentials") is False
    run = authorization["run"]
    assert isinstance(run, str)
    for evidence in (
        "pulls/${PR_NUMBER}/files",
        "pulls/${PR_NUMBER}/commits",
        "compare/${second_parent}...${base_sha}",
        "dependabot-auto-merge.mjs",
    ):
        assert evidence in run


def test_workflows_authorize_before_head_checkout_with_read_only_permissions() -> None:
    """Both workflows obtain complete evidence before executing PR-controlled code."""

    auto_jobs = _mapping(_workflow(AUTO_MERGE_WORKFLOW)["jobs"])
    _, authorization = _authorization_job(auto_jobs)
    validation_jobs = _mapping(_workflow(VALIDATION_WORKFLOW)["jobs"])
    _, validation = _authorization_job(validation_jobs)
    assert _mapping(authorization["permissions"]) == {"contents": "read", "pull-requests": "read"}
    assert _mapping(validation["permissions"]) == {"contents": "read", "pull-requests": "read"}
    _requires_author_only_dependabot_gate(authorization["if"])
    _assert_read_only_authorization(authorization)

    validation_steps = _steps(validation)
    trusted_checkout = next(
        step
        for step in validation_steps
        if _is_major_action_pin(step)
        and str(step.get("uses", "")).startswith("actions/checkout@")
        and isinstance(step.get("with"), dict)
        and _mapping(step["with"]).get("ref") == "${{ github.event.pull_request.base.sha }}"
    )
    _requires_dependabot_authored_pull_request(trusted_checkout["if"])
    _requires_dependabot_authored_pull_request(_authorization_step(validation_steps)["if"])
    _assert_read_only_authorization(validation)
    head_checkout = next(
        index
        for index, step in enumerate(validation_steps)
        if _is_major_action_pin(step)
        and str(step.get("uses", "")).startswith("actions/checkout@")
        and isinstance(step.get("with"), dict)
        and "ref" not in _mapping(step["with"])
    )
    assert validation_steps.index(_authorization_step(validation_steps)) < head_checkout


def test_dependabot_write_jobs_remain_checkout_free_and_guarded() -> None:
    """Write jobs stay downstream of authorization and never execute checked-out code."""

    jobs = _mapping(_workflow(AUTO_MERGE_WORKFLOW)["jobs"])
    authorization_name, _ = _authorization_job(jobs)
    write_jobs = [
        (name, _mapping(job))
        for name, job in jobs.items()
        if any(value == "write" for value in _mapping(_mapping(job)["permissions"]).values())
    ]
    enable_candidates = [
        job for _, job in write_jobs if job.get("needs") == authorization_name and "if" not in job
    ]
    cleanup_candidates: list[dict[str, object]] = []
    for _, job in write_jobs:
        condition = job.get("if")
        if isinstance(condition, str) and "failure()" in condition:
            cleanup_candidates.append(job)
    assert len(enable_candidates) == 1
    assert len(cleanup_candidates) == 1
    enable = enable_candidates[0]
    cleanup = cleanup_candidates[0]
    assert enable["needs"] == authorization_name
    assert _mapping(enable["permissions"]) == {"contents": "write", "pull-requests": "write"}
    assert isinstance(cleanup["if"], str)
    assert "failure()" in cleanup["if"] and "!cancelled()" in cleanup["if"]
    _requires_eligibility(cleanup["if"])
    for workflow_job in jobs.values():
        parsed_job = _mapping(workflow_job)
        if any(value == "write" for value in _mapping(parsed_job["permissions"]).values()):
            assert not any(
                str(step.get("uses", "")).startswith("actions/checkout@")
                for step in _steps(parsed_job)
            )
