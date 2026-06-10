"""ESPHome codegen for the native rtl_433 gateway component."""

from __future__ import annotations

from typing import Any

from esphome import automation
import esphome.codegen as cg
from esphome.components import binary_sensor, sensor, text, text_sensor, time
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.core import ID

AUTO_LOAD = ["binary_sensor", "json", "sensor", "text", "text_sensor", "time"]
CODEOWNERS = ["@Snuffy2"]

CONF_CANDIDATE_LIMIT = "candidate_limit"
CONF_CANDIDATES = "candidates"
CONF_BATTERY = "battery"
CONF_DISCOVERY_ENABLED = "discovery_enabled"
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
CONF_TEMPERATURE = "temperature"
CONF_TIME_ID = "time_id"
CONF_UNKNOWN_PACKET_COUNT = "unknown_packet_count"

rtl433_native_ns = cg.esphome_ns.namespace("rtl433_native")
Gateway = rtl433_native_ns.class_("Gateway", cg.Component)
MappingText = rtl433_native_ns.class_("MappingText", text.Text, cg.Component)
StatusAction = rtl433_native_ns.class_("StatusAction", automation.Action)
StopAction = rtl433_native_ns.class_("StopAction", automation.Action)
ClearCandidatesAction = rtl433_native_ns.class_("ClearCandidatesAction", automation.Action)

UINT32_MAX_MILLISECONDS = 4_294_967_295
MAPPING_TEXT_MAX_LENGTH = 240
MAPPING_TEXT_MIN_LENGTH = 3
ARDUINO_NETWORK_INCLUDE_FLAG = (
    '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
)
LEDC_COMPAT_INCLUDE_FLAG = "-include src/esphome/components/rtl433_native/ledc_compat.h"
RTL433_NATIVE_LIBRARIES = (
    ("rtl_433_ESP", None, "https://github.com/NorthernMan54/rtl_433_ESP.git#v0.3.3"),
    ("RadioLib", "6.2.0", None),
    ("Networking", None, None),
    ("SPI", None, None),
    ("EEPROM", None, None),
)
DEFAULT_RADIO_MODULE = "SX1278"
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
DEFAULT_RADIO_CONFIG = {
    CONF_MODULE: DEFAULT_RADIO_MODULE,
    CONF_FREQUENCY: DEFAULT_RADIO_FREQUENCY,
    CONF_PINS: DEFAULT_RADIO_PINS,
}


def _validate_known_sensor_keys(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure logical sensor keys are unique."""

    seen: set[str] = set()
    for entry in value:
        key_value = entry[CONF_KEY]
        if key_value in seen:
            raise cv.Invalid(f"Duplicate known sensor key '{key_value}'")
        seen.add(key_value)
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


def _validate_stale_after(value: Any) -> Any:
    """Validate stale duration fits the C++ millisecond storage type."""

    result = cv.positive_time_period_milliseconds(value)
    if result.total_milliseconds > UINT32_MAX_MILLISECONDS:
        raise cv.Invalid(f"stale_after exceeds uint32_t limit: {result.total_milliseconds}ms")
    return result


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
                "disabled_by_default": False,
                "icon": "mdi:radio-tower",
            }
            for index in range(config[CONF_CANDIDATE_LIMIT])
        ]
    return config


def _mapping_text_name(entry: dict[str, Any]) -> str:
    """Return the generated mapping text entity name for a known sensor."""

    return f"{entry[CONF_TEMPERATURE]['name']} Mapping"


SENSOR_ENTRY_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_KEY): cv.string_strict,
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

RADIO_SCHEMA = cv.Schema(
    {
        cv.Optional(CONF_MODULE, default=DEFAULT_RADIO_MODULE): cv.one_of("SX1278", upper=True),
        cv.Optional(CONF_FREQUENCY, default=DEFAULT_RADIO_FREQUENCY): cv.float_,
        cv.Optional(CONF_PINS, default=DEFAULT_RADIO_PINS): cv.Schema(
            {
                cv.Optional(CONF_DIO0, default=DEFAULT_RADIO_PINS[CONF_DIO0]): cv.int_range(min=0),
                cv.Optional(CONF_DIO1, default=DEFAULT_RADIO_PINS[CONF_DIO1]): cv.int_range(min=0),
                cv.Optional(CONF_DIO2, default=DEFAULT_RADIO_PINS[CONF_DIO2]): cv.int_range(min=0),
                cv.Optional(CONF_RST, default=DEFAULT_RADIO_PINS[CONF_RST]): cv.int_range(min=0),
                cv.Optional(CONF_CS, default=DEFAULT_RADIO_PINS[CONF_CS]): cv.int_range(min=0),
                cv.Optional(CONF_SCK, default=DEFAULT_RADIO_PINS[CONF_SCK]): cv.int_range(min=0),
                cv.Optional(CONF_MISO, default=DEFAULT_RADIO_PINS[CONF_MISO]): cv.int_range(min=0),
                cv.Optional(CONF_MOSI, default=DEFAULT_RADIO_PINS[CONF_MOSI]): cv.int_range(min=0),
            }
        ),
    }
)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(Gateway),
            cv.Required(CONF_KNOWN_SENSORS): cv.All(
                cv.ensure_list(SENSOR_ENTRY_SCHEMA),
                cv.Length(min=1),
                _validate_known_sensor_keys,
            ),
            cv.Optional(CONF_CANDIDATE_LIMIT, default=10): cv.int_range(min=1, max=20),
            cv.Optional(CONF_LED_PIN, default=25): cv.int_range(min=0),
            cv.Optional(CONF_RADIO, default=DEFAULT_RADIO_CONFIG): RADIO_SCHEMA,
            cv.Optional(CONF_STALE_AFTER, default="1h"): _validate_stale_after,
            cv.Optional(CONF_TIME_ID): cv.use_id(time.RealTimeClock),
            cv.Optional(CONF_CANDIDATES): cv.All(
                cv.ensure_list(text_sensor.text_sensor_schema(icon="mdi:radio-tower")),
                cv.Length(max=20),
            ),
            cv.Optional(CONF_LAST_PACKET): text_sensor.text_sensor_schema(icon="mdi:radio"),
            cv.Optional(CONF_PACKET_COUNT): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(CONF_KNOWN_PACKET_COUNT): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(CONF_UNKNOWN_PACKET_COUNT): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class="total_increasing",
            ),
            cv.Optional(CONF_DISCOVERY_ENABLED): binary_sensor.binary_sensor_schema(
                # Diagnostic read-only binary sensor mirroring runtime discovery enable state.
                entity_category="diagnostic",
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _add_default_candidates,
)

GATEWAY_ID_SCHEMA = cv.Schema({cv.GenerateID(): cv.use_id(Gateway)})


async def to_code(config: dict[str, Any]) -> None:
    """Generate C++ for the rtl433_native component."""

    cg.add_build_flag(ARDUINO_NETWORK_INCLUDE_FLAG)
    cg.add_build_flag(LEDC_COMPAT_INCLUDE_FLAG)
    cg.add_platformio_option("lib_ldf_mode", "chain+")
    radio_config = config.get(CONF_RADIO, DEFAULT_RADIO_CONFIG)
    radio_pins = radio_config[CONF_PINS]
    cg.add_build_flag(f"-DRF_{radio_config[CONF_MODULE]}")
    cg.add_build_flag(f"-DRF_MODULE_FREQUENCY={radio_config[CONF_FREQUENCY]:g}")
    cg.add_build_flag(f"-DRF_MODULE_DIO0={radio_pins[CONF_DIO0]}")
    cg.add_build_flag(f"-DRF_MODULE_DIO1={radio_pins[CONF_DIO1]}")
    cg.add_build_flag(f"-DRF_MODULE_DIO2={radio_pins[CONF_DIO2]}")
    cg.add_build_flag(f"-DRF_MODULE_RST={radio_pins[CONF_RST]}")
    cg.add_build_flag(f"-DRF_MODULE_CS={radio_pins[CONF_CS]}")
    cg.add_build_flag(f"-DRF_MODULE_SCK={radio_pins[CONF_SCK]}")
    cg.add_build_flag(f"-DRF_MODULE_MISO={radio_pins[CONF_MISO]}")
    cg.add_build_flag(f"-DRF_MODULE_MOSI={radio_pins[CONF_MOSI]}")
    for name, version, repository in RTL433_NATIVE_LIBRARIES:
        cg.add_library(name, version, repository)

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_candidate_limit(config[CONF_CANDIDATE_LIMIT]))
    cg.add(var.set_stale_after_ms(config[CONF_STALE_AFTER].total_milliseconds))
    cg.add(var.set_led_pin(config.get(CONF_LED_PIN, 25)))
    if CONF_TIME_ID in config:
        time_var = await cg.get_variable(config[CONF_TIME_ID])
        cg.add(var.set_time(time_var))

    for entry in config[CONF_KNOWN_SENSORS]:
        cg.add(
            var.add_mapping(
                entry[CONF_KEY],
                entry[CONF_MAPPING],
            )
        )
        mapping_text_id = ID(f"{entry[CONF_KEY]}_mapping", is_declaration=True, type=MappingText)
        mapping_text_config = {
            CONF_ID: mapping_text_id,
            "name": _mapping_text_name(entry),
            "entity_category": "config",
            "disabled_by_default": False,
            "mode": text.TextMode.TEXT_MODE_TEXT,
        }
        mapping_text = await text.new_text(
            mapping_text_config,
            min_length=MAPPING_TEXT_MIN_LENGTH,
            max_length=MAPPING_TEXT_MAX_LENGTH,
        )
        cg.add(cg.App.register_component_(mapping_text))
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
