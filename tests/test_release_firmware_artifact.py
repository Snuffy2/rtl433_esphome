"""Tests for release firmware artifact and local-profile boundaries."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
import zipfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_SCRIPT = REPO_ROOT / ".github" / "scripts" / "release_firmware_artifact.py"
CONFIG_SCRIPT = REPO_ROOT / ".github" / "scripts" / "prepare_release_firmware_config.py"
OID = "a" * 40
FIRMWARE_SHA = "b" * 64


def load_script(path: Path, name: str) -> ModuleType:
    """Load a repository helper without putting its directory on sys.path.

    Args:
        path: Helper module path.
        name: Isolated module name.

    Returns:
        Imported helper module.
    """

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_candidate(tmp_path: Path) -> tuple[ModuleType, Path, dict[str, str | bool]]:
    """Create a complete bounded candidate artifact for validation tests.

    Args:
        tmp_path: Test workspace.

    Returns:
        Helper module, candidate directory, and expected metadata.
    """

    artifact = load_script(ARTIFACT_SCRIPT, "release_firmware_artifact")
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(b"firmware bytes")
    candidate_dir = tmp_path / "candidate"
    args = argparse.Namespace(
        firmware=firmware,
        archive=candidate_dir / "firmware.zip",
        candidate_sha=OID,
        source_sha=OID,
        release_tag="v1.2.3-rc.1",
        tag_oid=OID,
        latest_oid=OID,
        resume="false",
    )
    manifest = artifact.create_archive(args)
    (candidate_dir / "candidate.bundle").write_bytes(b"bounded test bundle")
    (candidate_dir / "candidate.json").write_text(json.dumps(manifest), encoding="utf-8")
    return artifact, candidate_dir, manifest


def test_release_candidate_proves_all_archive_contents(tmp_path: Path) -> None:
    """Validation should accept only the archive whose full content matches metadata."""

    artifact, candidate_dir, manifest = create_candidate(tmp_path)

    assert artifact.validate_candidate(candidate_dir) == manifest

    with zipfile.ZipFile(candidate_dir / "firmware.zip", "a") as archive:
        archive.writestr("extra.bin", b"unexpected")
    with pytest.raises(ValueError, match="missing or unexpected"):
        artifact.validate_candidate(candidate_dir)


def test_release_candidate_rejects_digest_mismatch_before_promotion(tmp_path: Path) -> None:
    """A manifest that does not hash the archived firmware must fail closed."""

    artifact, candidate_dir, manifest = create_candidate(tmp_path)
    manifest["firmware_sha256"] = FIRMWARE_SHA
    (candidate_dir / "candidate.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance"):
        artifact.validate_candidate(candidate_dir)


def test_release_candidate_rejects_duplicate_archive_members(tmp_path: Path) -> None:
    """Duplicate member names must not bypass the exact archive contract."""

    artifact, candidate_dir, _manifest = create_candidate(tmp_path)
    with zipfile.ZipFile(candidate_dir / "firmware.zip", "a") as archive:
        archive.writestr("firmware.bin", b"replacement")

    with pytest.raises(ValueError, match="missing or unexpected"):
        artifact.validate_candidate(candidate_dir)


def test_release_candidate_rejects_non_oid_metadata_before_reading_bundle(tmp_path: Path) -> None:
    """Promotion metadata must not be able to inject shell environment values."""

    artifact, candidate_dir, manifest = create_candidate(tmp_path)
    manifest["candidate_sha"] = "bad\nGITHUB_TOKEN=forged"
    (candidate_dir / "candidate.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="object ID"):
        artifact.validate_candidate(candidate_dir)


def test_prepare_release_profile_selects_checked_out_components(tmp_path: Path) -> None:
    """The release build profile must use local candidate sources, not a moving tag."""

    config = load_script(CONFIG_SCRIPT, "prepare_release_firmware_config")
    components = tmp_path / "components"
    components.mkdir()
    destination = tmp_path / "release.yaml"

    config.prepare_config(
        REPO_ROOT / "rtl433-esphome-heltec-lora-32-v2.yaml",
        destination,
        components,
    )

    output = destination.read_text(encoding="utf-8")
    assert "type: local" in output
    assert f"path: {components.resolve()}" in output
    assert "type: git" not in output
