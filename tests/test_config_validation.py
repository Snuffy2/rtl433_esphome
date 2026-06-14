"""Tests for rtl433_native ESPHome config validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from esphome import config_validation as cv
from esphome.const import (
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_DISABLED_BY_DEFAULT,
    CONF_ESPHOME,
    CONF_ID,
    CONF_NAME,
    CONF_OTA,
    CONF_PLATFORMIO_OPTIONS,
)
from esphome.core import CORE
import esphome.final_validate as fv
import pytest

import components.rtl433_native as rtl433_native
from components.rtl433_native import (
    ARDUINO_NETWORK_INCLUDE_FLAG,
    CONF_BATTERY,
    CONF_CANDIDATE_LIMIT,
    CONF_CANDIDATES,
    CONF_CLEAR_CANDIDATES_BUTTON,
    CONF_CS,
    CONF_DIO0,
    CONF_DIO1,
    CONF_DIO2,
    CONF_DISCOVERY_MODE,
    CONF_ENTITIES,
    CONF_EXTRA_SCRIPTS,
    CONF_FREQUENCY,
    CONF_HUMIDITY,
    CONF_KEY,
    CONF_KNOWN_PACKET_COUNT,
    CONF_KNOWN_SENSORS,
    CONF_LAST_PACKET,
    CONF_LAST_UPDATED,
    CONF_LED_PIN,
    CONF_MAPPING,
    CONF_MISO,
    CONF_MODULE,
    CONF_MOSI,
    CONF_PACKET_COUNT,
    CONF_PINS,
    CONF_RADIO,
    CONF_RSSI,
    CONF_RST,
    CONF_SCK,
    CONF_STALE,
    CONF_STALE_AFTER,
    CONF_STATUS_BUTTON,
    CONF_TEMPERATURE,
    CONF_TIME_ID,
    CONF_UNKNOWN_PACKET_COUNT,
    CONFIG_SCHEMA,
    DEFAULT_RADIO_CONFIG,
    RTL433_ESP_PREBUILD_SCRIPT,
    _project_version,
    _validate_known_sensor_keys,
    _validate_mapping,
    _validate_radio_module,
    _validate_stale_after,
    action_to_code,
    to_code,
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


class IdLike(Protocol):
    """Protocol for ESPHome ID-like objects used by test fakes."""

    id: str


EXPECTED_PLATFORMIO_OPTIONS = [
    ("lib_ldf_mode", "chain+"),
    (CONF_EXTRA_SCRIPTS, [RTL433_ESP_PREBUILD_SCRIPT]),
]
EXPECTED_LIBRARY_NAMES = ["rtl_433_ESP", "RadioLib", "Networking", "SPI", "EEPROM"]

GENERATED_GATEWAY_METHODS = frozenset(
    {
        "add_mapping",
        "set_battery_sensor",
        "set_candidate_limit",
        "set_candidate_text_sensor",
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
        "set_version",
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
)
GATEWAY_CONTROL_DEFAULTS = (
    (CONF_DISCOVERY_MODE, "Discovery Mode"),
    (CONF_CLEAR_CANDIDATES_BUTTON, "Clear Candidates"),
    (CONF_STATUS_BUTTON, "Radio Status"),
)
REQUIRED_TIME_CONFIG = {CONF_TIME_ID: "time_id"}


@dataclass
class FakeGateway:
    """Test double that records generated gateway method calls."""

    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: object) -> tuple[str, tuple[object, ...]]:
        """Record a generated gateway method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[object, ...]]]:
        """Return a recorder for known generated gateway methods."""

        if name not in GENERATED_GATEWAY_METHODS:
            raise AttributeError(name)

        def recorder(*args: object) -> tuple[str, tuple[object, ...]]:
            """Record a generated gateway method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeMappingText:
    """Test double that records generated mapping text method calls."""

    name: str
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: object) -> tuple[str, tuple[object, ...]]:
        """Record a generated mapping text method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[object, ...]]]:
        """Return a recorder for known generated mapping text methods."""

        if name not in GENERATED_MAPPING_TEXT_METHODS:
            raise AttributeError(name)

        def recorder(*args: object) -> tuple[str, tuple[object, ...]]:
            """Record a generated mapping text method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeGatewayControl:
    """Test double that records generated gateway control method calls."""

    name: str
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def _record(self, name: str, *args: object) -> tuple[str, tuple[object, ...]]:
        """Record a generated gateway control method call."""

        self.calls.append((name, args))
        return name, args

    def __getattr__(self, name: str) -> Callable[..., tuple[str, tuple[object, ...]]]:
        """Return a recorder for known generated gateway control methods."""

        if name not in GENERATED_GATEWAY_CONTROL_METHODS:
            raise AttributeError(name)

        def recorder(*args: object) -> tuple[str, tuple[object, ...]]:
            """Record a generated gateway control method call."""

            return self._record(name, *args)

        return recorder


@dataclass
class FakeCodegen:
    """Test double for the ESPHome codegen module."""

    gateway: FakeGateway
    added: list[Any] = field(default_factory=list)
    build_flags: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
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

    def add_define(self, define: str) -> None:
        """Record a generated preprocessor define."""

        self.defines.append(define)

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
    name: str,
    entities: list[str],
    key: str = "garage_freezer_1",
    device_id: str | None = None,
) -> dict[str, Any]:
    """Return a compact known sensor test config."""

    config = {
        CONF_KEY: key,
        "name": name,
        CONF_MAPPING: "Acurite-986/1R/11932",
        CONF_ENTITIES: entities,
    }
    if device_id is not None:
        config[CONF_DEVICE_ID] = device_id
    return config


class FakeFinalValidateConfig:
    """Minimal ESPHome final-validation config for device ID lookups."""

    def __init__(self, devices: dict[str, dict[str, Any]]) -> None:
        """Initialize the fake with device configs keyed by ID."""

        self._devices = devices

    def get_path_for_id(self, id_value: IdLike | str) -> list[Any]:
        """Return the validated config path for a declared device ID."""

        id_string = id_value if isinstance(id_value, str) else id_value.id
        device_ids = list(self._devices)
        if id_string not in self._devices:
            raise KeyError(id_string)
        return [CONF_ESPHOME, CONF_DEVICES, device_ids.index(id_string), CONF_ID]

    def get_config_for_path(self, path: list[Any]) -> dict[str, Any]:
        """Return the device config for a validated config path."""

        device_id = list(self._devices)[path[2]]
        return self._devices[device_id]


def long_mapping_fixture() -> str:
    """Return a valid mapping longer than the mapping text storage limit."""

    sensor_key = "Acurite-986/1R/11932"
    return ";".join(sensor_key for _ in range(13))


def _entity_name_and_category(config: dict[str, Any]) -> tuple[str, str]:
    """Return stable entity identity fields from a generated config."""

    return config["name"], config["entity_category"]


def install_project_version_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pyproject_text: str
) -> None:
    """Install a temporary component tree for project version tests."""

    component_file = tmp_path / "components" / "rtl433_native" / "__init__.py"
    component_file.parent.mkdir(parents=True)
    component_file.write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    monkeypatch.setattr(rtl433_native, "__file__", str(component_file))


def install_codegen_fakes_for_config(
    monkeypatch: pytest.MonkeyPatch, config: dict[str, Any]
) -> FakeCodegenEnvironment:
    """Install codegen fakes that can resolve the config's required time source."""

    return install_codegen_fakes(monkeypatch, variables={config[CONF_TIME_ID]: "time:clock"})


def assert_codegen_dependencies(
    fake_env: FakeCodegenEnvironment, *, expect_ota_listener: bool
) -> None:
    """Assert generated PlatformIO build flags and options."""

    assert "ota" not in rtl433_native.AUTO_LOAD
    assert fake_env.codegen.build_flags == EXPECTED_BUILD_FLAGS
    assert fake_env.codegen.platformio_options == EXPECTED_PLATFORMIO_OPTIONS
    assert [library[0] for library in fake_env.codegen.libraries] == EXPECTED_LIBRARY_NAMES
    if expect_ota_listener:
        assert "USE_OTA_STATE_LISTENER" in fake_env.codegen.defines
    else:
        assert "USE_OTA_STATE_LISTENER" not in fake_env.codegen.defines


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


def test_config_schema_requires_time_id() -> None:
    """Require a wall-clock time source for restored stale-state aging."""

    with pytest.raises(cv.Invalid, match="time_id"):
        CONFIG_SCHEMA(
            {
                CONF_ID: "gateway_id",
                **gateway_diagnostic_overrides("Missing Time Fixture"),
                **gateway_control_overrides("Missing Time Fixture"),
                CONF_KNOWN_SENSORS: [
                    compact_known_sensor_config("Missing Time Fixture", ["temperature"])
                ],
            }
        )


@pytest.mark.parametrize(
    ("mapping", "expected"),
    [
        pytest.param(
            "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88",
            "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88",
            id="semicolon-delimited",
        ),
        pytest.param(
            " TFA-303221/2/88 ; LaCrosse-TX141THBv2/1/88 ",
            "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88",
            id="spaced-segments",
        ),
        pytest.param(
            "TFA-303221 / 2 / 88 ; LaCrosse-TX141THBv2 / 1 / 88",
            "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88",
            id="spaced-fields",
        ),
    ],
)
def test_validate_mapping_accepts_and_normalizes_sensor_key_lists(
    mapping: str, expected: str
) -> None:
    """Accept mapping lists and normalize safe whitespace."""

    assert _validate_mapping(mapping) == expected


def test_validate_mapping_accepts_values_exceeding_mapping_text_limit() -> None:
    """Allow long mappings when no runtime mapping text storage is involved."""

    mapping = long_mapping_fixture()

    assert _validate_mapping(mapping) == mapping


def test_config_schema_rejects_long_generated_mapping_text_value() -> None:
    """Reject mappings that cannot fit in generated runtime mapping text storage."""

    config = compact_known_sensor_config("Long Mapping Text Fixture", ["temperature", "mapping"])
    config[CONF_MAPPING] = long_mapping_fixture()

    with pytest.raises(cv.Invalid, match=f"exceeds {rtl433_native.MAPPING_TEXT_MAX_LENGTH}"):
        CONFIG_SCHEMA(
            {
                CONF_ID: "gateway_id",
                **REQUIRED_TIME_CONFIG,
                **gateway_diagnostic_overrides("Long Mapping Text Fixture"),
                **gateway_control_overrides("Long Mapping Text Fixture"),
                CONF_KNOWN_SENSORS: [config],
            }
        )


def test_config_schema_accepts_long_mapping_without_generated_text() -> None:
    """Accept long mappings when compact config does not generate a mapping text entity."""

    config = compact_known_sensor_config("Long Mapping No Text Fixture", ["temperature"])
    config[CONF_MAPPING] = long_mapping_fixture()

    validated = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Long Mapping No Text Fixture"),
            **gateway_control_overrides("Long Mapping No Text Fixture"),
            CONF_KNOWN_SENSORS: [config],
        }
    )

    assert validated[CONF_KNOWN_SENSORS][0][CONF_MAPPING] == config[CONF_MAPPING]


@pytest.mark.parametrize(
    ("pyproject_text", "expected_version"),
    [
        pytest.param(
            '[project]\nname = "rtl433-esphome"\nversion = "v9.8.7"\n',
            "v9.8.7",
            id="matching-package",
        ),
        pytest.param(
            '[project]\nname = "other-project"\nversion = "v9.8.7"\n',
            "unknown",
            id="foreign-package",
        ),
        pytest.param(
            '[project]\nname = "rtl433-esphome"\n',
            "unknown",
            id="missing-version",
        ),
        pytest.param("[project\n", "unknown", id="malformed-metadata"),
    ],
)
def test_project_version_reads_owned_package_metadata_or_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pyproject_text: str, expected_version: str
) -> None:
    """Read owned package metadata and fall back safely for unusable metadata."""

    install_project_version_fixture(monkeypatch, tmp_path, pyproject_text)

    assert _project_version() == expected_version


def test_arduino_network_include_flag_quotes_platformio_path() -> None:
    """Keep PlatformIO package paths with spaces as one include flag."""

    assert ARDUINO_NETWORK_INCLUDE_FLAG == (
        '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
    )


def test_rtl433_esp_prebuild_script_uses_absolute_path() -> None:
    """Keep PlatformIO extra_scripts independent from generated build directory depth."""

    script_scope, script_path = RTL433_ESP_PREBUILD_SCRIPT.split(":", 1)

    assert script_scope == "pre"
    assert Path(script_path).is_absolute()
    assert Path(script_path).name == "rtl433_esp_prebuild.py"


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
def test_config_schema_accepts_legacy_known_sensor_keys(key: str) -> None:
    """Accept existing logical keys even when generated ESPHome IDs need sanitizing."""

    fixture_name = f"Legacy Key {key}"
    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
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

    assert config[CONF_KNOWN_SENSORS][0][CONF_KEY] == key


def test_config_schema_rejects_duplicate_generated_mapping_text_ids() -> None:
    """Reject distinct logical keys that collide after mapping text ID sanitizing."""

    with pytest.raises(cv.Invalid, match="duplicate mapping text ID 'garage_freezer_1_mapping'"):
        CONFIG_SCHEMA(
            {
                CONF_ID: "gateway_id",
                **REQUIRED_TIME_CONFIG,
                **gateway_diagnostic_overrides("Duplicate Mapping ID Fixture"),
                **gateway_control_overrides("Duplicate Mapping ID Fixture"),
                CONF_KNOWN_SENSORS: [
                    {
                        CONF_KEY: "garage-freezer-1",
                        CONF_MAPPING: "Acurite-986/1R/11932",
                        CONF_TEMPERATURE: {"name": "Garage Freezer Dashed Temperature"},
                    },
                    {
                        CONF_KEY: "garage_freezer_1",
                        CONF_MAPPING: "Acurite-986/2F/31274",
                        CONF_TEMPERATURE: {"name": "Garage Freezer Underscore Temperature"},
                    },
                ],
            }
        )


async def test_to_code_wires_all_configured_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code for known sensors, diagnostics, counters, candidates, and time."""

    fake_env = install_codegen_fakes(monkeypatch, variables={"time_id": "time:clock"})
    monkeypatch.setattr(CORE, "config", {CONF_OTA: [{}]})

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
    }

    await to_code(config)

    assert_codegen_dependencies(fake_env, expect_ota_listener=True)
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
    expected_version = _project_version()
    assert fake_env.gateway.calls == [
        ("set_version", (expected_version,)),
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
    ]
    for call in fake_env.gateway.calls:
        assert call in fake_env.codegen.added
    for call in fake_env.text.texts[0].calls:
        assert call in fake_env.codegen.added
    assert (
        fake_env.text.texts[0],
        fake_env.text.created[0],
    ) in fake_env.codegen.registered_components
    assert ("register_component", fake_env.text.texts[0]) not in fake_env.codegen.added


async def test_to_code_wires_required_entities_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate code when optional entities are omitted."""

    fake_env = install_codegen_fakes(monkeypatch, variables={"time_id": "time:clock"})
    monkeypatch.setattr(CORE, "config", {})

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 1,
        CONF_LED_PIN: 25,
        CONF_RADIO: DEFAULT_RADIO_CONFIG,
        CONF_STALE_AFTER: FakeTimePeriod(total_milliseconds=60_000),
        CONF_TIME_ID: "time_id",
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

    assert_codegen_dependencies(fake_env, expect_ota_listener=False)
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
    expected_version = _project_version()
    assert fake_env.gateway.calls == [
        ("set_version", (expected_version,)),
        ("set_candidate_limit", (1,)),
        ("set_stale_after_ms", (60_000,)),
        ("set_led_pin", (25,)),
        ("set_time", ("time:clock",)),
        ("add_mapping", ("garage_freezer_1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage_freezer_1", "sensor:temperature")),
    ]
    for call in fake_env.gateway.calls:
        assert call in fake_env.codegen.added
    for call in fake_env.text.texts[0].calls:
        assert call in fake_env.codegen.added


async def test_to_code_normalizes_user_extra_script_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve ESPHome shorthand extra scripts when adding the prebuild hook."""

    fake_env = install_codegen_fakes(monkeypatch, variables={"time_id": "time:clock"})
    core_config: dict[str, Any] = {
        CONF_ESPHOME: {
            CONF_PLATFORMIO_OPTIONS: {
                CONF_EXTRA_SCRIPTS: "user_script.py",
            }
        }
    }
    monkeypatch.setattr(CORE, "config", core_config)

    config: dict[str, Any] = {
        CONF_ID: "gateway_id",
        CONF_CANDIDATE_LIMIT: 1,
        CONF_LED_PIN: 25,
        CONF_RADIO: DEFAULT_RADIO_CONFIG,
        CONF_STALE_AFTER: FakeTimePeriod(total_milliseconds=60_000),
        CONF_TIME_ID: "time_id",
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

    assert core_config[CONF_ESPHOME][CONF_PLATFORMIO_OPTIONS][CONF_EXTRA_SCRIPTS] == [
        "user_script.py"
    ]
    assert fake_env.codegen.platformio_options == EXPECTED_PLATFORMIO_OPTIONS


async def test_to_code_sanitizes_generated_mapping_text_id_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep legacy logical keys while generating a valid mapping text component ID."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATE_LIMIT: 1,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            **gateway_diagnostic_overrides("Sanitized ID Fixture"),
            **gateway_control_overrides("Sanitized ID Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage-freezer-1",
                    CONF_MAPPING: "Acurite-986/1R/11932",
                    CONF_TEMPERATURE: {"name": "Garage Freezer Temperature"},
                }
            ],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

    await to_code(config)

    mapping_text_id = fake_env.text.created[0][CONF_ID]
    assert getattr(mapping_text_id, "id") == "garage_freezer_1_mapping"
    assert fake_env.text.texts[0].calls == [
        ("set_parent", (fake_env.gateway,)),
        ("set_logical_key", ("garage-freezer-1",)),
        ("set_initial_value", ("Acurite-986/1R/11932",)),
    ]
    expected_gateway_calls = [
        ("add_mapping", ("garage-freezer-1", "Acurite-986/1R/11932")),
        ("set_temperature_sensor", ("garage-freezer-1", "sensor:Garage Freezer Temperature")),
    ]
    for call in expected_gateway_calls:
        assert call in fake_env.gateway.calls


def test_config_schema_generates_candidate_sensors_from_limit() -> None:
    """Create default candidate text sensors when only a limit is configured."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
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
            CONF_DISABLED_BY_DEFAULT: candidate[CONF_DISABLED_BY_DEFAULT],
            "icon": candidate["icon"],
        }
        for candidate in config[CONF_CANDIDATES]
    ] == [
        {
            "name": "Candidate 1",
            "entity_category": "diagnostic",
            CONF_DISABLED_BY_DEFAULT: False,
            "icon": "mdi:radio-tower",
        },
        {
            "name": "Candidate 2",
            "entity_category": "diagnostic",
            CONF_DISABLED_BY_DEFAULT: False,
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
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATES: [],
            **gateway_control_overrides("Default Diagnostics Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Default Diagnostics Fixture", ["temperature"])
            ],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

    await to_code(config)

    assert [_entity_name_and_category(config[key]) for key, _ in GATEWAY_DIAGNOSTIC_DEFAULTS] == [
        (name, "diagnostic") for _, name in GATEWAY_DIAGNOSTIC_DEFAULTS
    ]
    assert all(
        config[key][CONF_DISABLED_BY_DEFAULT] is True for key, _ in GATEWAY_DIAGNOSTIC_DEFAULTS
    )
    assert _entity_name_and_category(fake_env.text_sensor.created[0]) == (
        "Last Packet",
        "diagnostic",
    )
    assert fake_env.text_sensor.created[0][CONF_DISABLED_BY_DEFAULT] is True
    assert [_entity_name_and_category(entity) for entity in fake_env.sensor.created[-3:]] == [
        ("Packet Count", "diagnostic"),
        ("Known Packet Count", "diagnostic"),
        ("Unknown Packet Count", "diagnostic"),
    ]
    assert all(entity[CONF_DISABLED_BY_DEFAULT] is True for entity in fake_env.sensor.created[-3:])
    assert fake_env.binary_sensor.created == []


async def test_config_schema_generates_default_gateway_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create default gateway config controls when omitted."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATES: [],
            **gateway_diagnostic_overrides("Default Controls Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Default Controls Fixture", ["temperature"])
            ],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

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
            **REQUIRED_TIME_CONFIG,
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


def test_config_schema_accepts_valid_custom_hardware_profile() -> None:
    """Accept supported custom LED, radio frequency, and GPIO overrides."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_LED_PIN: 2,
            CONF_RADIO: {
                CONF_FREQUENCY: 315,
                CONF_PINS: {
                    CONF_DIO0: 26,
                    CONF_DIO1: 35,
                    CONF_DIO2: 34,
                    CONF_RST: 14,
                    CONF_CS: 18,
                    CONF_SCK: 5,
                    CONF_MISO: 19,
                    CONF_MOSI: 27,
                },
            },
            **gateway_diagnostic_overrides("Custom Hardware Fixture"),
            **gateway_control_overrides("Custom Hardware Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config("Custom Hardware Fixture", ["temperature"])
            ],
        }
    )

    assert config[CONF_LED_PIN] == 2
    assert config[CONF_RADIO][CONF_FREQUENCY] == 315
    assert config[CONF_RADIO][CONF_PINS][CONF_DIO1] == 35


@pytest.mark.parametrize(
    "override",
    [
        {CONF_LED_PIN: 999},
        {CONF_LED_PIN: 35},
        {CONF_LED_PIN: 6},
        {CONF_LED_PIN: -1},
        {CONF_RADIO: {CONF_FREQUENCY: 0}},
        {CONF_RADIO: {CONF_FREQUENCY: -1}},
        {CONF_RADIO: {CONF_PINS: {CONF_DIO0: 999}}},
        {CONF_RADIO: {CONF_PINS: {CONF_DIO0: -1}}},
        {CONF_RADIO: {CONF_PINS: {CONF_DIO0: 6}}},
        {CONF_RADIO: {CONF_PINS: {CONF_CS: 35}}},
        {CONF_RADIO: {CONF_PINS: {CONF_CS: 6}}},
        {CONF_RADIO: {CONF_PINS: {CONF_RST: 34}}},
        {CONF_RADIO: {CONF_PINS: {CONF_SCK: 39}}},
        {CONF_RADIO: {CONF_PINS: {CONF_MOSI: 36}}},
    ],
)
def test_config_schema_rejects_invalid_hardware_profile(override: dict[str, Any]) -> None:
    """Reject impossible GPIO and frequency values before build flag generation."""

    with pytest.raises(cv.Invalid):
        CONFIG_SCHEMA(
            {
                CONF_ID: "gateway_id",
                **REQUIRED_TIME_CONFIG,
                **override,
                **gateway_diagnostic_overrides("Invalid Hardware Fixture"),
                **gateway_control_overrides("Invalid Hardware Fixture"),
                CONF_KNOWN_SENSORS: [
                    compact_known_sensor_config("Invalid Hardware Fixture", ["temperature"])
                ],
            }
        )


def test_validate_radio_module_accepts_build_flag_suffixes() -> None:
    """Accept non-default rtl_433_ESP radio module build flag suffixes."""

    assert _validate_radio_module("cc1101") == "CC1101"


def test_validate_radio_module_rejects_unsafe_build_flag_suffixes() -> None:
    """Reject radio module names that cannot safely form a build flag."""

    with pytest.raises(cv.Invalid):
        _validate_radio_module("RF-CC1101")


def test_validate_radio_module_rejects_unsupported_modules() -> None:
    """Reject unknown radio module names before build flag generation."""

    with pytest.raises(cv.Invalid, match="Unsupported rtl_433_ESP radio module 'BANANA'"):
        _validate_radio_module("banana")


async def test_to_code_uses_configured_radio_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate RF module build flags from configured non-default modules."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            CONF_RADIO: {CONF_MODULE: "cc1101"},
            **gateway_diagnostic_overrides("Radio Fixture"),
            **gateway_control_overrides("Radio Fixture"),
            CONF_KNOWN_SENSORS: [compact_known_sensor_config("Radio Fixture", ["temperature"])],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

    await to_code(config)

    assert config[CONF_RADIO][CONF_MODULE] == "CC1101"
    assert "-DRF_CC1101" in fake_env.codegen.build_flags
    assert "-DRF_SX1278" not in fake_env.codegen.build_flags
    assert "-DRF_MODULE_GDO0=26" in fake_env.codegen.build_flags
    assert "-DRF_MODULE_GDO2=34" in fake_env.codegen.build_flags
    assert "-DRF_MODULE_DIO0=26" not in fake_env.codegen.build_flags
    assert "-DRF_MODULE_DIO2=34" not in fake_env.codegen.build_flags


def test_config_schema_expands_compact_known_sensor_entities() -> None:
    """Expand compact known sensor entries into generated entity configs."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Compact Fixture"),
            **gateway_control_overrides("Compact Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    "name": "Garage Combo Fridge",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: [
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
    assert "entity_category" not in entry[CONF_HUMIDITY]
    assert entry[CONF_BATTERY]["entity_category"] == "diagnostic"
    assert entry[CONF_RSSI]["entity_category"] == "diagnostic"
    assert entry[CONF_STALE]["entity_category"] == "diagnostic"
    assert entry[CONF_LAST_UPDATED]["entity_category"] == "diagnostic"
    assert entry[CONF_RSSI][CONF_DISABLED_BY_DEFAULT] is True
    assert entry[CONF_LAST_UPDATED][CONF_DISABLED_BY_DEFAULT] is True


def test_config_schema_leaves_name_only_compact_known_entities_on_gateway() -> None:
    """Leave name-only compact known sensor entities on the main device."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Device Fixture"),
            **gateway_control_overrides("Device Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    "name": "Device Fixture Fridge",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: [
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

    for entity in (
        CONF_TEMPERATURE,
        CONF_HUMIDITY,
        CONF_BATTERY,
        CONF_RSSI,
        CONF_STALE,
        CONF_LAST_UPDATED,
    ):
        assert CONF_DEVICE_ID not in entry[entity]


def test_config_schema_uses_explicit_known_sensor_device_id() -> None:
    """Use an explicit known sensor device ID instead of deriving one from the key."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Explicit Device Fixture"),
            **gateway_control_overrides("Explicit Device Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_DEVICE_ID: "combo_fridge_device",
                    "name": "Explicit Device Fixture Fridge",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: [
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

    for entity in (
        CONF_TEMPERATURE,
        CONF_HUMIDITY,
        CONF_BATTERY,
        CONF_RSSI,
        CONF_STALE,
        CONF_LAST_UPDATED,
    ):
        assert entry[entity][CONF_DEVICE_ID].id == "combo_fridge_device"


def test_config_schema_uses_device_name_when_compact_name_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the linked ESPHome device name when compact known sensor name is omitted."""

    monkeypatch.setattr(
        CORE,
        "config",
        {
            CONF_ESPHOME: {
                CONF_DEVICES: [
                    {
                        CONF_ID: "combo_fridge_device",
                        "name": "Device Name Fixture Fridge",
                    }
                ]
            }
        },
    )

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Device Name Fixture"),
            **gateway_control_overrides("Device Name Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_DEVICE_ID: "combo_fridge_device",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: [
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

    assert entry["name"] == "Device Name Fixture Fridge"
    assert entry[CONF_TEMPERATURE]["name"] == "Device Name Fixture Fridge Temperature"
    assert entry[CONF_HUMIDITY]["name"] == "Device Name Fixture Fridge Humidity"
    assert entry[CONF_BATTERY]["name"] == "Device Name Fixture Fridge Battery"


def test_config_schema_preserves_explicit_compact_name_matching_device_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve explicit compact names that match the linked device ID."""

    monkeypatch.setattr(
        CORE,
        "config",
        {
            CONF_ESPHOME: {
                CONF_DEVICES: [
                    {
                        CONF_ID: "combo_fridge_device",
                        "name": "Explicit Name Fixture Fridge",
                    }
                ]
            }
        },
    )

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Explicit Name Fixture"),
            **gateway_control_overrides("Explicit Name Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_NAME: "combo_fridge_device",
                    CONF_DEVICE_ID: "combo_fridge_device",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: ["temperature"],
                }
            ],
        }
    )

    entry = config[CONF_KNOWN_SENSORS][0]

    assert entry["name"] == "combo_fridge_device"
    assert entry[CONF_TEMPERATURE]["name"] == "combo_fridge_device Temperature"


def test_final_validation_uses_runtime_config_to_resolve_compact_device_name() -> None:
    """Use ESPHome final-validation config to resolve omitted compact names."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Runtime Device Fixture"),
            **gateway_control_overrides("Runtime Device Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_DEVICE_ID: "runtime_fridge_device",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: ["temperature"],
                }
            ],
        }
    )
    token = fv.full_config.set(
        FakeFinalValidateConfig(
            {
                "runtime_fridge_device": {
                    CONF_ID: "runtime_fridge_device",
                    "name": "Runtime Device Fridge",
                }
            }
        )
    )
    try:
        rtl433_native.FINAL_VALIDATE_SCHEMA(config)
    finally:
        fv.full_config.reset(token)

    entry = config[CONF_KNOWN_SENSORS][0]

    assert entry["name"] == "Runtime Device Fridge"
    assert entry[CONF_TEMPERATURE]["name"] == "Runtime Device Fridge Temperature"


def test_final_validation_rejects_unresolved_compact_device_name() -> None:
    """Reject compact known sensors that omit name and reference an unknown device."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Unknown Device Fixture"),
            **gateway_control_overrides("Unknown Device Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_DEVICE_ID: "missing_fridge_device",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: ["temperature"],
                }
            ],
        }
    )
    token = fv.full_config.set(FakeFinalValidateConfig({}))
    try:
        with pytest.raises(cv.Invalid, match="missing_fridge_device"):
            rtl433_native.FINAL_VALIDATE_SCHEMA(config)
    finally:
        fv.full_config.reset(token)


async def test_to_code_rejects_compact_device_without_name_in_core_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject compact device IDs that match a nameless CORE config device."""

    monkeypatch.setattr(
        CORE,
        "config",
        {
            CONF_ESPHOME: {
                CONF_DEVICES: [
                    {
                        CONF_ID: "nameless_fridge_device",
                    }
                ]
            }
        },
    )
    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            **gateway_diagnostic_overrides("Nameless Device Fixture"),
            **gateway_control_overrides("Nameless Device Fixture"),
            CONF_KNOWN_SENSORS: [
                {
                    CONF_KEY: "garage_combo_fridge",
                    CONF_DEVICE_ID: "nameless_fridge_device",
                    CONF_MAPPING: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203",
                    CONF_ENTITIES: ["temperature"],
                }
            ],
        }
    )

    with pytest.raises(cv.Invalid, match="nameless_fridge_device"):
        await to_code(config)


async def test_compact_known_sensor_mapping_entity_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip the mapping text entity when compact config omits mapping from entities."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATE_LIMIT: 1,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            **gateway_diagnostic_overrides("No Mapping Fixture"),
            **gateway_control_overrides("No Mapping Fixture"),
            CONF_KNOWN_SENSORS: [compact_known_sensor_config("Garage Freezer 1", ["temperature"])],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

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
            **REQUIRED_TIME_CONFIG,
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
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

    await to_code(config)

    assert [text_config["name"] for text_config in fake_env.text.created] == [
        "Garage Mapping Fixture Mapping"
    ]
    assert CONF_DEVICE_ID not in fake_env.text.created[0]


async def test_compact_known_sensor_entities_keep_mapping_text_on_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generate known sensor entities on a sub-device while mapping text stays on gateway."""

    config = CONFIG_SCHEMA(
        {
            CONF_ID: "gateway_id",
            **REQUIRED_TIME_CONFIG,
            CONF_CANDIDATE_LIMIT: 1,
            CONF_CANDIDATES: [],
            CONF_STALE_AFTER: "1min",
            **gateway_diagnostic_overrides("Mapping Device Fixture"),
            **gateway_control_overrides("Mapping Device Fixture"),
            CONF_KNOWN_SENSORS: [
                compact_known_sensor_config(
                    "Mapping Device Fixture Freezer",
                    ["temperature", "battery", "rssi", "stale", "last_updated", "mapping"],
                    device_id="garage_freezer_1_device",
                )
            ],
        }
    )
    fake_env = install_codegen_fakes_for_config(monkeypatch, config)

    await to_code(config)

    created_entity_configs = fake_env.sensor.created[:3] + fake_env.binary_sensor.created[:2]
    for entity_config in created_entity_configs:
        assert entity_config[CONF_DEVICE_ID].id == "garage_freezer_1_device"
    assert CONF_DEVICE_ID not in fake_env.text.created[0]


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
