"""Tests for rtl433_native ESPHome config validation."""

import pytest
from esphome import config_validation as cv

from components.rtl433_native import ARDUINO_NETWORK_INCLUDE_FLAG, _validate_mapping


def test_validate_mapping_accepts_semicolon_delimited_sensor_keys() -> None:
    """Accept mapping strings with one primary key and synonyms."""

    assert (
        _validate_mapping("TFA-303221/2/88;LaCrosse-TX141THBv2/1/88")
        == "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88"
    )


def test_validate_mapping_normalizes_spaced_sensor_keys() -> None:
    """Trim whitespace around semicolon-delimited mapping entries."""

    assert (
        _validate_mapping(" TFA-303221/2/88 ; LaCrosse-TX141THBv2/1/88 ")
        == "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88"
    )


def test_arduino_network_include_flag_quotes_platformio_path() -> None:
    """Keep PlatformIO package paths with spaces as one include flag."""

    assert ARDUINO_NETWORK_INCLUDE_FLAG == (
        '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
    )


@pytest.mark.parametrize(
    "sensor_key",
    [
        "LaCrosse-TX141THBv2/88",
        "LaCrosse-TX141THBv2//88",
        "LaCrosse-TX141THBv2/1/88/extra",
    ],
)
def test_validate_mapping_rejects_malformed_key(sensor_key: str) -> None:
    """Reject mappings that cannot be parsed as model/channel/id entries."""

    with pytest.raises(cv.Invalid):
        _validate_mapping(sensor_key)


@pytest.mark.parametrize(
    "mapping",
    [
        "",
        "TFA-303221/2/88;",
        ";TFA-303221/2/88",
        "TFA-303221/2/88;;LaCrosse-TX141THBv2/1/88",
    ],
)
def test_validate_mapping_rejects_empty_segments(mapping: str) -> None:
    """Reject blank mapping strings and empty semicolon-delimited entries."""

    with pytest.raises(cv.Invalid):
        _validate_mapping(mapping)
