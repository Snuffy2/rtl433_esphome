"""Regression tests for the checked-in ESPHome firmware YAML."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_CONFIG = REPO_ROOT / "rtl433-esphome-heltec-lora-32-v2.yaml"


def test_local_device_yaml_uses_release_constrained_github_component() -> None:
    """Build the local device from the latest released GitHub component."""

    firmware_yaml = FIRMWARE_CONFIG.read_text(encoding="utf-8")

    assert "type: git" in firmware_yaml
    assert "url: https://github.com/Snuffy2/rtl433_esphome.git" in firmware_yaml
    assert "rtl433_esphome_ref: latest" in firmware_yaml
    assert "ref: ${rtl433_esphome_ref}" in firmware_yaml
    assert "refresh: never" in firmware_yaml
    assert "rtl433_native" in firmware_yaml
    assert "type: local" not in firmware_yaml
    assert "path: components" not in firmware_yaml


def test_local_device_yaml_keeps_sensor_details_in_profile() -> None:
    """Keep deployment-specific freezer and fridge mappings in the local YAML."""

    firmware_yaml = FIRMWARE_CONFIG.read_text(encoding="utf-8")

    assert "known_sensors:" in firmware_yaml
    for logical_key in (
        "key: garage_combo_fridge",
        "key: garage_combo_freezer",
        "key: garage_freezer_1",
        "key: garage_freezer_2",
    ):
        assert logical_key in firmware_yaml
