"""Tests for rtl433_native ESPHome config validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from esphome import config_validation as cv
from esphome.const import CONF_ID

import components.rtl433_native as rtl433_native
from components.rtl433_native import (
    ARDUINO_NETWORK_INCLUDE_FLAG,
    CONF_BATTERY,
    CONF_CANDIDATE_LIMIT,
    CONF_CANDIDATES,
    CONF_DISCOVERY_ENABLED,
    CONF_HUMIDITY,
    CONF_KEY,
    CONF_KNOWN_PACKET_COUNT,
    CONF_KNOWN_SENSORS,
    CONF_LAST_PACKET,
    CONF_LAST_UPDATED,
    CONF_MAPPING,
    CONF_PACKET_COUNT,
    CONF_RSSI,
    CONF_STALE,
    CONF_STALE_AFTER,
    CONF_TEMPERATURE,
    CONF_TIME_ID,
    CONF_UNKNOWN_PACKET_COUNT,
    action_to_code,
    to_code,
    _validate_known_sensor_keys,
    _validate_mapping,
    _validate_stale_after,
)

GENERATED_GATEWAY_METHODS = frozenset(
    {
        "add_mapping",
        "set_battery_sensor",
        "set_candidate_limit",
        "set_candidate_text_sensor",
        "set_discovery_enabled_sensor",
        "set_humidity_sensor",
        "set_known_packet_count_sensor",
        "set_last_packet_sensor",
        "set_last_updated_sensor",
        "set_packet_count_sensor",
        "set_rssi_sensor",
        "set_stale_after_ms",
        "set_stale_sensor",
        "set_temperature_sensor",
        "set_time",
        "set_unknown_packet_count_sensor",
    }
)


@dataclass
class FakeGateway:
    """Test double that records generated gateway method calls."""

    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: Any) -> tuple[str, tuple[Any, ...]]:
        """Record a generated gateway method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[Any, ...]]]:
        """Return a recorder for known generated gateway methods."""

        if name not in GENERATED_GATEWAY_METHODS:
            raise AttributeError(name)

        def recorder(*args: Any) -> tuple[str, tuple[Any, ...]]:
            """Record a generated gateway method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeCodegen:
    """Test double for the ESPHome codegen module."""

    gateway: FakeGateway
    added: list[Any] = field(default_factory=list)
    build_flags: list[str] = field(default_factory=list)
    new_pvariable_calls: list[tuple[Any, ...]] = field(default_factory=list)
    registered_components: list[tuple[FakeGateway, dict[str, Any]]] = field(default_factory=list)
    registered_parents: list[tuple[Any, Any]] = field(default_factory=list)
    variables: dict[Any, Any] = field(default_factory=dict)

    def add(self, expression: Any) -> None:
        """Record a generated expression."""

        self.added.append(expression)

    def add_build_flag(self, flag: str) -> None:
        """Record a build flag."""

        self.build_flags.append(flag)

    def new_Pvariable(self, *args: Any) -> Any:  # noqa: N802
        """Create a fake Pvariable value."""

        self.new_pvariable_calls.append(args)
        if len(args) == 1:
            return self.gateway
        return {"action_id": args[0], "template_arg": args[1]}

    async def register_component(self, var: FakeGateway, config: dict[str, Any]) -> None:
        """Record component registration."""

        self.registered_components.append((var, config))

    async def register_parented(self, var: Any, parent: Any) -> None:
        """Record parented action registration."""

        self.registered_parents.append((var, parent))

    async def get_variable(self, value: Any) -> Any:
        """Return a fake resolved variable."""

        return self.variables[value]


@dataclass
class FakeSensorModule:
    """Test double for ESPHome sensor factories."""

    prefix: str
    created: list[dict[str, Any]] = field(default_factory=list)

    async def new_sensor(self, config: dict[str, Any]) -> str:
        """Record sensor creation and return a fake sensor."""

        self.created.append(config)
        return f"{self.prefix}:{config['name']}"


@dataclass
class FakeBinarySensorModule:
    """Test double for ESPHome binary sensor factories."""

    created: list[dict[str, Any]] = field(default_factory=list)

    async def new_binary_sensor(self, config: dict[str, Any]) -> str:
        """Record binary sensor creation and return a fake binary sensor."""

        self.created.append(config)
        return f"binary:{config['name']}"


@dataclass
class FakeTextSensorModule:
    """Test double for ESPHome text sensor factories."""

    created: list[dict[str, Any]] = field(default_factory=list)

    async def new_text_sensor(self, config: dict[str, Any]) -> str:
        """Record text sensor creation and return a fake text sensor."""

        self.created.append(config)
        return f"text:{config['name']}"


@dataclass(frozen=True)
class FakeTimePeriod:
    """Small stand-in for ESPHome time period values."""

    total_milliseconds: int


@dataclass(frozen=True)
class FakeCodegenEnvironment:
    """Installed ESPHome codegen fakes for a test."""

    gateway: FakeGateway
    codegen: FakeCodegen
    sensor: FakeSensorModule
    binary_sensor: FakeBinarySensorModule
    text_sensor: FakeTextSensorModule


def install_codegen_fakes(
    monkeypatch: pytest.MonkeyPatch, variables: dict[Any, Any] | None = None
) -> FakeCodegenEnvironment:
    """Install ESPHome codegen fakes and return them for assertions."""

    gateway = FakeGateway()
    fake_cg = FakeCodegen(gateway=gateway, variables=variables or {})
    fake_sensor = FakeSensorModule(prefix="sensor")
    fake_binary_sensor = FakeBinarySensorModule()
    fake_text_sensor = FakeTextSensorModule()
    monkeypatch.setattr(rtl433_native, "cg", fake_cg)
    monkeypatch.setattr(rtl433_native, "sensor", fake_sensor)
    monkeypatch.setattr(rtl433_native, "binary_sensor", fake_binary_sensor)
    monkeypatch.setattr(rtl433_native, "text_sensor", fake_text_sensor)
    return FakeCodegenEnvironment(
        gateway=gateway,
        codegen=fake_cg,
        sensor=fake_sensor,
        binary_sensor=fake_binary_sensor,
        text_sensor=fake_text_sensor,
    )


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


def test_validate_mapping_normalizes_slash_spaced_fields() -> None:
    """Trim whitespace around model, channel, and id fields."""

    assert (
        _validate_mapping("TFA-303221 / 2 / 88 ; LaCrosse-TX141THBv2 / 1 / 88")
        == "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88"
    )


def test_arduino_network_include_flag_quotes_platformio_path() -> None:
    """Keep PlatformIO package paths with spaces as one include flag."""

    assert ARDUINO_NETWORK_INCLUDE_FLAG == (
        '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
    )


def test_validate_stale_after_accepts_uint32_millisecond_value() -> None:
    """Accept stale durations that fit C++ uint32_t millisecond storage."""

    assert _validate_stale_after("1h").total_milliseconds == 3_600_000


def test_validate_stale_after_rejects_uint32_millisecond_overflow() -> None:
    """Reject stale durations too large for C++ uint32_t millisecond storage."""

    with pytest.raises(cv.Invalid):
        _validate_stale_after("50d")


def test_validate_known_sensor_keys_rejects_duplicates() -> None:
    """Reject duplicated logical sensor keys before code generation."""

    with pytest.raises(cv.Invalid):
        _validate_known_sensor_keys(
            [{CONF_KEY: "garage_freezer_1"}, {CONF_KEY: "garage_freezer_1"}]
        )


def test_validate_known_sensor_keys_accepts_unique_keys() -> None:
    """Accept unique logical sensor keys and return the original config."""

    config = [{CONF_KEY: "garage_freezer_1"}, {CONF_KEY: "garage_freezer_2"}]

    assert _validate_known_sensor_keys(config) is config


async def test_to_code_wires_all_configured_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code for known sensors, diagnostics, counters, candidates, and time."""

    fake_env = install_codegen_fakes(monkeypatch, variables={"time_id": "time:clock"})

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 2,
        CONF_STALE_AFTER: FakeTimePeriod(total_milliseconds=3_600_000),
        CONF_TIME_ID: "time_id",
        CONF_KNOWN_SENSORS: [
            {
                CONF_KEY: "garage_freezer_1",
                CONF_MAPPING: "Acurite-986/1R/11932",
                CONF_TEMPERATURE: {"name": "temperature"},
                CONF_HUMIDITY: {"name": "humidity"},
                CONF_BATTERY: {"name": "battery"},
                CONF_RSSI: {"name": "rssi"},
                CONF_STALE: {"name": "stale"},
                CONF_LAST_UPDATED: {"name": "last_updated"},
            }
        ],
        CONF_CANDIDATES: [{"name": "candidate_0"}, {"name": "candidate_1"}],
        CONF_LAST_PACKET: {"name": "last_packet"},
        CONF_PACKET_COUNT: {"name": "packet_count"},
        CONF_KNOWN_PACKET_COUNT: {"name": "known_packet_count"},
        CONF_UNKNOWN_PACKET_COUNT: {"name": "unknown_packet_count"},
        CONF_DISCOVERY_ENABLED: {"name": "discovery_enabled"},
    }

    await to_code(config)

    assert fake_env.codegen.build_flags == [ARDUINO_NETWORK_INCLUDE_FLAG]
    assert fake_env.codegen.new_pvariable_calls == [("gateway_id",)]
    assert fake_env.codegen.registered_components == [(fake_env.gateway, config)]
    assert fake_env.sensor.created == [
        {"name": "temperature"},
        {"name": "humidity"},
        {"name": "rssi"},
        {"name": "last_updated"},
        {"name": "packet_count"},
        {"name": "known_packet_count"},
        {"name": "unknown_packet_count"},
    ]
    assert fake_env.binary_sensor.created == [
        {"name": "battery"},
        {"name": "stale"},
        {"name": "discovery_enabled"},
    ]
    assert fake_env.text_sensor.created == [
        {"name": "candidate_0"},
        {"name": "candidate_1"},
        {"name": "last_packet"},
    ]
    assert fake_env.gateway.calls == [
        ("set_candidate_limit", (2,)),
        ("set_stale_after_ms", (3_600_000,)),
        ("set_time", ("time:clock",)),
        ("add_mapping", ("garage_freezer_1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage_freezer_1", "sensor:temperature")),
        ("set_humidity_sensor", ("garage_freezer_1", "sensor:humidity")),
        ("set_battery_sensor", ("garage_freezer_1", "binary:battery")),
        ("set_rssi_sensor", ("garage_freezer_1", "sensor:rssi")),
        ("set_stale_sensor", ("garage_freezer_1", "binary:stale")),
        ("set_last_updated_sensor", ("garage_freezer_1", "sensor:last_updated")),
        ("set_candidate_text_sensor", (0, "text:candidate_0")),
        ("set_candidate_text_sensor", (1, "text:candidate_1")),
        ("set_last_packet_sensor", ("text:last_packet",)),
        ("set_packet_count_sensor", ("sensor:packet_count",)),
        ("set_known_packet_count_sensor", ("sensor:known_packet_count",)),
        ("set_unknown_packet_count_sensor", ("sensor:unknown_packet_count",)),
        ("set_discovery_enabled_sensor", ("binary:discovery_enabled",)),
    ]
    assert fake_env.codegen.added == fake_env.gateway.calls


async def test_to_code_wires_required_entities_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code when optional entities and time are omitted."""

    fake_env = install_codegen_fakes(monkeypatch)

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 1,
        CONF_STALE_AFTER: FakeTimePeriod(total_milliseconds=60_000),
        CONF_KNOWN_SENSORS: [
            {
                CONF_KEY: "garage_freezer_1",
                CONF_MAPPING: "Acurite-986/1R/11932",
                CONF_TEMPERATURE: {"name": "temperature"},
            }
        ],
        CONF_CANDIDATES: [],
    }

    await to_code(config)

    assert fake_env.codegen.build_flags == [ARDUINO_NETWORK_INCLUDE_FLAG]
    assert fake_env.codegen.new_pvariable_calls == [("gateway_id",)]
    assert fake_env.codegen.registered_components == [(fake_env.gateway, config)]
    assert fake_env.sensor.created == [{"name": "temperature"}]
    assert fake_env.binary_sensor.created == []
    assert fake_env.text_sensor.created == []
    assert fake_env.gateway.calls == [
        ("set_candidate_limit", (1,)),
        ("set_stale_after_ms", (60_000,)),
        ("add_mapping", ("garage_freezer_1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage_freezer_1", "sensor:temperature")),
    ]
    assert fake_env.codegen.added == fake_env.gateway.calls


async def test_action_to_code_registers_parented_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate parented action code for rtl433_native actions."""

    fake_cg = FakeCodegen(gateway=FakeGateway())
    monkeypatch.setattr(rtl433_native, "cg", fake_cg)

    result = await action_to_code({CONF_ID: "gateway_id"}, "action_id", "template_arg", ())

    assert result == {"action_id": "action_id", "template_arg": "template_arg"}
    assert fake_cg.new_pvariable_calls == [("action_id", "template_arg")]
    assert fake_cg.registered_parents == [(result, "gateway_id")]


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
