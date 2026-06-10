"""ESPHome codegen for the native rtl_433 gateway component."""

from __future__ import annotations

from typing import Any

from esphome import automation
import esphome.codegen as cg
from esphome.components import binary_sensor, sensor, text_sensor, time
import esphome.config_validation as cv
from esphome.const import CONF_ID

AUTO_LOAD = ["binary_sensor", "json", "sensor", "text_sensor", "time"]
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
CONF_MAPPING = "mapping"
CONF_PACKET_COUNT = "packet_count"
CONF_RSSI = "rssi"
CONF_STALE = "stale"
CONF_STALE_AFTER = "stale_after"
CONF_TEMPERATURE = "temperature"
CONF_TIME_ID = "time_id"
CONF_UNKNOWN_PACKET_COUNT = "unknown_packet_count"

rtl433_native_ns = cg.esphome_ns.namespace("rtl433_native")
Gateway = rtl433_native_ns.class_("Gateway", cg.Component)
StatusAction = rtl433_native_ns.class_("StatusAction", automation.Action)
StopAction = rtl433_native_ns.class_("StopAction", automation.Action)
ClearCandidatesAction = rtl433_native_ns.class_("ClearCandidatesAction", automation.Action)

UINT32_MAX_MILLISECONDS = 4_294_967_295
ARDUINO_NETWORK_INCLUDE_FLAG = (
    '-I"${platformio.packages_dir}/framework-arduinoespressif32/libraries/Network/src"'
)


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
        config[CONF_CANDIDATES] = [
            {
                "name": f"Candidate {index + 1}",
                "entity_category": "diagnostic",
                "icon": "mdi:radio-tower",
            }
            for index in range(config[CONF_CANDIDATE_LIMIT])
        ]
    return config


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
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_candidate_limit(config[CONF_CANDIDATE_LIMIT]))
    cg.add(var.set_stale_after_ms(config[CONF_STALE_AFTER].total_milliseconds))
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
