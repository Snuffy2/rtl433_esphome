"""Tests for immutable GitHub release-asset upload behavior."""

from __future__ import annotations

import hashlib
from pathlib import Path
import socket
import ssl
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest

REPOSITORY = "owner/repository"
RELEASE_ID = 17
TAG = "v1.2.3"
ASSET_NAME = "rtl433_esphome-v1.2.3.zip"
TOKEN = "test-token"
ASSET_CONTENT = b"firmware archive"


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


@pytest.mark.parametrize(
    ("target", "expected_authorization"),
    [
        ("https://api.github.com:443/other", f"Bearer {TOKEN}"),
        ("https://api.github.com/other", f"Bearer {TOKEN}"),
        ("http://api.github.com/other", None),
        ("https://api.github.com:8443/other", None),
        ("https://api.github.com:invalid/other", None),
        ("https://evil.example/collect", None),
    ],
)
def test_redirect_handler_scopes_bearer_tokens_to_the_source_host(
    uploader: ModuleType, target: str, expected_authorization: str | None
) -> None:
    """Strip bearer authentication only when a redirect changes hosts.

    Args:
        uploader: Imported release uploader module.
        target: Redirect destination URL.
        expected_authorization: Authorization value expected after redirect.
    """
    request = uploader.Request(
        "https://api.github.com/repos/owner/repository/releases/17",
        headers={"Authorization": f"Bearer {TOKEN}"},
        method="GET",
    )
    redirected = uploader._GitHubRedirectHandler().redirect_request(
        request, None, 302, "Found", {}, target
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") == expected_authorization


def test_http_request_uses_the_scoped_redirect_handler(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Use the token-scoping handler for real HTTP request setup.

    Args:
        monkeypatch: Fixture for replacing the opener.
        uploader: Imported release uploader module.
    """
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"{}"
    response.__enter__.return_value = response
    opener = MagicMock()
    opener.open.return_value = response
    handlers: list[Any] = []

    def fake_build_opener(handler: Any) -> MagicMock:
        """Record the configured redirect handler and return a fake opener."""
        handlers.append(handler)
        return opener

    monkeypatch.setattr(uploader, "build_opener", fake_build_opener)

    result = uploader.http_request(
        "GET", "https://api.github.com/repos/owner/repository/releases/17", {}
    )

    assert result == uploader.HttpResponse(200, b"{}")
    assert len(handlers) == 1
    assert isinstance(handlers[0], uploader._GitHubRedirectHandler)


def assert_release_reads_only(calls: list[tuple[str, str, dict[str, str], bytes | None]]) -> None:
    """Require a failure path to avoid mutating release assets.

    Args:
        calls: Recorded HTTP requests.
    """
    assert calls
    assert all(method == "GET" for method, _url, _headers, _body in calls)


def assert_upload_sequence(
    calls: list[tuple[str, str, dict[str, str], bytes | None]], *, final_fetch: bool
) -> None:
    """Require reads around one upload without snapshotting incidental read count.

    Args:
        calls: Recorded HTTP requests.
        final_fetch: Whether a release read must follow the upload response.
    """
    methods = [method for method, _url, _headers, _body in calls]
    assert methods
    assert methods.count("POST") == 1
    upload_index = methods.index("POST")
    assert upload_index > 0
    assert all(method == "GET" for method in methods[:upload_index])
    trailing_methods = methods[upload_index + 1 :]
    if final_fetch:
        assert trailing_methods
        assert all(method == "GET" for method in trailing_methods)
    else:
        assert not trailing_methods


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
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Validate live release identity without making an asset mutation.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
    """
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release()).encode())],
    )

    uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert_release_reads_only(calls)


def test_verify_only_rejects_an_invalidated_release(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Reject a release changed to draft before stable Git ref promotion.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
    """
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release(draft=True)).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match="expected published identity"):
        uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert_release_reads_only(calls)


def test_uploads_raw_zip_and_refetches_exact_release_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Upload only after identity validation and retain the exact returned asset.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
    """
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

    assert_upload_sequence(calls, final_fetch=True)
    upload = next(call for call in calls if call[0] == "POST")
    assert upload[1].startswith(
        f"https://uploads.github.com/repos/{REPOSITORY}/releases/{RELEASE_ID}/assets?name="
    )
    assert upload[2]["Content-Type"] == "application/zip"
    assert upload[3] == ASSET_CONTENT


@pytest.mark.parametrize(
    ("overrides", "assets", "expected_match"),
    [
        pytest.param({"id": RELEASE_ID + 1}, None, "expected published identity", id="release-id"),
        pytest.param({"prerelease": True}, None, "expected published identity", id="prerelease"),
        pytest.param(
            {}, [uploaded_asset(31), uploaded_asset(32)], "duplicate assets", id="duplicate-assets"
        ),
        pytest.param(
            {},
            [uploaded_asset(31, digest="sha256:" + "0" * 64)],
            "preserve it and recover manually",
            id="digest-mismatch",
        ),
    ],
)
def test_rejects_invalid_release_state_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uploader: ModuleType,
    overrides: dict[str, Any],
    assets: list[dict[str, Any]] | None,
    expected_match: str,
) -> None:
    """Reject invalid release or asset state before any mutation.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
        overrides: Release fields to replace for the negative case.
        assets: Assets returned by the release endpoint.
        expected_match: Expected error text.
    """
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(200, uploader.json.dumps(release(assets, **overrides)).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match=expected_match):
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

    assert_release_reads_only(calls)


def test_retains_identical_existing_asset_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Treat an already-correct uploaded asset as an idempotent success.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
    """
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

    assert_release_reads_only(calls)


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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uploader: ModuleType,
    invalid_asset: dict[str, Any],
) -> None:
    """Reject an upload response that cannot prove the local archive identity.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
        invalid_asset: Upload response with one invalid immutable property.
    """
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

    assert_upload_sequence(calls, final_fetch=False)


def test_rejects_refetched_asset_that_does_not_belong_to_uploaded_release_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Require the final exact-release response to retain the uploaded asset ID.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
    """
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

    assert_upload_sequence(calls, final_fetch=True)


@pytest.mark.parametrize(
    "responses",
    [
        [lambda uploader: uploader.HttpResponse(500, b"{}") for _ in range(4)],
        [
            lambda uploader: uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
            *[lambda uploader: uploader.HttpResponse(503, b"{}") for _ in range(4)],
        ],
    ],
)
def test_rejects_http_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uploader: ModuleType,
    responses: list[Any],
) -> None:
    """Reject GitHub HTTP failures before upload confirmation.

    Args:
        tmp_path: Test workspace.
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
        responses: Factories for scripted HTTP responses.
    """
    monkeypatch.setattr(uploader.time, "sleep", lambda _seconds: None)
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

    assert_release_reads_only(calls)


def test_retries_transient_get_until_success(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Retry a transient GET response before accepting a valid release.

    Args:
        monkeypatch: Fixture for replacing transport and sleep.
        uploader: Imported release uploader module.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            uploader.HttpResponse(503, b"{}"),
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
        ],
    )

    uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert [method for method, _url, _headers, _body in calls] == ["GET", "GET"]
    assert delays == [1]


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(TimeoutError("timed out"), id="timeout"),
        pytest.param(ConnectionResetError("connection reset"), id="connection-reset"),
        pytest.param(ConnectionAbortedError("connection aborted"), id="connection-aborted"),
        pytest.param(ConnectionRefusedError("connection refused"), id="connection-refused"),
        pytest.param(
            socket.gaierror(socket.EAI_AGAIN, "temporary DNS failure"), id="temporary-dns"
        ),
    ],
)
def test_retries_selected_transient_url_errors(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType, reason: BaseException
) -> None:
    """Retry selected transient URL errors before accepting a valid release.

    Args:
        monkeypatch: Fixture for replacing transport and sleep.
        uploader: Imported release uploader module.
        reason: Transient transport cause wrapped by ``URLError``.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    calls = install_transport(
        monkeypatch,
        uploader,
        [
            URLError(reason),
            uploader.HttpResponse(200, uploader.json.dumps(release()).encode()),
        ],
    )

    uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert [method for method, _url, _headers, _body in calls] == ["GET", "GET"]
    assert delays == [1]


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(ssl.SSLCertVerificationError("certificate verify failed"), id="tls"),
        pytest.param(socket.gaierror(socket.EAI_NONAME, "name not known"), id="permanent-dns"),
        pytest.param("invalid URL configuration", id="configuration-string"),
        pytest.param(ValueError("malformed URL"), id="malformed-url"),
    ],
)
def test_does_not_retry_permanent_url_errors(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType, reason: BaseException
) -> None:
    """Fail immediately for URL errors that cannot recover by retrying.

    Args:
        monkeypatch: Fixture for replacing transport and sleep.
        uploader: Imported release uploader module.
        reason: Permanent transport cause wrapped by ``URLError``.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    calls = install_transport(
        monkeypatch,
        uploader,
        [URLError(reason), uploader.HttpResponse(200, uploader.json.dumps(release()).encode())],
    )

    with pytest.raises(uploader.GitHubRequestError, match="could not be completed"):
        uploader.verify_release(REPOSITORY, RELEASE_ID, TAG, False, TOKEN)

    assert len(calls) == 1
    assert delays == []


def test_get_retry_exhaustion_preserves_github_request_error(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Bound transient GET retries and retain the final status error.

    Args:
        monkeypatch: Fixture for replacing transport and sleep.
        uploader: Imported release uploader module.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    calls = install_transport(
        monkeypatch,
        uploader,
        [uploader.HttpResponse(503, b"{}") for _ in range(uploader.MAX_GET_ATTEMPTS)],
    )

    with pytest.raises(uploader.GitHubRequestError, match="unexpected HTTP status 503"):
        uploader.request_json(
            "GET", uploader.release_endpoint(REPOSITORY, RELEASE_ID), TOKEN, expected_status=200
        )

    assert len(calls) == uploader.MAX_GET_ATTEMPTS
    assert delays == [1, 2, 4]


def test_post_does_not_retry_transient_status(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Issue a POST once even when GitHub reports a transient status.

    Args:
        monkeypatch: Fixture for replacing the HTTP transport.
        uploader: Imported release uploader module.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    calls = install_transport(monkeypatch, uploader, [uploader.HttpResponse(503, b"{}")])

    with pytest.raises(uploader.GitHubRequestError, match="unexpected HTTP status 503"):
        uploader.request_json(
            "POST",
            "https://uploads.github.com/asset",
            TOKEN,
            expected_status=201,
            body=b"asset",
        )

    assert len(calls) == 1
    assert delays == []


def test_post_does_not_retry_transport_failure(
    monkeypatch: pytest.MonkeyPatch, uploader: ModuleType
) -> None:
    """Issue a POST once when the transport reports a transient URL error.

    Args:
        monkeypatch: Fixture for replacing the opener and sleep.
        uploader: Imported release uploader module.
    """
    delays: list[int] = []
    monkeypatch.setattr(uploader.time, "sleep", delays.append)
    opener = MagicMock()
    opener.open.side_effect = URLError(ConnectionResetError("connection reset"))
    monkeypatch.setattr(uploader, "build_opener", lambda _handler: opener)

    with pytest.raises(uploader.GitHubRequestError, match="could not be completed"):
        uploader.request_json(
            "POST",
            "https://uploads.github.com/asset",
            TOKEN,
            expected_status=201,
            body=b"asset",
        )

    opener.open.assert_called_once()
    assert delays == []
