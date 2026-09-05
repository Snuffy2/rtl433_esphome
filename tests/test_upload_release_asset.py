"""Tests for immutable GitHub release-asset upload behavior."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "upload_release_asset.py"
REPOSITORY = "owner/repository"
RELEASE_ID = 17
TAG = "v1.2.3"
ASSET_NAME = "rtl433_esphome-v1.2.3.zip"
TOKEN = "test-token"
ASSET_CONTENT = b"firmware archive"


def load_script() -> ModuleType:
    """Load the release uploader without adding its directory to ``sys.path``.

    Returns:
        Imported release uploader module.

    Raises:
        RuntimeError: If the helper cannot be imported from its assigned path.
    """
    spec = importlib.util.spec_from_file_location("upload_release_asset", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def release(assets: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    """Return one valid published-release response with optional overrides.

    Args:
        assets: Assets returned by the release endpoint.
        **overrides: Release fields to replace for a negative case.

    Returns:
        GitHub release response fixture.
    """
    result: dict[str, Any] = {
        "assets": [] if assets is None else assets,
        "draft": False,
        "id": RELEASE_ID,
        "prerelease": False,
        "published_at": "2026-09-05T12:00:00Z",
        "tag_name": TAG,
    }
    result.update(overrides)
    return result


def uploaded_asset(asset_id: int = 99, **overrides: Any) -> dict[str, Any]:
    """Return the expected uploaded asset response with optional overrides.

    Args:
        asset_id: Immutable GitHub asset ID.
        **overrides: Asset fields to replace for a negative case.

    Returns:
        GitHub release-asset response fixture.
    """
    result: dict[str, Any] = {
        "digest": f"sha256:{hashlib.sha256(ASSET_CONTENT).hexdigest()}",
        "id": asset_id,
        "name": ASSET_NAME,
        "size": len(ASSET_CONTENT),
        "state": "uploaded",
    }
    result.update(overrides)
    return result


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    uploader: ModuleType,
    responses: list[Any],
) -> list[tuple[str, str, dict[str, str], bytes | None]]:
    """Install a scripted transport and return its recorded requests.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
        responses: Ordered responses or exceptions for the scripted transport.

    Returns:
        Recorded HTTP method, URL, headers, and body values.
    """
    calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def fake_transport(
        method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> Any:
        """Record a request and return the next scripted transport result.

        Args:
            method: HTTP method.
            url: Fully qualified GitHub endpoint.
            headers: In-memory request headers.
            body: Optional raw request body.

        Returns:
            Scripted HTTP response.

        Raises:
            RuntimeError: If the test did not provide a response for a request.
            Exception: If the scripted result is an exception.
        """
        calls.append((method, url, headers, body))
        if not responses:
            raise RuntimeError("Unexpected HTTP request")
        result = responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(uploader, "http_request", fake_transport)
    return calls


def write_asset(tmp_path: Path) -> Path:
    """Write the deterministic test firmware archive.

    Args:
        tmp_path: Test workspace.

    Returns:
        Local archive path.
    """
    path = tmp_path / ASSET_NAME
    path.write_bytes(ASSET_CONTENT)
    return path


def test_verify_only_requires_the_exact_published_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate live release identity without making an asset mutation.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release()).encode())],
    )

    uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert [call[0] for call in calls] == ["GET"]


def test_verify_only_rejects_an_invalidated_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a release changed to draft before stable Git ref promotion.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release(draft=True)).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match="expected published identity"):
        uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert [call[0] for call in calls] == ["GET"]


def test_uploads_raw_zip_and_refetches_exact_release_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upload only after identity validation and retain the exact returned asset.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(201, uploader.json.dumps(uploaded_asset()).encode()),
            uploader.HttpResponse(200, uploader.json.dumps(release([uploaded_asset()])).encode()),
        ],
    )

    uploader.upload_release_asset(
        REPOSITORY,
        RELEASE_ID,
        TAG,
        False,
        write_asset(tmp_path),
        ASSET_NAME,
        "application/zip",
        TOKEN,
    )

    assert [call[0] for call in calls] == ["GET", "GET", "POST", "GET"]
    upload = calls[2]
    assert upload[1].startswith(
        f"https://uploads.github.com/repos/{REPOSITORY}/releases/{RELEASE_ID}/assets?name="
    )
    assert upload[2]["Content-Type"] == "application/zip"
    assert upload[3] == ASSET_CONTENT


def test_rejects_mismatched_release_identity_before_asset_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a release ID mismatch before deletion or upload can occur.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release(id=RELEASE_ID + 1)).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match="expected published identity"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET"]


def test_rejects_prerelease_state_mismatch_before_asset_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a release whose prerelease state differs from candidate metadata.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release(prerelease=True)).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match="expected published identity"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET"]


def test_rejects_duplicate_existing_assets_before_recovery_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject same-name duplicates instead of selecting an ambiguous asset to delete.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(
                200,
                uploader.json.dumps(release([uploaded_asset(31), uploaded_asset(32)])).encode(),
            )
        ],
    )

    with pytest.raises(uploader.GitHubRequestError, match="duplicate assets"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET"]


def test_preserves_mismatched_existing_asset_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed when a same-name asset does not match the candidate digest.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(
                200,
                uploader.json.dumps(
                    release([uploaded_asset(31, digest="sha256:" + "0" * 64)])
                ).encode(),
            )
        ],
    )

    with pytest.raises(uploader.GitHubRequestError, match="preserve it and recover manually"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET"]


def test_retains_identical_existing_asset_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treat an already-correct uploaded asset as an idempotent success.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release([uploaded_asset(31)])).encode())],
    )

    uploader.upload_release_asset(
        REPOSITORY,
        RELEASE_ID,
        TAG,
        False,
        write_asset(tmp_path),
        ASSET_NAME,
        "application/zip",
        TOKEN,
    )

    assert [call[0] for call in calls] == ["GET"]


def test_preserves_mismatched_asset_before_transient_replacement_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Avoid the former destructive replacement path when later recovery would fail.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(
                200,
                uploader.json.dumps(
                    release([uploaded_asset(31, digest="sha256:" + "0" * 64)])
                ).encode(),
            )
        ],
    )

    with pytest.raises(uploader.GitHubRequestError, match="preserve it and recover manually"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET"]


@pytest.mark.parametrize(
    "invalid_asset",
    [
        uploaded_asset(size=len(ASSET_CONTENT) + 1),
        uploaded_asset(name="other.zip"),
        uploaded_asset(state="starter"),
        uploaded_asset(digest="sha256:" + "0" * 64),
    ],
)
def test_rejects_mismatched_upload_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_asset: dict[str, Any]
) -> None:
    """Reject an upload response that cannot prove the local archive identity.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        invalid_asset: Upload response with one invalid immutable property.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(201, uploader.json.dumps(invalid_asset).encode()),
        ],
    )

    with pytest.raises(uploader.GitHubRequestError, match="does not match the local artifact"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET", "GET", "POST"]


def test_rejects_refetched_asset_that_does_not_belong_to_uploaded_release_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require the final exact-release response to retain the uploaded asset ID.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            uploader.HttpResponse(201, uploader.json.dumps(uploaded_asset(99)).encode()),
            uploader.HttpResponse(
                200, uploader.json.dumps(release([uploaded_asset(100)])).encode()
            ),
        ],
    )

    with pytest.raises(uploader.GitHubRequestError, match="did not retain"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert [call[0] for call in calls] == ["GET", "GET", "POST", "GET"]


@pytest.mark.parametrize(
    "responses",
    [
        [
            lambda uploader: uploader.HttpResponse(500, b"{}"),
        ],
        [
            lambda uploader: uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            lambda uploader: uploader.HttpResponse(503, b"{}"),
        ],
    ],
)
def test_rejects_http_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, responses: list[Any]
) -> None:
    """Reject GitHub HTTP failures before upload confirmation.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        responses: Factories for scripted HTTP responses.
    """
    uploader = load_script()
    calls = install_transport(
        monkeypatch,
        uploader,
        [response(uploader) for response in responses],
    )

    with pytest.raises(uploader.GitHubRequestError, match="unexpected HTTP status"):
        uploader.upload_release_asset(
            REPOSITORY,
            RELEASE_ID,
            TAG,
            False,
            write_asset(tmp_path),
            ASSET_NAME,
            "application/zip",
            TOKEN,
        )

    assert calls
