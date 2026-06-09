"""Tests for rtl433_native ESPHome config validation."""

import pytest
from esphome import config_validation as cv

from components.rtl433_native import _validate_sensor_key


def test_validate_sensor_key_accepts_model_channel_id() -> None:
    """Accept full rtl_433 sensor keys used by mapping aliases."""

    assert _validate_sensor_key("LaCrosse-TX141THBv2/1/88") == "LaCrosse-TX141THBv2/1/88"


@pytest.mark.parametrize(
    "sensor_key",
    [
        "LaCrosse-TX141THBv2/88",
        "LaCrosse-TX141THBv2//88",
        "LaCrosse-TX141THBv2/1/88/extra",
    ],
)
def test_validate_sensor_key_rejects_malformed_key(sensor_key: str) -> None:
    """Reject aliases that cannot be parsed as model/channel/id."""

    with pytest.raises(cv.Invalid):
        _validate_sensor_key(sensor_key)
