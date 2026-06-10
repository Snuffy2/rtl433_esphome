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
    CONFIG_SCHEMA,
    CONF_BATTERY,
    CONF_CANDIDATE_LIMIT,
    CONF_CANDIDATES,
    CONF_CLEAR_CANDIDATES_BUTTON,
    CONF_DISCOVERY_ENABLED,
    CONF_DISCOVERY_MODE,
    CONF_HUMIDITY,
    CONF_KEY,
    CONF_KNOWN_PACKET_COUNT,
    CONF_KNOWN_SENSORS,
    CONF_LAST_PACKET,
    CONF_LAST_UPDATED,
    CONF_LED_PIN,
    CONF_MAPPING,
    CONF_PACKET_COUNT,
    CONF_RADIO,
    CONF_RSSI,
    CONF_STALE,
    CONF_STALE_AFTER,
    CONF_STATUS_BUTTON,
    CONF_TEMPERATURE,
    CONF_TIME_ID,
    CONF_UNKNOWN_PACKET_COUNT,
    DEFAULT_RADIO_CONFIG,
    action_to_code,
    to_code,
    _validate_known_sensor_keys,
    _validate_mapping,
    _validate_stale_after,
)

EXPECTED_BUILD_FLAGS = [
    ARDUINO_NETWORK_INCLUDE_FLAG,
    "-include src/esphome/components/rtl433_native/ledc_compat.h",
    "-DRF_SX1278",
    "-DRF_MODULE_FREQUENCY=433.92",
    "-DRF_MODULE_DIO0=26",
    "-DRF_MODULE_DIO1=35",
    "-DRF_MODULE_DIO2=34",
    "-DRF_MODULE_RST=14",
    "-DRF_MODULE_CS=18",
    "-DRF_MODULE_SCK=5",
    "-DRF_MODULE_MISO=19",
    "-DRF_MODULE_MOSI=27",
]

GENERATED_GATEWAY_METHODS = frozenset(
    {
        "add_mapping",
        "set_battery_sensor",
        "set_candidate_limit",
        "set_candidate_text_sensor",
        "set_discovery_enabled_sensor",
        "set_humidity_sensor",
        "set_known_packet_count_sensor",
        "set_led_pin",
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

GENERATED_MAPPING_TEXT_METHODS = frozenset(
    {
        "set_initial_value",
        "set_logical_key",
        "set_parent",
    }
)

GENERATED_GATEWAY_CONTROL_METHODS = frozenset({"set_parent"})

GATEWAY_DIAGNOSTIC_DEFAULTS = (
    (CONF_LAST_PACKET, "Last Packet"),
    (CONF_PACKET_COUNT, "Packet Count"),
    (CONF_KNOWN_PACKET_COUNT, "Known Packet Count"),
    (CONF_UNKNOWN_PACKET_COUNT, "Unknown Packet Count"),
    (CONF_DISCOVERY_ENABLED, "Discovery Enabled"),
)
GATEWAY_CONTROL_DEFAULTS = (
    (CONF_DISCOVERY_MODE, "Discovery Mode"),
    (CONF_CLEAR_CANDIDATES_BUTTON, "Clear Candidates"),
    (CONF_STATUS_BUTTON, "Radio Status"),
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
class FakeMappingText:
    """Test double that records generated mapping text method calls."""

    name: str
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: Any) -> tuple[str, tuple[Any, ...]]:
        """Record a generated mapping text method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[Any, ...]]]:
        """Return a recorder for known generated mapping text methods."""

        if name not in GENERATED_MAPPING_TEXT_METHODS:
            raise AttributeError(name)

        def recorder(*args: Any) -> tuple[str, tuple[Any, ...]]:
            """Record a generated mapping text method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeGatewayControl:
    """Test double that records generated gateway control method calls."""

    name: str
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: Any) -> tuple[str, tuple[Any, ...]]:
        """Record a generated gateway control method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[Any, ...]]]:
        """Return a recorder for known generated gateway control methods."""

        if name not in GENERATED_GATEWAY_CONTROL_METHODS:
            raise AttributeError(name)

        def recorder(*args: Any) -> tuple[str, tuple[Any, ...]]:
            """Record a generated gateway control method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeCodegen:
    """Test double for the ESPHome codegen module."""

    gateway: FakeGateway
    added: list[Any] = field(default_factory=list)
    build_flags: list[str] = field(default_factory=list)
    libraries: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    platformio_options: list[tuple[str, str | list[str]]] = field(default_factory=list)
    new_pvariable_calls: list[tuple[Any, ...]] = field(default_factory=list)
    registered_components: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)
    registered_parents: list[tuple[Any, Any]] = field(default_factory=list)
    variables: dict[Any, Any] = field(default_factory=dict)

    @property
    def App(self) -> Any:  # noqa: N802
        """Return a small fake Application codegen object."""

        class FakeApp:
            """Test double for cg.App."""

            @staticmethod
            def register_component_(var: Any) -> tuple[str, Any]:
                """Record direct component registration expression."""

                return "register_component", var

        return FakeApp

    def add(self, expression: Any) -> None:
        """Record a generated expression."""

        self.added.append(expression)

    def add_build_flag(self, flag: str) -> None:
        """Record a build flag."""

        self.build_flags.append(flag)

    def add_library(self, name: str, version: str | None, repository: str | None = None) -> None:
        """Record a PlatformIO library dependency."""

        self.libraries.append((name, version, repository))

    def add_platformio_option(self, name: str, value: str | list[str]) -> None:
        """Record a PlatformIO option."""

        self.platformio_options.append((name, value))

    def new_Pvariable(self, *args: Any) -> Any:  # noqa: N802
        """Create a fake Pvariable value."""

        self.new_pvariable_calls.append(args)
        if len(args) == 1:
            return self.gateway
        return {"action_id": args[0], "template_arg": args[1]}

    async def register_component(self, var: Any, config: dict[str, Any]) -> None:
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


@dataclass
class FakeTextModule:
    """Test double for ESPHome text factories."""

    created: list[dict[str, Any]] = field(default_factory=list)
    texts: list[FakeMappingText] = field(default_factory=list)

    class TextMode:
        """Test double for text mode enum values."""

        TEXT_MODE_TEXT = "TEXT_MODE_TEXT"

    async def new_text(
        self,
        config: dict[str, Any],
        *,
        min_length: int | None = 0,
        max_length: int | None = 255,
        pattern: str | None = None,
    ) -> FakeMappingText:
        """Record text creation and return a fake text input."""

        del min_length, max_length, pattern
        self.created.append(config)
        text_input = FakeMappingText(config["name"])
        self.texts.append(text_input)
        return text_input


@dataclass
class FakeSwitchModule:
    """Test double for ESPHome switch factories."""

    created: list[dict[str, Any]] = field(default_factory=list)
    switches: list[FakeGatewayControl] = field(default_factory=list)

    async def new_switch(self, config: dict[str, Any]) -> FakeGatewayControl:
        """Record switch creation and return a fake switch."""

        self.created.append(config)
        gateway_switch = FakeGatewayControl(config["name"])
        self.switches.append(gateway_switch)
        return gateway_switch


@dataclass
class FakeButtonModule:
    """Test double for ESPHome button factories."""

    created: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[FakeGatewayControl] = field(default_factory=list)

    async def new_button(self, config: dict[str, Any]) -> FakeGatewayControl:
        """Record button creation and return a fake button."""

        self.created.append(config)
        gateway_button = FakeGatewayControl(config["name"])
        self.buttons.append(gateway_button)
        return gateway_button


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
    text: FakeTextModule
    switch: FakeSwitchModule
    button: FakeButtonModule


def install_codegen_fakes(
    monkeypatch: pytest.MonkeyPatch, variables: dict[Any, Any] | None = None
) -> FakeCodegenEnvironment:
    """Install ESPHome codegen fakes and return them for assertions.

    Args:
        monkeypatch: Pytest monkeypatch fixture used to replace ESPHome codegen
            modules with local fakes.
        variables: Optional fake codegen variable lookup values keyed by
            ESPHome ID.

    Returns:
        Installed fake codegen environment containing the gateway recorder,
        codegen module, sensor module, binary sensor module, and text sensor
        module fakes.
    """

    gateway = FakeGateway()
    fake_cg = FakeCodegen(gateway=gateway, variables=variables or {})
    fake_sensor = FakeSensorModule(prefix="sensor")
    fake_binary_sensor = FakeBinarySensorModule()
    fake_text_sensor = FakeTextSensorModule()
    fake_text = FakeTextModule()
    fake_switch = FakeSwitchModule()
    fake_button = FakeButtonModule()
    monkeypatch.setattr(rtl433_native, "cg", fake_cg)
    monkeypatch.setattr(rtl433_native, "sensor", fake_sensor)
    monkeypatch.setattr(rtl433_native, "binary_sensor", fake_binary_sensor)
    monkeypatch.setattr(rtl433_native, "text_sensor", fake_text_sensor)
    monkeypatch.setattr(rtl433_native, "text", fake_text)
    monkeypatch.setattr(rtl433_native, "switch", fake_switch)
    monkeypatch.setattr(rtl433_native, "button", fake_button)
    return FakeCodegenEnvironment(
        gateway=gateway,
        codegen=fake_cg,
        sensor=fake_sensor,
        binary_sensor=fake_binary_sensor,
        text_sensor=fake_text_sensor,
        text=fake_text,
        switch=fake_switch,
        button=fake_button,
    )


def compact_known_sensor_config(
    name: str, entities: list[str], key: str = "garage_freezer_1"
) -> dict[str, Any]:
    """Return a compact known sensor test config."""

    return {
        CONF_KEY: key,
        "name": name,
        CONF_MAPPING: "Acurite-986/1R/11932",
        "entities": entities,
    }


def _entity_name_and_category(config: dict[str, Any]) -> tuple[str, str]:
    """Return stable entity identity fields from a generated config."""

    return config["name"], config["entity_category"]


def gateway_diagnostic_overrides(prefix: str) -> dict[str, dict[str, str]]:
    """Return unique gateway diagnostic configs for schema test isolation."""

    return {
        key: {"name": f"{prefix} {name}", "entity_category": "diagnostic"}
        for key, name in GATEWAY_DIAGNOSTIC_DEFAULTS
    }


def gateway_control_overrides(prefix: str) -> dict[str, dict[str, str]]:
    """Return unique gateway control configs for schema test isolation."""

    return {
        key: {"name": f"{prefix} {name}", "entity_category": "config"}
        for key, name in GATEWAY_CONTROL_DEFAULTS
    }


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


@pytest.mark.parametrize("key", ["garage-freezer-1", "Acurite-986/1R/11932", "1_freezer"])
def test_config_schema_rejects_known_sensor_keys_that_cannot_generate_ids(key: str) -> None:
    """Reject logical keys that cannot safely form generated ESPHome IDs."""

    fixture_name = f"Invalid Key {key}"
    with pytest.raises(cv.Invalid):
        CONFIG_SCHEMA(
            {
                CONF_ID: "gateway_id",
                **gateway_diagnostic_overrides(fixture_name),
                **gateway_control_overrides(fixture_name),
                CONF_KNOWN_SENSORS: [
                    {
                        CONF_KEY: key,
                        CONF_MAPPING: "Acurite-986/1R/11932",
                        CONF_TEMPERATURE: {"name": f"{fixture_name} Temperature"},
                    }
                ],
            }
        )


async def test_to_code_wires_all_configured_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code for known sensors, diagnostics, counters, candidates, and time."""

    fake_env = install_codegen_fakes(monkeypatch, variables={"time_id": "time:clock"})

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 2,
        CONF_LED_PIN: 25,
        CONF_RADIO: DEFAULT_RADIO_CONFIG,
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

    assert fake_env.codegen.build_flags == EXPECTED_BUILD_FLAGS
    assert fake_env.codegen.platformio_options == [("lib_ldf_mode", "chain+")]
    assert fake_env.codegen.libraries == [
        ("rtl_433_ESP", None, "https://github.com/NorthernMan54/rtl_433_ESP.git#v0.3.3"),
        ("RadioLib", "6.2.0", None),
        ("Networking", None, None),
        ("SPI", None, None),
        ("EEPROM", None, None),
    ]
    assert fake_env.codegen.new_pvariable_calls == [("gateway_id",)]
    assert fake_env.codegen.registered_components[0] == (fake_env.gateway, config)
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
    assert [text_config["name"] for text_config in fake_env.text.created] == ["temperature Mapping"]
    assert fake_env.text.texts[0].calls == [
        ("set_parent", (fake_env.gateway,)),
        ("set_logical_key", ("garage_freezer_1",)),
        ("set_initial_value", ("Acurite-986/1R/11932",)),
    ]
    assert fake_env.gateway.calls == [
        ("set_candidate_limit", (2,)),
        ("set_stale_after_ms", (3_600_000,)),
        ("set_led_pin", (25,)),
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
    for call in fake_env.gateway.calls:
        assert call in fake_env.codegen.added
    for call in fake_env.text.texts[0].calls:
        assert call in fake_env.codegen.added


async def test_to_code_wires_required_entities_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code when optional entities and time are omitted."""

    fake_env = install_codegen_fakes(monkeypatch)

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 1,
        CONF_LED_PIN: 25,
        CONF_RADIO: DEFAULT_RADIO_CONFIG,
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

    assert fake_env.codegen.build_flags == EXPECTED_BUILD_FLAGS
    assert fake_env.codegen.platformio_options == [("lib_ldf_mode", "chain+")]
    assert fake_env.codegen.libraries == [
        ("rtl_433_ESP", None, "https://github.com/NorthernMan54/rtl_433_ESP.git#v0.3.3"),
        ("RadioLib", "6.2.0", None),
        ("Networking", None, None),
        ("SPI", None, None),
        ("EEPROM", None, None),
    ]
    assert fake_env.codegen.new_pvariable_calls == [("gateway_id",)]
    assert fake_env.codegen.registered_components[0] == (fake_env.gateway, config)
    assert fake_env.sensor.created == [{"name": "temperature"}]
    assert fake_env.binary_sensor.created == []
    assert fake_env.text_sensor.created == []
    assert [text_config["name"] for text_config in fake_env.text.created] == ["temperature Mapping"]
    assert fake_env.text.texts[0].calls == [
        ("set_parent", (fake_env.gateway,)),
        ("set_logical_key", ("garage_freezer_1",)),
        ("set_initial_value", ("Acurite-986/1R/11932",)),
    ]
    assert fake_env.gateway.calls == [
        ("set_candidate_limit", (1,)),
        ("set_stale_after_ms", (60_000,)),
        ("set_led_pin", (25,)),
        ("add_mapping", ("garage_freezer_1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage_freezer_1", "sensor:temperature")),
    ]
    for call in fake_env.gateway.calls:
        assert call in fake_env.codegen.added
    for call in fake_env.text.texts[0].calls:
        assert call in fake_env.codegen.added


def test_config_schema_generates_candidate_sensors_from_limit() -> None:
    """Create default candidate text sensors when only a limit is configured."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            CONF_CANDIDATE_LIMIT: 2,
            **gateway_diagnostic_overrides("Candidates Fixture"),
            **gateway_control_overrides("Candidates Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_freezer_1",
                    CONF_MAPPING: "Acurite-986/1R/11932",
                    CONF_TEMPERATURE: {"name": "default profile temperature"},
                }
            ],
        }
    )

    assert [
        {
            "name": candidate["name"],
            "entity_category": candidate["entity_category"],
            "disabled_by_default": candidate["disabled_by_default"],
            "icon": candidate["icon"],
        }
        for candidate in config[CONF_CANDIDATES]
    ] == [
        {
            "name": "Candidate 1",
            "entity_category": "diagnostic",
            "disabled_by_default": False,
            "icon": "mdi:radio-tower",
        },
        {
            "name": "Candidate 2",
            "entity_category": "diagnostic",
            "disabled_by_default": False,
            "icon": "mdi:radio-tower",
        },
    ]


async def test_config_schema_generates_default_gateway_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create default gateway diagnostic entities when omitted."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            CONF_CANDIDATES: [],
            **gateway_control_overrides("Default Diagnostics Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Default Diagnostics Fixture", ["temperature"])
            ],
        }
    )
    fake_env = install_codegen_fakes(monkeypatch)

    await to_code(config)

    assert [_entity_name_and_category(config[key]) for key, _ in GATEWAY_DIAGNOSTIC_DEFAULTS] == [
        (name, "diagnostic") for _, name in GATEWAY_DIAGNOSTIC_DEFAULTS
    ]
    assert _entity_name_and_category(fake_env.text_sensor.created[0]) == (
        "Last Packet",
        "diagnostic",
    )
    assert [_entity_name_and_category(entity) for entity in fake_env.sensor.created[-3:]] == [
        ("Packet Count", "diagnostic"),
        ("Known Packet Count", "diagnostic"),
        ("Unknown Packet Count", "diagnostic"),
    ]
    assert _entity_name_and_category(fake_env.binary_sensor.created[0]) == (
        "Discovery Enabled",
        "diagnostic",
    )


async def test_config_schema_generates_default_gateway_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create default gateway config controls when omitted."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            CONF_CANDIDATES: [],
            **gateway_diagnostic_overrides("Default Controls Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Default Controls Fixture", ["temperature"])
            ],
        }
    )
    fake_env = install_codegen_fakes(monkeypatch)

    await to_code(config)

    assert [_entity_name_and_category(config[key]) for key, _ in GATEWAY_CONTROL_DEFAULTS] == [
        (name, "config") for _, name in GATEWAY_CONTROL_DEFAULTS
    ]
    assert [_entity_name_and_category(entity) for entity in fake_env.switch.created] == [
        ("Discovery Mode", "config")
    ]
    assert [_entity_name_and_category(entity) for entity in fake_env.button.created] == [
        ("Clear Candidates", "config"),
        ("Radio Status", "config"),
    ]
    assert fake_env.switch.switches[0].calls == [("set_parent", (fake_env.gateway,))]
    assert fake_env.button.buttons[0].calls == [("set_parent", (fake_env.gateway,))]
    assert fake_env.button.buttons[1].calls == [("set_parent", (fake_env.gateway,))]


def test_config_schema_supplies_default_hardware_profile() -> None:
    """Use component hardware defaults when LED and radio options are omitted."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **gateway_diagnostic_overrides("Hardware Fixture"),
            **gateway_control_overrides("Hardware Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_freezer_1",
                    CONF_MAPPING: "Acurite-986/1R/11932",
                    CONF_TEMPERATURE: {"name": "temperature"},
                }
            ],
        }
    )

    assert config[CONF_LED_PIN] == 25
    assert config[CONF_RADIO] == DEFAULT_RADIO_CONFIG


def test_config_schema_expands_compact_known_sensor_entities() -> None:
    """Expand compact known sensor entries into generated entity configs."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **gateway_diagnostic_overrides("Compact Fixture"),
            **gateway_control_overrides("Compact Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    "name": "Garage Combo Fridge",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    "entities": [
                        "temperature",
                        "humidity",
                        "battery",
                        "rssi",
                        "stale",
                        "last_updated",
                        "mapping",
                    ],
                }
            ],
        }
    )

    entry = config[CONF_KNOWN_SENSORS][0]

    assert entry[CONF_TEMPERATURE]["name"] == "Garage Combo Fridge Temperature"
    assert entry[CONF_HUMIDITY]["name"] == "Garage Combo Fridge Humidity"
    assert entry[CONF_BATTERY]["name"] == "Garage Combo Fridge Battery"
    assert entry[CONF_RSSI]["name"] == "Garage Combo Fridge RSSI"
    assert entry[CONF_STALE]["name"] == "Garage Combo Fridge Stale"
    assert entry[CONF_LAST_UPDATED]["name"] == "Garage Combo Fridge Last Updated"
    assert entry[CONF_HUMIDITY]["entity_category"] == "diagnostic"
    assert entry[CONF_BATTERY]["entity_category"] == "diagnostic"
    assert entry[CONF_RSSI]["entity_category"] == "diagnostic"
    assert entry[CONF_STALE]["entity_category"] == "diagnostic"
    assert entry[CONF_LAST_UPDATED]["entity_category"] == "diagnostic"


async def test_compact_known_sensor_mapping_entity_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip the mapping text entity when compact config omits mapping from entities."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            CONF_CANDIDATE_LIMIT: 1,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            **gateway_diagnostic_overrides("No Mapping Fixture"),
            **gateway_control_overrides("No Mapping Fixture"),
            CONF_KNOWN_SENSORS: [compact_known_sensor_config("Garage Freezer 1", ["temperature"])],
        }
    )
    fake_env = install_codegen_fakes(monkeypatch)

    await to_code(config)

    assert fake_env.text.created == []
    expected_calls = [
        ("set_candidate_limit", (1,)),
        ("set_stale_after_ms", (60_000,)),
        ("set_led_pin", (25,)),
        ("add_mapping", ("garage_freezer_1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage_freezer_1", "sensor:Garage Freezer 1 Temperature")),
    ]
    for call in expected_calls:
        assert call in fake_env.gateway.calls


async def test_compact_known_sensor_mapping_entity_uses_base_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Name compact mapping text entities from the base known sensor name."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            CONF_CANDIDATE_LIMIT: 1,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            **gateway_diagnostic_overrides("Mapping Fixture"),
            **gateway_control_overrides("Mapping Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Garage Mapping Fixture", ["temperature", "mapping"])
            ],
        }
    )
    fake_env = install_codegen_fakes(monkeypatch)

    await to_code(config)

    assert [text_config["name"] for text_config in fake_env.text.created] == [
        "Garage Mapping Fixture Mapping"
    ]


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
