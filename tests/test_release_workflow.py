"""Behavioral contracts for release candidate promotion."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict[str, Any]:
    """Load a workflow without YAML 1.1 boolean coercion.

    Args:
        name: Workflow filename.

    Returns:
        Parsed workflow mapping with scalar values retained as strings.
    """

    result = yaml.load((WORKFLOW_ROOT / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(result, dict):
        raise TypeError(f"Workflow {name} is not a mapping")
    return result


def required_step(job: Mapping[str, Any], token: str) -> Mapping[str, Any]:
    """Return the unique job step whose executable content contains a token.

    Args:
        job: Parsed workflow job.
        token: Semantic command or action identifier.

    Returns:
        The unique matching step.
    """

    steps = job.get("steps")
    if not isinstance(steps, list):
        raise TypeError("Workflow job has no steps")
    matches = [
        step
        for step in steps
        if isinstance(step, dict)
        and token in "\n".join(str(step.get(key, "")) for key in ("run", "uses"))
    ]
    assert len(matches) == 1
    return matches[0]


def git(cwd: Path, *arguments: str, env: Mapping[str, str] | None = None) -> str:
    """Run Git successfully in a test repository.

    Args:
        cwd: Git working directory.
        *arguments: Git command arguments.
        env: Optional environment additions.

    Returns:
        Stripped standard output.
    """

    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.strip()


def commit(cwd: Path, message: str) -> str:
    """Commit the test repository with deterministic identity metadata.

    Args:
        cwd: Git working directory.
        message: Commit subject.

    Returns:
        New commit SHA.
    """

    git(cwd, "add", ".")
    git(
        cwd,
        "commit",
        "-m",
        message,
        env={
            "GIT_AUTHOR_NAME": "Release Test",
            "GIT_AUTHOR_EMAIL": "release@example.invalid",
            "GIT_COMMITTER_NAME": "Release Test",
            "GIT_COMMITTER_EMAIL": "release@example.invalid",
        },
    )
    return git(cwd, "rev-parse", "HEAD")


def initialize_release_remote(
    tmp_path: Path,
    release_tag: str,
    *,
    latest: bool = True,
    initial_version: str = "v1.2.2",
) -> tuple[Path, Path, str, str]:
    """Create a source checkout and bare release remote.

    Args:
        tmp_path: Temporary test root.
        release_tag: Initial lightweight release tag.
        latest: Whether the remote begins with a latest alias.
        initial_version: Version already recorded by the source commit.

    Returns:
        Worktree, bare remote, source SHA, and initial latest OID.
    """

    worktree = tmp_path / "worktree"
    remote = tmp_path / "remote.git"
    worktree.mkdir()
    git(worktree, "init", "-b", "main")
    version_script = worktree / ".github" / "scripts" / "update_release_version.py"
    version_script.parent.mkdir(parents=True)
    shutil.copy(REPO_ROOT / ".github" / "scripts" / "update_release_version.py", version_script)
    (worktree / "rtl433_esphome_version.py").write_text(
        f'"""Test version."""\n\nVERSION = "{initial_version}"\n', encoding="utf-8"
    )
    source_sha = commit(worktree, "Source")
    git(worktree, "tag", release_tag, source_sha)
    latest_oid = ""
    if latest:
        git(worktree, "tag", "latest", source_sha)
        latest_oid = source_sha
    git(remote.parent, "init", "--bare", str(remote))
    git(worktree, "remote", "add", "origin", str(remote))
    git(worktree, "push", "origin", "main", f"refs/tags/{release_tag}")
    if latest:
        git(worktree, "push", "origin", "refs/tags/latest")
    return worktree, remote, source_sha, latest_oid


def run_candidate_step(
    worktree: Path,
    source_sha: str,
    release_tag: str,
    *,
    prerelease: bool,
    release_id: str = "12345",
) -> subprocess.CompletedProcess[str]:
    """Execute the production candidate state transition in a local Git remote.

    Args:
        worktree: Checked-out event source.
        source_sha: Immutable release event SHA.
        release_tag: Published release tag.
        prerelease: GitHub release prerelease state.
        release_id: GitHub release database ID.

    Returns:
        Completed Bash process.
    """

    step = required_step(load_workflow("release.yml")["jobs"]["candidate"], "trusted_sha=")
    output = worktree / "github-output"
    return subprocess.run(
        ["bash", "-c", str(step["run"])],
        cwd=worktree,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DEFAULT_BRANCH": "main",
            "EVENT_SHA": source_sha,
            "GITHUB_OUTPUT": str(output),
            "IS_PRERELEASE": str(prerelease).lower(),
            "RELEASE_ID": release_id,
            "RELEASE_TAG": release_tag,
        },
    )


def read_outputs(path: Path) -> dict[str, str]:
    """Read simple GitHub output key-value lines.

    Args:
        path: Output file written by a workflow step.

    Returns:
        Output values keyed by name.
    """

    return dict(
        line.split("=", maxsplit=1) for line in path.read_text(encoding="utf-8").splitlines()
    )


def install_release_identity_stub(runner_temp: Path) -> Path:
    """Install a deterministic release-identity verifier for promotion tests.

    Args:
        runner_temp: Temporary runner directory used by the workflow step.

    Returns:
        Directory prepended to PATH containing a no-op GitHub CLI stub.
    """

    trusted_scripts = runner_temp / "trusted-release-scripts"
    trusted_scripts.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / ".github" / "scripts" / "update_release_version.py",
        trusted_scripts / "update_release_version.py",
    )
    (trusted_scripts / "upload_release_asset.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "import subprocess\n"
        "\n"
        "counter = Path(os.environ['RELEASE_IDENTITY_COUNTER'])\n"
        "calls = int(counter.read_text() if counter.exists() else '0') + 1\n"
        "counter.write_text(str(calls))\n"
        "if calls == int(os.environ.get('FAIL_RELEASE_IDENTITY_AT', '0')):\n"
        "    if os.environ.get('DRIFT_MAIN') == 'true':\n"
        "        subprocess.run(\n"
        "            [\n"
        "                'git', '--git-dir', os.environ['TEST_REMOTE'], 'update-ref',\n"
        "                'refs/heads/main', os.environ['DRIFT_SHA'],\n"
        "                os.environ['CANDIDATE_SHA'],\n"
        "            ],\n"
        "            check=True,\n"
        "        )\n"
        "    raise SystemExit('Simulated release identity change.')\n",
        encoding="utf-8",
    )
    bin_dir = runner_temp / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)
    return bin_dir


def run_stable_promotion_step(
    worktree: Path,
    source_sha: str,
    candidate_sha: str,
    tag_oid: str,
    runner_temp: Path,
    *,
    resume: bool,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the stable ref promotion seam against a local remote.

    Args:
        worktree: Release worktree containing the candidate commit.
        source_sha: Original published release commit.
        candidate_sha: Verified versioned release candidate commit.
        tag_oid: Original direct release-tag object ID.
        runner_temp: Temporary runner directory containing trusted test helpers.
        resume: Whether remote stable refs already identify the candidate.
        extra_env: Optional environment additions for race simulation.

    Returns:
        Completed workflow shell process.
    """

    step = required_step(load_workflow("release.yml")["jobs"]["promote"], "git push --atomic")
    counter = runner_temp / "release-identity-calls"
    return subprocess.run(
        ["bash", "-c", str(step["run"])],
        cwd=worktree,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CANDIDATE_SHA": candidate_sha,
            "DEFAULT_BRANCH": "main",
            "GH_TOKEN": "test-token",
            "GITHUB_ENV": str(runner_temp / "github-env"),
            "GITHUB_REPOSITORY": "example/release-test",
            "GITHUB_TOKEN": "test-token",
            "RELEASE_ID": "12345",
            "RELEASE_IDENTITY_COUNTER": str(counter),
            "RELEASE_TAG": "v1.2.3",
            "RESUME": str(resume).lower(),
            "RUNNER_TEMP": str(runner_temp),
            "SOURCE_SHA": source_sha,
            "TAG_OID": tag_oid,
            **(extra_env or {}),
        },
    )


@pytest.mark.parametrize("latest", [False, True])
def test_fresh_stable_candidate_is_version_only_and_supports_first_latest(
    tmp_path: Path, latest: bool
) -> None:
    """Fresh stable releases should build a bounded commit with optional latest state."""

    worktree, _remote, source_sha, latest_oid = initialize_release_remote(
        tmp_path, "v1.2.3", latest=latest
    )
    result = run_candidate_step(worktree, source_sha, "v1.2.3", prerelease=False)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(worktree / "github-output")
    assert outputs["source-sha"] == source_sha
    assert outputs["candidate-sha"] == git(worktree, "rev-parse", "HEAD")
    assert outputs["candidate-sha"] != source_sha
    assert outputs["resume"] == "false"
    assert outputs["latest-exists"] == str(latest).lower()
    assert outputs["latest-oid"] == latest_oid
    assert git(worktree, "diff", "--name-only", source_sha, outputs["candidate-sha"]) == (
        "rtl433_esphome_version.py"
    )


def test_prerelease_candidate_commits_embedded_version_without_moving_refs(tmp_path: Path) -> None:
    """Prerelease firmware provenance should include its version mutation in the bundle commit."""

    worktree, remote, source_sha, _latest_oid = initialize_release_remote(tmp_path, "v1.2.3-rc.1")
    result = run_candidate_step(worktree, source_sha, "v1.2.3-rc.1", prerelease=True)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(worktree / "github-output")
    assert outputs["candidate-sha"] != source_sha
    assert git(worktree, "rev-parse", f"{outputs['candidate-sha']}^") == source_sha
    assert git(remote, "rev-parse", "refs/heads/main") == source_sha
    assert git(remote, "rev-parse", "refs/tags/v1.2.3-rc.1") == source_sha


def test_fresh_stable_candidate_accepts_an_already_versioned_source(tmp_path: Path) -> None:
    """A stable release should not require a synthetic commit when the version already matches."""

    worktree, remote, source_sha, _latest_oid = initialize_release_remote(
        tmp_path, "v1.2.3", initial_version="v1.2.3"
    )

    result = run_candidate_step(worktree, source_sha, "v1.2.3", prerelease=False)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(worktree / "github-output")
    assert outputs["candidate-sha"] == source_sha
    assert outputs["resume"] == "false"
    assert git(remote, "rev-parse", "refs/heads/main") == source_sha
    assert git(remote, "rev-parse", "refs/tags/v1.2.3") == source_sha


@pytest.mark.parametrize(
    ("release_tag", "prerelease"),
    [("v1.2.3+build-7", False), ("v1.2.3-rc.1+build-7", True)],
)
def test_candidate_classifies_prerelease_before_build_metadata(
    tmp_path: Path, release_tag: str, prerelease: bool
) -> None:
    """Hyphens in build metadata must not be mistaken for prerelease syntax."""

    worktree, _remote, source_sha, _latest_oid = initialize_release_remote(tmp_path, release_tag)

    result = run_candidate_step(worktree, source_sha, release_tag, prerelease=prerelease)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("release_tag", "prerelease"),
    [("v1.2.3-rc.1", False), ("v1.2.3", True)],
)
def test_candidate_rejects_tag_and_prerelease_state_disagreement(
    tmp_path: Path, release_tag: str, prerelease: bool
) -> None:
    """Operator checkbox mistakes must not promote or publish the wrong release class."""

    worktree, remote, source_sha, _latest_oid = initialize_release_remote(tmp_path, release_tag)
    result = run_candidate_step(worktree, source_sha, release_tag, prerelease=prerelease)

    assert result.returncode != 0
    assert "prerelease state disagree" in result.stderr
    assert git(remote, "rev-parse", "refs/heads/main") == source_sha


def test_stable_resume_requires_the_same_annotated_tag_object(tmp_path: Path) -> None:
    """Resume metadata should retain both the release commit and direct tag identity."""

    worktree, _remote, source_sha, _latest_oid = initialize_release_remote(tmp_path, "v1.2.3")
    (worktree / "rtl433_esphome_version.py").write_text(
        '"""Test version."""\n\nVERSION = "v1.2.3"\n', encoding="utf-8"
    )
    candidate_sha = commit(worktree, "Release v1.2.3")
    git(worktree, "tag", "-fa", "v1.2.3", "-m", "Release v1.2.3", candidate_sha)
    tag_oid = git(worktree, "rev-parse", "refs/tags/v1.2.3")
    git(worktree, "push", "--force", "origin", "main", "refs/tags/v1.2.3")
    git(worktree, "checkout", "--detach", source_sha)

    result = run_candidate_step(worktree, source_sha, "v1.2.3", prerelease=False)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(worktree / "github-output")
    assert outputs["resume"] == "true"
    assert outputs["candidate-sha"] == candidate_sha
    assert outputs["tag-oid"] == tag_oid


def test_release_workflow_uses_real_artifact_and_protected_gate_contracts() -> None:
    """Promotion must consume the build output and verify every real protected check."""

    workflow = load_workflow("release.yml")
    candidate = workflow["jobs"]["candidate"]
    promote = workflow["jobs"]["promote"]
    build = required_step(candidate, "--firmware-output")
    archive = required_step(candidate, "release_firmware_artifact.py create")
    trusted_helpers = required_step(promote, "trusted_scripts=")
    gates = required_step(promote, "--required-check")
    promotion = required_step(promote, "git push --atomic")
    upload = required_step(promote, "--asset-name")
    cleanup = required_step(promote, 'origin ":refs/heads/$TEMP_REF"')

    assert "contents: write" not in candidate["permissions"]
    assert "$RUNNER_TEMP/firmware-path" in str(build["run"])
    assert "FIRMWARE_PATH_FILE" in archive["env"]
    assert ".esphome/build" not in str(archive["run"])
    assert promote["permissions"] == {
        "actions": "write",
        "checks": "read",
        "contents": "write",
        "statuses": "write",
    }
    assert set(re.findall(r"--required-check '([^']+)'", str(gates["run"]))) == {
        "validation.yml::Test and build",
        "prek-autofix-review.yml::review",
    }
    assert "upload_release_asset.py" in str(trusted_helpers["run"])
    assert "$RUNNER_TEMP/trusted-release-scripts/verify_release_checks.py" in str(gates["run"])
    assert '--workflow-ref "$DEFAULT_BRANCH"' in str(gates["run"])
    assert '--workflow-sha "$TRUSTED_WORKFLOW_SHA"' in str(gates["run"])
    assert "steps.trusted.outputs.sha" in str(gates["env"]["TRUSTED_WORKFLOW_SHA"])
    assert upload["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert '--release-id "$RELEASE_ID"' in str(upload["run"])
    assert '--expected-prerelease "$PRERELEASE"' in str(upload["run"])
    assert '--asset-name "rtl433_esphome-$RELEASE_TAG.zip"' in str(upload["run"])
    assert '--asset-name "rtl433_esphome-$RELEASE_TAG-source.bundle"' in str(upload["run"])
    promotion_run = str(promotion["run"])
    assert promotion["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert "--verify-only" in promotion_run
    assert promotion_run.index("--verify-only") < promotion_run.index("git push --atomic")
    assert '"refs/tags/$RELEASE_TAG")" == "$TAG_OID"' in str(promotion["run"])
    assert "PROMOTED_TAG_OID=" in str(promotion["run"])
    cleanup_condition = str(cleanup["if"])
    assert "success()" not in cleanup_condition
    assert "always()" in cleanup_condition
    assert "steps.validation_ref.outcome == 'success'" in cleanup_condition
    assert '--force-with-lease="refs/heads/$TEMP_REF:$CANDIDATE_SHA"' in str(cleanup["run"])


def prepare_fresh_stable_promotion(tmp_path: Path) -> tuple[Path, Path, str, str, str]:
    """Create a new stable candidate immediately before its ref promotion.

    Args:
        tmp_path: Temporary test root.

    Returns:
        Worktree, remote, source SHA, candidate SHA, and original tag object ID.
    """

    worktree, remote, source_sha, _latest_oid = initialize_release_remote(tmp_path, "v1.2.3")
    (worktree / "rtl433_esphome_version.py").write_text(
        '"""Test version."""\n\nVERSION = "v1.2.3"\n', encoding="utf-8"
    )
    candidate_sha = commit(worktree, "Release v1.2.3")
    return (
        worktree,
        remote,
        source_sha,
        candidate_sha,
        git(worktree, "rev-parse", "refs/tags/v1.2.3"),
    )


def test_stable_promotion_compensates_when_release_identity_changes(tmp_path: Path) -> None:
    """A post-push release-object failure should restore both promoted stable refs."""

    worktree, remote, source_sha, candidate_sha, tag_oid = prepare_fresh_stable_promotion(tmp_path)
    runner_temp = tmp_path / "runner-temp"
    bin_dir = install_release_identity_stub(runner_temp)

    result = run_stable_promotion_step(
        worktree,
        source_sha,
        candidate_sha,
        tag_oid,
        runner_temp,
        resume=False,
        extra_env={
            "FAIL_RELEASE_IDENTITY_AT": "3",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )

    assert result.returncode != 0
    assert "Stable refs were restored because release identity changed" in result.stderr
    assert (runner_temp / "release-identity-calls").read_text(encoding="utf-8") == "3"
    assert git(remote, "rev-parse", "refs/heads/main") == source_sha
    assert git(remote, "rev-parse", "refs/tags/v1.2.3") == tag_oid
    assert git(remote, "rev-parse", "refs/tags/v1.2.3^{}") == source_sha


def test_stable_promotion_refuses_compensation_after_a_concurrent_ref_change(
    tmp_path: Path,
) -> None:
    """A failed lease must retain a third-party main update and leave atomic rollback untouched."""

    worktree, remote, source_sha, candidate_sha, tag_oid = prepare_fresh_stable_promotion(tmp_path)
    git(worktree, "switch", "-c", "third-party", source_sha)
    (worktree / "third-party.txt").write_text("concurrent update\n", encoding="utf-8")
    drift_sha = commit(worktree, "Third-party update")
    git(worktree, "push", "origin", f"{drift_sha}:refs/heads/third-party")
    git(worktree, "switch", "--detach", candidate_sha)
    runner_temp = tmp_path / "runner-temp"
    bin_dir = install_release_identity_stub(runner_temp)

    result = run_stable_promotion_step(
        worktree,
        source_sha,
        candidate_sha,
        tag_oid,
        runner_temp,
        resume=False,
        extra_env={
            "DRIFT_MAIN": "true",
            "DRIFT_SHA": drift_sha,
            "FAIL_RELEASE_IDENTITY_AT": "3",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TEST_REMOTE": str(remote),
        },
    )

    assert result.returncode != 0
    assert "Could not atomically compensate stable refs" in result.stderr
    assert git(remote, "rev-parse", "refs/heads/main") == drift_sha
    assert git(remote, "rev-parse", "refs/tags/v1.2.3^{}") == candidate_sha


@pytest.mark.parametrize("resume", [False, True])
def test_stable_promotion_skips_compensation_when_no_refs_mutate(
    tmp_path: Path, resume: bool
) -> None:
    """Already-promoted and already-versioned releases should need only the initial identity check."""

    if resume:
        worktree, remote, source_sha, candidate_sha, tag_oid = prepare_fresh_stable_promotion(
            tmp_path
        )
        git(worktree, "tag", "-fa", "v1.2.3", "-m", "Release v1.2.3", candidate_sha)
        tag_oid = git(worktree, "rev-parse", "refs/tags/v1.2.3")
        git(worktree, "push", "--force", "origin", "main", "refs/tags/v1.2.3")
    else:
        worktree, remote, source_sha, _latest_oid = initialize_release_remote(
            tmp_path, "v1.2.3", initial_version="v1.2.3"
        )
        candidate_sha = source_sha
        tag_oid = git(worktree, "rev-parse", "refs/tags/v1.2.3")
    runner_temp = tmp_path / "runner-temp"
    bin_dir = install_release_identity_stub(runner_temp)

    result = run_stable_promotion_step(
        worktree,
        source_sha,
        candidate_sha,
        tag_oid,
        runner_temp,
        resume=resume,
        extra_env={
            "FAIL_RELEASE_IDENTITY_AT": "2",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )

    assert result.returncode == 0, result.stderr
    assert (runner_temp / "release-identity-calls").read_text(encoding="utf-8") == "1"
    assert git(remote, "rev-parse", "refs/heads/main") == candidate_sha
    assert git(remote, "rev-parse", "refs/tags/v1.2.3") == tag_oid


@pytest.mark.parametrize("workflow_name", ["validation.yml", "prek-autofix-review.yml"])
def test_release_gate_workflows_require_and_checkout_exact_sha(workflow_name: str) -> None:
    """Every dispatched gate should reject a ref that is not the requested candidate SHA."""

    workflow = load_workflow(workflow_name)
    dispatch = workflow["on"]["workflow_dispatch"]
    expected_sha = dispatch["inputs"]["expected_sha"]
    job = next(iter(workflow["jobs"].values()))
    guard = required_step(job, 'EXPECTED_SHA" =~')
    checkout = required_step(job, "actions/checkout")
    checkout_verification = required_step(job, "git rev-parse HEAD")

    assert expected_sha["required"] == "true"
    assert expected_sha["type"] == "string"
    assert guard["if"] == "github.event_name == 'workflow_dispatch'"
    assert "inputs.expected_sha" in str(checkout["with"]["ref"])
    assert '[[ "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]]' in str(checkout_verification["run"])
    if workflow_name == "validation.yml":
        compile_step = required_step(job, "./scripts/build")
        assert "inputs.expected_sha" in str(compile_step["env"]["RTL433_ESPHOME_REF"])


def prepare_promoted_release(
    tmp_path: Path, *, latest: bool
) -> tuple[Path, Path, str, str, str, str]:
    """Create remote state immediately before the stable latest transition.

    Args:
        tmp_path: Temporary test root.
        latest: Whether the remote begins with a latest alias.

    Returns:
        Worktree, remote, source SHA, candidate SHA, tag OID, and latest OID.
    """

    worktree, remote, source_sha, latest_oid = initialize_release_remote(
        tmp_path, "v1.2.3", latest=latest
    )
    (worktree / "rtl433_esphome_version.py").write_text(
        '"""Test version."""\n\nVERSION = "v1.2.3"\n', encoding="utf-8"
    )
    candidate_sha = commit(worktree, "Release v1.2.3")
    git(worktree, "tag", "-fa", "v1.2.3", "-m", "Release v1.2.3", candidate_sha)
    promoted_tag_oid = git(worktree, "rev-parse", "refs/tags/v1.2.3")
    git(worktree, "push", "--force", "origin", "main", "refs/tags/v1.2.3")
    return worktree, remote, source_sha, candidate_sha, promoted_tag_oid, latest_oid


def run_latest_step(
    worktree: Path,
    candidate_sha: str,
    promoted_tag_oid: str,
    latest_oid: str,
    *,
    latest_exists: bool,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the production stable latest transition with a stubbed GitHub CLI.

    Args:
        worktree: Release worktree.
        candidate_sha: Verified release candidate SHA.
        promoted_tag_oid: Expected annotated release tag OID.
        latest_oid: Previously observed latest OID, or empty when absent.
        latest_exists: Whether latest existed when the candidate was built.
        extra_env: Optional environment additions for race simulation.

    Returns:
        Completed Bash process.
    """

    step = required_step(load_workflow("release.yml")["jobs"]["promote"], "verify_stable_refs()")
    return subprocess.run(
        ["bash", "-c", str(step["run"])],
        cwd=worktree,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CANDIDATE_SHA": candidate_sha,
            "DEFAULT_BRANCH": "main",
            "GH_TOKEN": "test-token",
            "LATEST_EXISTS": str(latest_exists).lower(),
            "LATEST_OID": latest_oid,
            "PROMOTED_TAG_OID": promoted_tag_oid,
            "RELEASE_TAG": "v1.2.3",
            **(extra_env or {}),
        },
    )


@pytest.mark.parametrize("latest", [False, True])
def test_stable_latest_update_supports_create_and_compare_and_swap(
    tmp_path: Path, latest: bool
) -> None:
    """Stable latest should be created or moved only from its observed state."""

    worktree, remote, source_sha, candidate_sha, tag_oid, latest_oid = prepare_promoted_release(
        tmp_path, latest=latest
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)

    result = run_latest_step(
        worktree,
        candidate_sha,
        tag_oid,
        latest_oid,
        latest_exists=latest,
        extra_env={"PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert git(remote, "rev-parse", "refs/tags/latest") == candidate_sha
    assert git(remote, "rev-parse", "refs/heads/main") == candidate_sha
    assert source_sha != candidate_sha


def test_stable_latest_update_rolls_back_when_release_refs_drift(tmp_path: Path) -> None:
    """A post-upload stable-ref race must not leave latest pointing at the candidate."""

    worktree, remote, source_sha, candidate_sha, tag_oid, latest_oid = prepare_promoted_release(
        tmp_path, latest=True
    )
    drift_sha = source_sha
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        'git --git-dir="$TEST_REMOTE" update-ref refs/heads/main "$DRIFT_SHA"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)

    result = run_latest_step(
        worktree,
        candidate_sha,
        tag_oid,
        latest_oid,
        latest_exists=True,
        extra_env={
            "DRIFT_SHA": drift_sha,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TEST_REMOTE": str(remote),
        },
    )

    assert result.returncode != 0
    assert git(remote, "rev-parse", "refs/tags/latest") == source_sha
    assert git(remote, "rev-parse", "refs/heads/main") == drift_sha
