"""ESPHome codegen for the native rtl_433 gateway component."""

from __future__ import annotations

from typing import Any

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import binary_sensor, sensor, text_sensor
from esphome.const import CONF_ID

AUTO_LOAD = ["binary_sensor", "json", "sensor", "text_sensor"]
CODEOWNERS = ["@snuffy2"]

candidate_limit = "candidate_limit"
candidates = "candidates"
battery = "battery"
channel = "channel"
discovery_enabled = "discovery_enabled"
humidity = "humidity"
key = "key"
known_sensors = "known_sensors"
last_packet = "last_packet"
model = "model"
packet_count = "packet_count"
rf_id = "rf_id"
rssi = "rssi"
stale = "stale"
stale_after = "stale_after"
temperature = "temperature"
unknown_packet_count = "unknown_packet_count"

CONF_CANDIDATE_LIMIT = candidate_limit
CONF_CANDIDATES = candidates
CONF_BATTERY = battery
CONF_CHANNEL = channel
CONF_DISCOVERY_ENABLED = discovery_enabled
CONF_HUMIDITY = humidity
CONF_KEY = key
CONF_KNOWN_SENSORS = known_sensors
CONF_LAST_PACKET = last_packet
CONF_MODEL = model
CONF_PACKET_COUNT = packet_count
CONF_RF_ID = rf_id
CONF_RSSI = rssi
CONF_STALE = stale
CONF_STALE_AFTER = stale_after
CONF_TEMPERATURE = temperature
CONF_UNKNOWN_PACKET_COUNT = unknown_packet_count

rtl433_native_ns = cg.esphome_ns.namespace("rtl433_native")
Gateway = rtl433_native_ns.class_("Gateway", cg.Component)
StatusAction = rtl433_native_ns.class_("StatusAction", automation.Action)
StopAction = rtl433_native_ns.class_("StopAction", automation.Action)
ClearCandidatesAction = rtl433_native_ns.class_("ClearCandidatesAction", automation.Action)

SENSOR_ENTRY_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_KEY): cv.string_strict,
        cv.Required(CONF_MODEL): cv.string_strict,
        cv.Required(CONF_CHANNEL): cv.string_strict,
        cv.Required(CONF_RF_ID): cv.string_strict,
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
        cv.Optional(CONF_BATTERY): sensor.sensor_schema(
            unit_of_measurement="%",
            accuracy_decimals=0,
            device_class="battery",
            state_class="measurement",
        ),
        cv.Optional(CONF_RSSI): sensor.sensor_schema(
            unit_of_measurement="dB",
            accuracy_decimals=0,
            device_class="signal_strength",
            state_class="measurement",
        ),
        cv.Optional(CONF_STALE): binary_sensor.binary_sensor_schema(device_class="problem"),
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(Gateway),
        cv.Required(CONF_KNOWN_SENSORS): cv.All(
            cv.ensure_list(SENSOR_ENTRY_SCHEMA),
            cv.Length(min=1),
        ),
        cv.Optional(CONF_CANDIDATE_LIMIT, default=10): cv.int_range(min=1, max=20),
        cv.Optional(CONF_STALE_AFTER, default="1h"): cv.positive_time_period_milliseconds,
        cv.Optional(CONF_CANDIDATES, default=[]): cv.All(
            cv.ensure_list(text_sensor.text_sensor_schema(icon="mdi:radio-tower")),
            cv.Length(max=20),
        ),
        cv.Optional(CONF_LAST_PACKET): text_sensor.text_sensor_schema(icon="mdi:radio"),
        cv.Optional(CONF_PACKET_COUNT): sensor.sensor_schema(
            accuracy_decimals=0,
            state_class="total_increasing",
        ),
        cv.Optional(CONF_UNKNOWN_PACKET_COUNT): sensor.sensor_schema(
            accuracy_decimals=0,
            state_class="total_increasing",
        ),
        cv.Optional(CONF_DISCOVERY_ENABLED): binary_sensor.binary_sensor_schema(
            entity_category="diagnostic",
        ),
    }
).extend(cv.COMPONENT_SCHEMA)

GATEWAY_ID_SCHEMA = cv.Schema({cv.GenerateID(): cv.use_id(Gateway)})


async def to_code(config: dict[str, Any]) -> None:
    """Generate C++ for the rtl433_native component."""

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_candidate_limit(config[CONF_CANDIDATE_LIMIT]))
    cg.add(var.set_stale_after_ms(config[CONF_STALE_AFTER].total_milliseconds))

    for entry in config[CONF_KNOWN_SENSORS]:
        cg.add(
            var.add_mapping(
                entry[CONF_KEY],
                entry[CONF_MODEL],
                entry[CONF_CHANNEL],
                entry[CONF_RF_ID],
            )
        )
        temperature = await sensor.new_sensor(entry[CONF_TEMPERATURE])
        cg.add(var.set_temperature_sensor(entry[CONF_KEY], temperature))
        if CONF_HUMIDITY in entry:
            humidity = await sensor.new_sensor(entry[CONF_HUMIDITY])
            cg.add(var.set_humidity_sensor(entry[CONF_KEY], humidity))
        if CONF_BATTERY in entry:
            battery = await sensor.new_sensor(entry[CONF_BATTERY])
            cg.add(var.set_battery_sensor(entry[CONF_KEY], battery))
        if CONF_RSSI in entry:
            rssi = await sensor.new_sensor(entry[CONF_RSSI])
            cg.add(var.set_rssi_sensor(entry[CONF_KEY], rssi))
        if CONF_STALE in entry:
            stale = await binary_sensor.new_binary_sensor(entry[CONF_STALE])
            cg.add(var.set_stale_sensor(entry[CONF_KEY], stale))

    for index, candidate_config in enumerate(config[CONF_CANDIDATES]):
        candidate = await text_sensor.new_text_sensor(candidate_config)
        cg.add(var.set_candidate_text_sensor(index, candidate))

    if CONF_LAST_PACKET in config:
        last_packet_sensor = await text_sensor.new_text_sensor(config[CONF_LAST_PACKET])
        cg.add(var.set_last_packet_sensor(last_packet_sensor))
    if CONF_PACKET_COUNT in config:
        packet_count_sensor = await sensor.new_sensor(config[CONF_PACKET_COUNT])
        cg.add(var.set_packet_count_sensor(packet_count_sensor))
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
)
@automation.register_action(
    "rtl433_native.stop",
    StopAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
)
@automation.register_action(
    "rtl433_native.clear_candidates",
    ClearCandidatesAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
)
async def action_to_code(
    config: dict[str, Any], action_id: Any, template_arg: Any, args: Any
) -> Any:
    """Generate ESPHome automation action instances."""

    del args
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var
