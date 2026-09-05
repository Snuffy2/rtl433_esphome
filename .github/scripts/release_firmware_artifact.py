"""Create and validate bounded firmware artifacts for release promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

MAX_BUNDLE_BYTES = 32 * 1024 * 1024
MAX_CANDIDATE_JSON_BYTES = 4 * 1024
MAX_FIRMWARE_BYTES = 12 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 16 * 1024 * 1024
FIRMWARE_NAME = "firmware.bin"
MANIFEST_NAME = "release-manifest.json"
REQUIRED_CANDIDATE_FILES = {"candidate.bundle", "candidate.json", "firmware.zip"}
GIT_OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SEMVER_TAG_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def parse_args() -> argparse.Namespace:
    """Parse artifact creation and validation arguments.

    Returns:
        Parsed command-line arguments.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--firmware", type=Path, required=True)
    create.add_argument("--archive", type=Path, required=True)
    create.add_argument("--candidate-sha", required=True)
    create.add_argument("--source-sha", required=True)
    create.add_argument("--release-tag", required=True)
    create.add_argument("--release-id", required=True)
    create.add_argument("--prerelease", choices=("true", "false"), required=True)
    create.add_argument("--tag-oid", required=True)
    create.add_argument("--latest-oid", required=True)
    create.add_argument("--latest-exists", choices=("true", "false"), required=True)
    create.add_argument("--resume", choices=("true", "false"), required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--candidate-dir", type=Path, required=True)
    return parser.parse_args()


def regular_file(path: Path, maximum_size: int) -> int:
    """Require a regular, non-symlink file within a byte bound.

    Args:
        path: File to inspect without following a symlink.
        maximum_size: Largest permitted file size in bytes.

    Returns:
        The checked file size.

    Raises:
        ValueError: If the file is missing, unsafe, or too large.
    """

    try:
        metadata = path.lstat()
    except OSError as err:
        raise ValueError(f"Could not stat {path}") from err
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Expected a regular file: {path}")
    if metadata.st_size > maximum_size:
        raise ValueError(f"File exceeds {maximum_size} byte limit: {path}")
    return metadata.st_size


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of an already bounded regular file.

    Args:
        path: Validated file to hash.

    Returns:
        Lowercase SHA-256 digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_manifest(args: argparse.Namespace, firmware_digest: str) -> dict[str, str | bool]:
    """Create the signed-by-content release candidate metadata.

    Args:
        args: Creation command arguments.
        firmware_digest: SHA-256 digest of the archived firmware.

    Returns:
        Strict release candidate metadata.
    """

    return {
        "candidate_sha": args.candidate_sha,
        "firmware_sha256": firmware_digest,
        "latest_exists": args.latest_exists == "true",
        "latest_oid": args.latest_oid,
        "prerelease": args.prerelease == "true",
        "release_id": args.release_id,
        "release_tag": args.release_tag,
        "resume": args.resume == "true",
        "source_sha": args.source_sha,
        "tag_oid": args.tag_oid,
    }


def create_archive(args: argparse.Namespace) -> dict[str, str | bool]:
    """Build a small firmware archive and return its provenance manifest.

    Args:
        args: Creation command arguments.

    Returns:
        Metadata also written inside the archive.

    Raises:
        ValueError: If the firmware file is unsafe.
    """

    regular_file(args.firmware, MAX_FIRMWARE_BYTES)
    firmware_digest = sha256_file(args.firmware)
    manifest = candidate_manifest(args, firmware_digest)
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(args.firmware, FIRMWARE_NAME)
        manifest_info = zipfile.ZipInfo(MANIFEST_NAME)
        manifest_info.external_attr = (stat.S_IFREG | 0o600) << 16
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(manifest_info, manifest_json)
    regular_file(args.archive, MAX_ARCHIVE_BYTES)
    return manifest


def read_candidate_manifest(path: Path) -> dict[str, str | bool]:
    """Read constrained candidate metadata after its bounds are checked.

    Args:
        path: Candidate JSON file.

    Returns:
        Parsed candidate metadata.

    Raises:
        TypeError: If the resume field is not a boolean.
        ValueError: If the JSON is malformed or has unexpected fields.
    """

    regular_file(path, MAX_CANDIDATE_JSON_BYTES)
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError("Candidate metadata is not valid JSON") from err
    expected = {
        "candidate_sha",
        "firmware_sha256",
        "latest_exists",
        "latest_oid",
        "prerelease",
        "release_id",
        "release_tag",
        "resume",
        "source_sha",
        "tag_oid",
    }
    if not isinstance(content, dict) or set(content) != expected:
        raise ValueError("Candidate metadata fields do not match the release contract")
    for key in ("latest_exists", "prerelease", "resume"):
        if not isinstance(content[key], bool):
            raise TypeError(f"Candidate {key.replace('_', ' ')} state must be a boolean")
    for key in expected - {"latest_exists", "prerelease", "resume", "latest_oid"}:
        if not isinstance(content[key], str) or not content[key]:
            raise ValueError(f"Candidate metadata field {key} must be a non-empty string")
    if not isinstance(content["latest_oid"], str):
        raise TypeError("Candidate metadata field latest_oid must be a string")
    for key in ("candidate_sha", "source_sha", "tag_oid"):
        if GIT_OID_PATTERN.fullmatch(content[key]) is None:
            raise ValueError(f"Candidate metadata field {key} must be a Git object ID")
    if content["latest_exists"]:
        if GIT_OID_PATTERN.fullmatch(content["latest_oid"]) is None:
            raise ValueError("Candidate metadata field latest_oid must be a Git object ID")
    elif content["latest_oid"]:
        raise ValueError("Candidate metadata field latest_oid must be empty when latest is absent")
    if not content["release_id"].isdigit() or int(content["release_id"]) <= 0:
        raise ValueError("Candidate release ID must be a positive integer")
    if SHA256_PATTERN.fullmatch(content["firmware_sha256"]) is None:
        raise ValueError("Candidate firmware digest must be a SHA-256 digest")
    if SEMVER_TAG_PATTERN.fullmatch(content["release_tag"]) is None:
        raise ValueError("Candidate release tag must be semantic version")
    return content


def safe_zip_member(info: zipfile.ZipInfo) -> None:
    """Reject archive members that can escape or inflate the artifact boundary.

    Args:
        info: ZIP metadata to validate before content is read.

    Raises:
        ValueError: If the member is unsafe or too large.
    """

    mode = info.external_attr >> 16
    if info.flag_bits & 0x1:
        raise ValueError("Encrypted archive members are not permitted")
    if info.filename.startswith("/") or ".." in Path(info.filename).parts:
        raise ValueError(f"Unsafe archive member path: {info.filename}")
    if info.is_dir() or not stat.S_ISREG(mode):
        raise ValueError(f"Archive member is not a regular file: {info.filename}")
    if info.file_size > MAX_FIRMWARE_BYTES:
        raise ValueError(f"Archive member exceeds byte limit: {info.filename}")


def validate_archive(path: Path, expected: dict[str, str | bool]) -> None:
    """Validate every archive member and prove firmware content provenance.

    Args:
        path: Firmware ZIP file.
        expected: Candidate metadata that must equal the embedded manifest.

    Raises:
        ValueError: If the archive contents or provenance are invalid.
    """

    regular_file(path, MAX_ARCHIVE_BYTES)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                len(infos) != 2
                or len(names) != len(set(names))
                or set(names) != {FIRMWARE_NAME, MANIFEST_NAME}
            ):
                raise ValueError("Firmware archive has missing or unexpected members")
            expanded = 0
            for info in infos:
                safe_zip_member(info)
                expanded += info.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise ValueError("Firmware archive expanded size exceeds limit")
            firmware = archive.read(FIRMWARE_NAME)
            embedded = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, json.JSONDecodeError) as err:
        raise ValueError("Firmware archive is unreadable") from err
    if embedded != expected:
        raise ValueError("Embedded firmware provenance does not match candidate metadata")
    if hashlib.sha256(firmware).hexdigest() != expected["firmware_sha256"]:
        raise ValueError("Firmware digest does not match candidate metadata")


def validate_candidate(candidate_dir: Path) -> dict[str, str | bool]:
    """Validate the complete downloaded candidate boundary before promotion.

    Args:
        candidate_dir: Downloaded artifact directory.

    Returns:
        Validated candidate metadata.

    Raises:
        ValueError: If files are missing, extra, unsafe, or unproven.
    """

    try:
        directory_metadata = candidate_dir.lstat()
    except OSError as err:
        raise ValueError("Candidate directory is missing") from err
    if not stat.S_ISDIR(directory_metadata.st_mode):
        raise ValueError("Candidate path must be a real directory")
    files = {path.name for path in candidate_dir.iterdir()}
    if files != REQUIRED_CANDIDATE_FILES:
        raise ValueError("Candidate directory has missing or unexpected files")
    regular_file(candidate_dir / "candidate.bundle", MAX_BUNDLE_BYTES)
    metadata = read_candidate_manifest(candidate_dir / "candidate.json")
    validate_archive(candidate_dir / "firmware.zip", metadata)
    return metadata


def main() -> None:
    """Run the selected artifact operation."""

    args = parse_args()
    try:
        if args.command == "create":
            result = create_archive(args)
        else:
            result = validate_candidate(args.candidate_dir)
    except (TypeError, ValueError) as err:
        raise SystemExit(str(err)) from err
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
