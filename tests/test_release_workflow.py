"""Semantic contracts for release candidate promotion."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_validates_candidate_before_any_privileged_promotion() -> None:
    """The write-capable job must consume only an attested complete candidate."""

    workflow = WORKFLOW.read_text(encoding="utf-8")
    candidate_job, promotion_job = workflow.split("  promote:", maxsplit=1)

    assert "contents: write" not in candidate_job
    assert "release_firmware_artifact.py validate" in promotion_job
    assert promotion_job.index("release_firmware_artifact.py validate") < promotion_job.index(
        "git push --atomic"
    )
    assert '--force-with-lease="refs/heads/$DEFAULT_BRANCH:$SOURCE_SHA"' in promotion_job
    assert '--force-with-lease="refs/tags/$RELEASE_TAG:$TAG_OID"' in promotion_job


def test_release_workflow_delays_latest_until_attested_asset_upload() -> None:
    """Stable aliases must not move when archive upload has failed."""

    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "refs/tags/latest:$LATEST_OID" in workflow
    assert workflow.index("gh release upload") < workflow.index(
        "Compare-and-swap the stable latest alias"
    )
    assert "validation.yml" not in workflow


def test_prerelease_upload_allows_only_forward_default_history_and_original_tag() -> None:
    """A later main commit cannot replace the prerelease source or release tag."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    upload = workflow[workflow.index("Verify release identity and upload the attested firmware") :]
    upload = upload[: upload.find("\n      - name:", 1)]

    assert (
        'git merge-base --is-ancestor "$SOURCE_SHA" "refs/remotes/origin/$DEFAULT_BRANCH"' in upload
    )
    assert '"refs/tags/$RELEASE_TAG")" == "$TAG_OID"' in upload
