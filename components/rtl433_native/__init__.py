"""ESPHome codegen for the native rtl_433 gateway component."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from esphome import automation
import esphome.codegen as cg
from esphome.components import binary_sensor, button, sensor, switch, text, text_sensor, time
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.const import (
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_DISABLED_BY_DEFAULT,
    CONF_ENTITY_CATEGORY,
    CONF_ESPHOME,
    CONF_ID,
    CONF_NAME,
    CONF_OTA,
    CONF_PLATFORMIO_OPTIONS,
)
from esphome.core import CORE, Define, ID

AUTO_LOAD = [
    "binary_sensor",
    "button",
    "json",
    "sensor",
    "switch",
    "text",
    "text_sensor",
    "time",
]
CODEOWNERS = ["@Snuffy2"]

CONF_CANDIDATE_LIMIT = "candidate_limit"
CONF_CANDIDATES = "candidates"
CONF_BATTERY = "battery"
CONF_CLEAR_CANDIDATES_BUTTON = "clear_candidates_button"
CONF_DISCOVERY_ENABLED = "discovery_enabled"
CONF_DISCOVERY_MODE = "discovery_mode"
CONF_ENTITIES = "entities"
CONF_HUMIDITY = "humidity"
CONF_KEY = "key"
CONF_KNOWN_SENSORS = "known_sensors"
CONF_KNOWN_PACKET_COUNT = "known_packet_count"
CONF_LAST_PACKET = "last_packet"
CONF_LAST_UPDATED = "last_updated"
CONF_LED_PIN = "led_pin"
CONF_MAPPING = "mapping"
CONF_PACKET_COUNT = "packet_count"
CONF_PINS = "pins"
CONF_RADIO = "radio"
CONF_RSSI = "rssi"
CONF_CS = "cs"
CONF_DIO0 = "dio0"
CONF_DIO1 = "dio1"
CONF_DIO2 = "dio2"
CONF_FREQUENCY = "frequency"
CONF_MISO = "miso"
CONF_MODULE = "module"
CONF_MOSI = "mosi"
CONF_RST = "rst"
CONF_SCK = "sck"
CONF_STALE = "stale"
CONF_STALE_AFTER = "stale_after"
CONF_STATUS_BUTTON = "status_button"
CONF_TEMPERATURE = "temperature"
CONF_TIME_ID = "time_id"
CONF_UNKNOWN_PACKET_COUNT = "unknown_packet_count"

ENTITY_MAPPING = CONF_MAPPING
_REFRESH_NAME_FROM_DEVICE = "_refresh_name_from_device"

rtl433_native_ns = cg.esphome_ns.namespace("rtl433_native")
Gateway = rtl433_native_ns.class_("Gateway", cg.Component)
MappingText = rtl433_native_ns.class_("MappingText", text.Text, cg.Component)
DiscoverySwitch = rtl433_native_ns.class_("DiscoverySwitch", switch.Switch, cg.Component)
ClearCandidatesButton = rtl433_native_ns.class_("ClearCandidatesButton", button.Button)
StatusButton = rtl433_native_ns.class_("StatusButton", button.Button)
StatusAction = rtl433_native_ns.class_("StatusAction", automation.Action)
StopAction = rtl433_native_ns.class_("StopAction", automation.Action)
ClearCandidatesAction = rtl433_native_ns.class_("ClearCandidatesAction", automation.Action)

UINT32_MAX_MILLISECONDS = 4_294_967_295
ESP32_GPIO_MAX = 39
ESP32_OUTPUT_GPIO_MAX = 33
MAPPING_TEXT_MAX_LENGTH = 240
MAPPING_TEXT_MIN_LENGTH = 3
ESP32_FLASH_GPIO_RANGE = range(6, 12)
ARDUINO_NETWORK_INCLUDE_FLAG = (
    '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
)
LEDC_COMPAT_INCLUDE_FLAG = "-include src/esphome/components/rtl433_native/ledc_compat.h"
RTL433_ESP_PREBUILD_SCRIPT = (
    f"pre:{Path(__file__).resolve().parents[2] / 'scripts/platformio/rtl433_esp_prebuild.py'}"
)
RTL433_NATIVE_LIBRARIES = (
    ("rtl_433_ESP", None, "https://github.com/NorthernMan54/rtl_433_ESP.git#v0.5.0"),
    ("RadioLib", "^7.2.1", None),
    ("Networking", None, None),
    ("SPI", None, None),
    ("EEPROM", None, None),
)
CONF_EXTRA_SCRIPTS = "extra_scripts"
DEFAULT_RADIO_MODULE = "SX1278"
SUPPORTED_RADIO_MODULES = frozenset({"CC1101", "SX1276", "SX1278"})
DEFAULT_RADIO_FREQUENCY = 433.92
DEFAULT_RADIO_PINS = {
    CONF_DIO0: 26,
    CONF_DIO1: 35,
    CONF_DIO2: 34,
    CONF_RST: 14,
    CONF_CS: 18,
    CONF_SCK: 5,
    CONF_MISO: 19,
    CONF_MOSI: 27,
}
RADIO_PIN_BUILD_FLAGS: tuple[tuple[str, str], ...] = (
    (CONF_DIO0, "DIO0"),
    (CONF_DIO1, "DIO1"),
    (CONF_DIO2, "DIO2"),
    (CONF_RST, "RST"),
    (CONF_CS, "CS"),
    (CONF_SCK, "SCK"),
    (CONF_MISO, "MISO"),
    (CONF_MOSI, "MOSI"),
)
CC1101_PIN_BUILD_FLAGS: tuple[tuple[str, str], ...] = (
    (CONF_DIO0, "GDO0"),
    (CONF_DIO2, "GDO2"),
    (CONF_CS, "CS"),
    (CONF_SCK, "SCK"),
    (CONF_MISO, "MISO"),
    (CONF_MOSI, "MOSI"),
)


def _validate_esp32_gpio(value: int) -> int:
    """Reject ESP32 GPIO numbers reserved for integrated flash."""

    if value in ESP32_FLASH_GPIO_RANGE:
        raise cv.Invalid(f"GPIO {value} is reserved for ESP32 flash")
    return value


DEFAULT_RADIO_CONFIG = {
    CONF_MODULE: DEFAULT_RADIO_MODULE,
    CONF_FREQUENCY: DEFAULT_RADIO_FREQUENCY,
    CONF_PINS: DEFAULT_RADIO_PINS,
}
RADIO_INPUT_PINS = frozenset({CONF_DIO0, CONF_DIO1, CONF_DIO2, CONF_MISO})
RADIO_PINS_SCHEMA = cv.Schema(
    {
        cv.Optional(
            pin_key,
            default=DEFAULT_RADIO_PINS[pin_key],
        ): cv.All(
            cv.int_range(
                min=0,
                max=ESP32_GPIO_MAX if pin_key in RADIO_INPUT_PINS else ESP32_OUTPUT_GPIO_MAX,
            ),
            _validate_esp32_gpio,
        )
        for pin_key, _ in RADIO_PIN_BUILD_FLAGS
    }
)
KNOWN_SENSOR_ENTITIES = (
    CONF_TEMPERATURE,
    CONF_HUMIDITY,
    CONF_BATTERY,
    CONF_RSSI,
    CONF_STALE,
    CONF_LAST_UPDATED,
    ENTITY_MAPPING,
)
MAPPING_TEXT_ID_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z_]+")
KEY_SCHEMA = cv.All(cv.string_strict, cv.Length(min=1))


def _validate_known_sensor_keys(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure logical sensor keys are unique."""

    seen: set[str] = set()
    for entry in value:
        key_value = entry[CONF_KEY]
        if key_value in seen:
            raise cv.Invalid(f"Duplicate known sensor key '{key_value}'")
        seen.add(key_value)
    return value


def _validate_mapping_text_ids(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure generated mapping text entity IDs are unique."""

    seen: dict[str, str] = {}
    for entry in value:
        if not _entry_has_mapping_text(entry):
            continue
        mapping_text_id = _mapping_text_id(entry)
        if mapping_text_id in seen:
            raise cv.Invalid(
                "Known sensor keys "
                f"'{seen[mapping_text_id]}' and '{entry[CONF_KEY]}' generate duplicate "
                f"mapping text ID '{mapping_text_id}'"
            )
        seen[mapping_text_id] = entry[CONF_KEY]
    return value


def _validate_known_sensor_entities(value: list[str]) -> list[str]:
    """Ensure compact known sensor entity names are unique and include temperature."""

    seen: set[str] = set()
    for entity in value:
        if entity in seen:
            raise cv.Invalid(f"Duplicate known sensor entity '{entity}'")
        seen.add(entity)
    if CONF_TEMPERATURE not in seen:
        raise cv.Invalid("Compact known sensor entries must include temperature")
    return value


def _validate_sensor_key(value: Any) -> str:
    """Validate a rtl_433 sensor key in model/channel/id format."""

    sensor_key = str(cv.string_strict(value))
    parts = [part.strip() for part in sensor_key.split("/")]
    if len(parts) != 3 or any(part == "" for part in parts):
        raise cv.Invalid("Expected sensor key in model/channel/id format")
    return "/".join(parts)


def _validate_mapping(value: Any) -> str:
    """Validate a semicolon-delimited rtl_433 mapping string."""

    mapping_value = str(cv.string_strict(value)).strip()
    if mapping_value == "":
        raise cv.Invalid("Expected at least one sensor key in model/channel/id format")
    sensor_keys = [sensor_key.strip() for sensor_key in mapping_value.split(";")]
    return ";".join(_validate_sensor_key(sensor_key) for sensor_key in sensor_keys)


def _validate_mapping_text_lengths(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure generated mapping text values fit the runtime text storage."""

    for entry in value:
        if _entry_has_mapping_text(entry) and len(entry[CONF_MAPPING]) > MAPPING_TEXT_MAX_LENGTH:
            raise cv.Invalid(
                f"Mapping string exceeds {MAPPING_TEXT_MAX_LENGTH} characters: "
                f"{entry[CONF_MAPPING]}"
            )
    return value


def _validate_stale_after(value: Any) -> Any:
    """Validate stale duration fits the C++ millisecond storage type."""

    result = cv.positive_time_period_milliseconds(value)
    if result.total_milliseconds > UINT32_MAX_MILLISECONDS:
        raise cv.Invalid(f"stale_after exceeds uint32_t limit: {result.total_milliseconds}ms")
    return result


def _validate_radio_module(value: Any) -> str:
    """Validate and normalize an rtl_433_ESP radio module build flag suffix."""

    module = str(cv.validate_id_name(value)).upper()
    if module not in SUPPORTED_RADIO_MODULES:
        supported = ", ".join(sorted(SUPPORTED_RADIO_MODULES))
        raise cv.Invalid(
            f"Unsupported rtl_433_ESP radio module '{module}'. Expected one of: {supported}"
        )
    return module


def _add_default_candidates(config: dict[str, Any]) -> dict[str, Any]:
    """Create default candidate text sensors from the configured limit."""

    if CONF_CANDIDATES not in config:
        component_id = getattr(config[CONF_ID], "id", str(config[CONF_ID]))
        config[CONF_CANDIDATES] = [
            {
                CONF_ID: ID(
                    f"{component_id}_candidate_{index + 1}",
                    is_declaration=True,
                    type=text_sensor.TextSensor,
                ),
                "name": f"Candidate {index + 1}",
                "entity_category": "diagnostic",
                CONF_DISABLED_BY_DEFAULT: False,
                "icon": "mdi:radio-tower",
            }
            for index in range(config[CONF_CANDIDATE_LIMIT])
        ]
    return config


def _mapping_text_name(entry: dict[str, Any]) -> str:
    """Return the generated mapping text entity name for a known sensor."""

    if CONF_NAME in entry:
        return f"{entry[CONF_NAME]} Mapping"
    return f"{entry[CONF_TEMPERATURE]['name']} Mapping"


def _mapping_text_id_fragment(logical_key: str) -> str:
    """Return a C++ ID-safe fragment for a known sensor mapping text entity."""

    try:
        return str(cv.validate_id_name(logical_key))
    except cv.Invalid:
        sanitized_key = MAPPING_TEXT_ID_UNSAFE_CHARS.sub("_", logical_key.strip()).strip("_")
        if sanitized_key == "":
            raise cv.Invalid("Known sensor key must generate a non-empty mapping text ID")
        if sanitized_key[0].isdigit():
            sanitized_key = f"sensor_{sanitized_key}"
        try:
            return str(cv.validate_id_name(sanitized_key))
        except cv.Invalid as err:
            raise cv.Invalid(
                f"Known sensor key '{logical_key}' cannot generate a valid mapping text ID"
            ) from err


def _mapping_text_id(entry: dict[str, Any]) -> str:
    """Return the generated ESPHome ID for a known sensor mapping text entity."""

    return f"{_mapping_text_id_fragment(entry[CONF_KEY])}_mapping"


def _id_value(value: Any) -> str:
    """Return the string value for an ESPHome ID or raw ID string."""

    return str(getattr(value, "id", value))


def _device_name_for_id(device_id: Any, config: dict[str, Any] | None = None) -> str | None:
    """Return the configured ESPHome device name for a device ID."""

    full_config = CORE.config if config is None else config
    if full_config is None:
        return None
    if hasattr(full_config, "get_path_for_id") and hasattr(full_config, "get_config_for_path"):
        try:
            device_config = full_config.get_config_for_path(
                full_config.get_path_for_id(device_id)[:-1]
            )
        except KeyError:
            return None
        if isinstance(device_config, dict) and CONF_NAME in device_config:
            return str(device_config[CONF_NAME])
        return None
    for device in full_config.get(CONF_ESPHOME, {}).get(CONF_DEVICES, []):
        if _id_value(device.get(CONF_ID)) == _id_value(device_id):
            if CONF_NAME not in device:
                return None
            return str(device[CONF_NAME])
    return None


def _known_sensor_name(entry: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    """Return the known sensor base name from entry config or linked device."""

    if CONF_NAME in entry:
        return str(entry[CONF_NAME])
    if CONF_DEVICE_ID in entry:
        device_name = _device_name_for_id(entry[CONF_DEVICE_ID], config)
        if device_name is not None:
            return device_name
        return _id_value(entry[CONF_DEVICE_ID])
    raise cv.Invalid("Compact known sensor entries require name or a device_id with a device name")


def _set_compact_sensor_name(entry: dict[str, Any], name: str) -> None:
    """Apply a compact known sensor base name to generated entity configs."""

    entry[CONF_NAME] = name
    for entity in entry.get(CONF_ENTITIES, []):
        if entity != ENTITY_MAPPING and entity in entry:
            entry[entity][CONF_NAME] = f"{name} {_entity_title(entity)}"


def _entity_title(entity: str) -> str:
    """Return the generated title suffix for a known sensor entity type."""

    if entity == CONF_RSSI:
        return "RSSI"
    return entity.replace("_", " ").title()


def _compact_entity_config(name: str, entity: str, device_id: Any | None) -> dict[str, Any]:
    """Return the generated entity config for a compact known sensor entity."""

    entity_config: dict[str, Any] = {CONF_NAME: f"{name} {_entity_title(entity)}"}
    if device_id is not None:
        entity_config[CONF_DEVICE_ID] = device_id
    if entity not in (CONF_TEMPERATURE, CONF_HUMIDITY):
        entity_config[CONF_ENTITY_CATEGORY] = "diagnostic"
    if entity in (CONF_RSSI, CONF_LAST_UPDATED):
        entity_config[CONF_DISABLED_BY_DEFAULT] = True
    return entity_config


def _add_generated_component_count(extra_count: int) -> None:
    """Increase ESPHome's static component capacity for generated components."""

    if extra_count == 0:
        return

    for define in tuple(CORE.defines):
        if define.name != "ESPHOME_COMPONENT_COUNT":
            continue

        CORE.defines.remove(define)
        CORE.add_define(Define("ESPHOME_COMPONENT_COUNT", int(str(define.value)) + extra_count))
        return


def _expand_compact_sensor_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Expand a compact known sensor entry into the verbose schema shape."""

    name_was_omitted = CONF_NAME not in entry
    name = _known_sensor_name(entry)
    device_id = entry.get(CONF_DEVICE_ID)
    for entity in entry[CONF_ENTITIES]:
        if entity != ENTITY_MAPPING:
            entry[entity] = _compact_entity_config(name, entity, device_id)
    entry[CONF_NAME] = name
    if name_was_omitted and device_id is not None:
        entry[_REFRESH_NAME_FROM_DEVICE] = True
    return entry


def _refresh_compact_device_names(
    config: dict[str, Any], full_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Refresh compact known sensor names from linked ESPHome device names."""

    for entry in config.get(CONF_KNOWN_SENSORS, []):
        if CONF_ENTITIES not in entry or CONF_DEVICE_ID not in entry:
            continue
        if not entry.pop(_REFRESH_NAME_FROM_DEVICE, False):
            continue
        placeholder_name = _id_value(entry[CONF_DEVICE_ID])
        device_name = _device_name_for_id(entry[CONF_DEVICE_ID], full_config)
        if device_name is None:
            raise cv.Invalid(
                f"Known sensor device_id '{placeholder_name}' must reference an "
                "esphome.devices entry with a name"
            )
        _set_compact_sensor_name(entry, device_name)
    return config


def _final_validate_config(config: dict[str, Any]) -> None:
    """Refresh device-linked names after ESPHome has the full config."""

    _refresh_compact_device_names(config, fv.full_config.get())


def _apply_known_sensor_device_id(entry: dict[str, Any]) -> dict[str, Any]:
    """Apply a known sensor's explicit device ID to generated entity configs."""

    device_id = entry.get(CONF_DEVICE_ID)
    if device_id is None:
        return entry
    for entity in KNOWN_SENSOR_ENTITIES:
        if entity == ENTITY_MAPPING or entity not in entry:
            continue
        entry[entity].setdefault(CONF_DEVICE_ID, device_id)
    return entry


SENSOR_ENTRY_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_KEY): KEY_SCHEMA,
        cv.Optional(CONF_DEVICE_ID): cv.sub_device_id,
        cv.Required(CONF_MAPPING): _validate_mapping,
        cv.Required(CONF_TEMPERATURE): sensor.sensor_schema(
            unit_of_measurement="°F",
            accuracy_decimals=2,
            device_class="temperature",
            state_class="measurement",
        ),
        cv.Optional(CONF_HUMIDITY): sensor.sensor_schema(
            unit_of_measurement="%",
            accuracy_decimals=0,
            device_class="humidity",
            state_class="measurement",
        ),
        cv.Optional(CONF_BATTERY): binary_sensor.binary_sensor_schema(device_class="battery"),
        cv.Optional(CONF_RSSI): sensor.sensor_schema(
            unit_of_measurement="dB",
            accuracy_decimals=0,
            device_class="signal_strength",
            state_class="measurement",
        ),
        cv.Optional(CONF_STALE): binary_sensor.binary_sensor_schema(device_class="problem"),
        cv.Optional(CONF_LAST_UPDATED): sensor.sensor_schema(
            accuracy_decimals=0,
            device_class="timestamp",
        ),
    }
)

COMPACT_SENSOR_ENTRY_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.Required(CONF_KEY): KEY_SCHEMA,
            cv.Optional(CONF_NAME): cv.string_strict,
            cv.Optional(CONF_DEVICE_ID): cv.sub_device_id,
            cv.Required(CONF_MAPPING): _validate_mapping,
            cv.Required(CONF_ENTITIES): cv.All(
                cv.ensure_list(cv.one_of(*KNOWN_SENSOR_ENTITIES, lower=True)),
                _validate_known_sensor_entities,
            ),
        }
    ),
    _expand_compact_sensor_entry,
    SENSOR_ENTRY_SCHEMA.extend(
        {
            cv.Required(CONF_NAME): cv.string_strict,
            cv.Optional(CONF_DEVICE_ID): cv.sub_device_id,
            cv.Optional(_REFRESH_NAME_FROM_DEVICE): cv.boolean,
            cv.Required(CONF_ENTITIES): cv.ensure_list(cv.one_of(*KNOWN_SENSOR_ENTITIES)),
        }
    ),
    _apply_known_sensor_device_id,
)

KNOWN_SENSOR_ENTRY_SCHEMA = cv.Any(
    COMPACT_SENSOR_ENTRY_SCHEMA,
    cv.All(SENSOR_ENTRY_SCHEMA, _apply_known_sensor_device_id),
)

RADIO_SCHEMA = cv.Schema(
    {
        cv.Optional(CONF_MODULE, default=DEFAULT_RADIO_MODULE): _validate_radio_module,
        cv.Optional(CONF_FREQUENCY, default=DEFAULT_RADIO_FREQUENCY): cv.positive_not_null_float,
        cv.Optional(CONF_PINS, default=DEFAULT_RADIO_PINS): RADIO_PINS_SCHEMA,
    }
)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(Gateway),
            cv.Required(CONF_KNOWN_SENSORS): cv.All(
                cv.ensure_list(KNOWN_SENSOR_ENTRY_SCHEMA),
                cv.Length(min=1),
                _validate_known_sensor_keys,
                _validate_mapping_text_ids,
                _validate_mapping_text_lengths,
            ),
            cv.Optional(CONF_CANDIDATE_LIMIT, default=10): cv.int_range(min=1, max=20),
            cv.Optional(CONF_LED_PIN, default=25): cv.All(
                cv.int_range(min=0, max=ESP32_OUTPUT_GPIO_MAX),
                _validate_esp32_gpio,
            ),
            cv.Optional(CONF_RADIO, default=DEFAULT_RADIO_CONFIG): RADIO_SCHEMA,
            cv.Optional(CONF_STALE_AFTER, default="1h"): _validate_stale_after,
            cv.Optional(CONF_TIME_ID): cv.use_id(time.RealTimeClock),
            cv.Optional(CONF_CANDIDATES): cv.All(
                cv.ensure_list(text_sensor.text_sensor_schema(icon="mdi:radio-tower")),
                cv.Length(max=20),
            ),
            cv.Optional(
                CONF_LAST_PACKET,
                default={
                    "name": "Last Packet",
                    "entity_category": "diagnostic",
                    CONF_DISABLED_BY_DEFAULT: True,
                },
            ): text_sensor.text_sensor_schema(icon="mdi:radio"),
            cv.Optional(
                CONF_PACKET_COUNT,
                default={
                    "name": "Packet Count",
                    "entity_category": "diagnostic",
                    CONF_DISABLED_BY_DEFAULT: True,
                },
            ): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(
                CONF_KNOWN_PACKET_COUNT,
                default={
                    "name": "Known Packet Count",
                    "entity_category": "diagnostic",
                    CONF_DISABLED_BY_DEFAULT: True,
                },
            ): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(
                CONF_UNKNOWN_PACKET_COUNT,
                default={
                    "name": "Unknown Packet Count",
                    "entity_category": "diagnostic",
                    CONF_DISABLED_BY_DEFAULT: True,
                },
            ): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(
                CONF_DISCOVERY_ENABLED,
                default={
                    "name": "Discovery Enabled",
                    "entity_category": "diagnostic",
                    CONF_DISABLED_BY_DEFAULT: True,
                },
            ): binary_sensor.binary_sensor_schema(
                # Diagnostic read-only binary sensor mirroring runtime discovery enable state.
                entity_category="diagnostic",
            ),
            cv.Optional(
                CONF_DISCOVERY_MODE,
                default={"name": "Discovery Mode", "entity_category": "config"},
            ): switch.switch_schema(
                DiscoverySwitch,
                default_restore_mode="RESTORE_DEFAULT_OFF",
                entity_category="config",
            ).extend(cv.COMPONENT_SCHEMA),
            cv.Optional(
                CONF_CLEAR_CANDIDATES_BUTTON,
                default={"name": "Clear Candidates", "entity_category": "config"},
            ): button.button_schema(ClearCandidatesButton, entity_category="config"),
            cv.Optional(
                CONF_STATUS_BUTTON,
                default={"name": "Radio Status", "entity_category": "config"},
            ): button.button_schema(StatusButton, entity_category="config"),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _add_default_candidates,
)
FINAL_VALIDATE_SCHEMA = _final_validate_config

GATEWAY_ID_SCHEMA = cv.Schema({cv.GenerateID(): cv.use_id(Gateway)})


async def to_code(config: dict[str, Any]) -> None:
    """Generate C++ for the rtl433_native component."""

    _refresh_compact_device_names(config)
    _normalize_extra_scripts_platformio_option()

    cg.add_build_flag(ARDUINO_NETWORK_INCLUDE_FLAG)
    cg.add_build_flag(LEDC_COMPAT_INCLUDE_FLAG)
    if CONF_OTA in (CORE.config or {}):
        cg.add_define("USE_OTA_STATE_LISTENER")
    cg.add_platformio_option("lib_ldf_mode", "chain+")
    cg.add_platformio_option(CONF_EXTRA_SCRIPTS, [RTL433_ESP_PREBUILD_SCRIPT])
    radio_config = config[CONF_RADIO]
    radio_pins = radio_config[CONF_PINS]
    cg.add_build_flag(f"-DRF_{radio_config[CONF_MODULE]}")
    cg.add_build_flag(f"-DRF_MODULE_FREQUENCY={radio_config[CONF_FREQUENCY]:g}")
    pin_build_flags = (
        CC1101_PIN_BUILD_FLAGS if radio_config[CONF_MODULE] == "CC1101" else RADIO_PIN_BUILD_FLAGS
    )
    for pin_key, build_flag_name in pin_build_flags:
        cg.add_build_flag(f"-DRF_MODULE_{build_flag_name}={radio_pins[pin_key]}")
    for name, version, repository in RTL433_NATIVE_LIBRARIES:
        cg.add_library(name, version, repository)

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_candidate_limit(config[CONF_CANDIDATE_LIMIT]))
    cg.add(var.set_stale_after_ms(config[CONF_STALE_AFTER].total_milliseconds))
    cg.add(var.set_led_pin(config[CONF_LED_PIN]))
    if CONF_TIME_ID in config:
        time_var = await cg.get_variable(config[CONF_TIME_ID])
        cg.add(var.set_time(time_var))

    generated_component_count = 0
    for entry in config[CONF_KNOWN_SENSORS]:
        cg.add(
            var.add_mapping(
                entry[CONF_KEY],
                entry[CONF_MAPPING],
            )
        )
        if _entry_has_mapping_text(entry):
            mapping_text_id = ID(_mapping_text_id(entry), is_declaration=True, type=MappingText)
            mapping_text_config = {
                CONF_ID: mapping_text_id,
                "name": _mapping_text_name(entry),
                "entity_category": "config",
                "disabled_by_default": False,
                "mode": text.TextMode.TEXT_MODE_TEXT,
            }
            CORE.component_ids.add(mapping_text_id.id)
            mapping_text = await text.new_text(
                mapping_text_config,
                min_length=MAPPING_TEXT_MIN_LENGTH,
                max_length=MAPPING_TEXT_MAX_LENGTH,
            )
            await cg.register_component(mapping_text, mapping_text_config)
            generated_component_count += 1
            cg.add(mapping_text.set_parent(var))
            cg.add(mapping_text.set_logical_key(entry[CONF_KEY]))
            cg.add(mapping_text.set_initial_value(entry[CONF_MAPPING]))
        temperature = await sensor.new_sensor(entry[CONF_TEMPERATURE])
        cg.add(var.set_temperature_sensor(entry[CONF_KEY], temperature))
        if CONF_HUMIDITY in entry:
            humidity = await sensor.new_sensor(entry[CONF_HUMIDITY])
            cg.add(var.set_humidity_sensor(entry[CONF_KEY], humidity))
        if CONF_BATTERY in entry:
            battery = await binary_sensor.new_binary_sensor(entry[CONF_BATTERY])
            cg.add(var.set_battery_sensor(entry[CONF_KEY], battery))
        if CONF_RSSI in entry:
            rssi = await sensor.new_sensor(entry[CONF_RSSI])
            cg.add(var.set_rssi_sensor(entry[CONF_KEY], rssi))
        if CONF_STALE in entry:
            stale = await binary_sensor.new_binary_sensor(entry[CONF_STALE])
            cg.add(var.set_stale_sensor(entry[CONF_KEY], stale))
        if CONF_LAST_UPDATED in entry:
            last_updated_sensor = await sensor.new_sensor(entry[CONF_LAST_UPDATED])
            cg.add(var.set_last_updated_sensor(entry[CONF_KEY], last_updated_sensor))

    for index, candidate_config in enumerate(config[CONF_CANDIDATES]):
        candidate = await text_sensor.new_text_sensor(candidate_config)
        cg.add(var.set_candidate_text_sensor(index, candidate))

    if CONF_LAST_PACKET in config:
        last_packet_sensor = await text_sensor.new_text_sensor(config[CONF_LAST_PACKET])
        cg.add(var.set_last_packet_sensor(last_packet_sensor))
    if CONF_PACKET_COUNT in config:
        packet_count_sensor = await sensor.new_sensor(config[CONF_PACKET_COUNT])
        cg.add(var.set_packet_count_sensor(packet_count_sensor))
    if CONF_KNOWN_PACKET_COUNT in config:
        known_packet_count_sensor = await sensor.new_sensor(config[CONF_KNOWN_PACKET_COUNT])
        cg.add(var.set_known_packet_count_sensor(known_packet_count_sensor))
    if CONF_UNKNOWN_PACKET_COUNT in config:
        unknown_packet_count_sensor = await sensor.new_sensor(config[CONF_UNKNOWN_PACKET_COUNT])
        cg.add(var.set_unknown_packet_count_sensor(unknown_packet_count_sensor))
    if CONF_DISCOVERY_ENABLED in config:
        discovery_enabled_sensor = await binary_sensor.new_binary_sensor(
            config[CONF_DISCOVERY_ENABLED]
        )
        cg.add(var.set_discovery_enabled_sensor(discovery_enabled_sensor))
    _add_generated_component_count(generated_component_count)
    if CONF_DISCOVERY_MODE in config:
        discovery_mode = await switch.new_switch(config[CONF_DISCOVERY_MODE])
        await cg.register_component(discovery_mode, config[CONF_DISCOVERY_MODE])
        cg.add(discovery_mode.set_parent(var))
    if CONF_CLEAR_CANDIDATES_BUTTON in config:
        clear_candidates_button = await button.new_button(config[CONF_CLEAR_CANDIDATES_BUTTON])
        cg.add(clear_candidates_button.set_parent(var))
    if CONF_STATUS_BUTTON in config:
        status_button = await button.new_button(config[CONF_STATUS_BUTTON])
        cg.add(status_button.set_parent(var))


def _normalize_extra_scripts_platformio_option() -> None:
    """Normalize user extra scripts before ESPHome merges component scripts."""

    core_config = CORE.config
    if not isinstance(core_config, dict):
        return

    platformio_options = core_config.get(CONF_ESPHOME, {}).get(CONF_PLATFORMIO_OPTIONS)
    if not isinstance(platformio_options, dict):
        return

    extra_scripts = platformio_options.get(CONF_EXTRA_SCRIPTS)
    if isinstance(extra_scripts, str):
        platformio_options[CONF_EXTRA_SCRIPTS] = [extra_scripts]


def _entry_has_mapping_text(entry: dict[str, Any]) -> bool:
    """Return whether this known sensor should generate a mapping text entity."""

    if CONF_ENTITIES not in entry:
        return True
    return ENTITY_MAPPING in entry[CONF_ENTITIES]


@automation.register_action(
    "rtl433_native.status",
    StatusAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
    synchronous=True,
)
@automation.register_action(
    "rtl433_native.stop",
    StopAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
    synchronous=True,
)
@automation.register_action(
    "rtl433_native.clear_candidates",
    ClearCandidatesAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
    synchronous=True,
)
async def action_to_code(
    config: dict[str, Any], action_id: Any, template_arg: Any, args: Any
) -> Any:
    """Generate ESPHome automation action instances."""

    del args
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var
