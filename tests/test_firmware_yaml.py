"""Regression tests for the checked-in ESPHome firmware YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import ScalarNode


REPO_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_CONFIG = REPO_ROOT / "rtl433-esphome-heltec-lora-32-v2.yaml"
REQUIRED_KNOWN_SENSOR_KEYS = frozenset({"key", "device_id", "mapping", "entities"})
REQUIRED_KNOWN_SENSOR_ENTITIES = frozenset({"temperature", "mapping"})


class SecretSafeLoader(yaml.SafeLoader):
    """YAML loader that preserves ESPHome-specific tagged scalar values."""


def _construct_tagged_scalar(loader: yaml.Loader, node: ScalarNode) -> str:
    """Return a scalar placeholder for ESPHome tags such as ``!secret``."""

    return str(loader.construct_scalar(node))


SecretSafeLoader.add_constructor("!secret", _construct_tagged_scalar)


def _load_firmware_config() -> dict[str, Any]:
    """Load the checked-in ESPHome firmware YAML as plain mapping data."""

    config = yaml.load(FIRMWARE_CONFIG.read_text(encoding="utf-8"), Loader=SecretSafeLoader)
    if not isinstance(config, dict):
        raise TypeError("Firmware YAML must load as a mapping")
    return config


def test_local_device_yaml_uses_release_constrained_github_component() -> None:
    """Build the local device from the latest released GitHub component."""

    firmware_yaml = FIRMWARE_CONFIG.read_text(encoding="utf-8")

    assert "type: git" in firmware_yaml
    assert "rtl433_esphome_url: https://github.com/Snuffy2/rtl433_esphome.git" in firmware_yaml
    assert "url: ${rtl433_esphome_url}" in firmware_yaml
    assert "rtl433_esphome_ref: latest" in firmware_yaml
    assert "ref: ${rtl433_esphome_ref}" in firmware_yaml
    assert "refresh: never" in firmware_yaml
    assert "rtl433_native" in firmware_yaml
    assert "type: local" not in firmware_yaml
    assert "path: components" not in firmware_yaml


def test_local_device_yaml_keeps_sensor_details_in_profile() -> None:
    """Keep concrete known sensor details in the local YAML profile."""

    config = _load_firmware_config()
    known_sensors = config["rtl433_native"]["known_sensors"]

    assert known_sensors
    for known_sensor in known_sensors:
        assert REQUIRED_KNOWN_SENSOR_KEYS <= known_sensor.keys()
        assert isinstance(known_sensor["key"], str)
        assert isinstance(known_sensor["device_id"], str)
        assert isinstance(known_sensor["mapping"], str)
        assert REQUIRED_KNOWN_SENSOR_ENTITIES <= set(known_sensor["entities"])


def test_local_device_yaml_links_known_sensors_to_declared_devices() -> None:
    """Keep known sensor device references aligned with ESPHome devices."""

    config = _load_firmware_config()
    declared_device_ids = {
        device["id"] for device in config["esphome"]["devices"] if isinstance(device, dict)
    }
    referenced_device_ids = {
        known_sensor["device_id"] for known_sensor in config["rtl433_native"]["known_sensors"]
    }

    assert referenced_device_ids <= declared_device_ids
