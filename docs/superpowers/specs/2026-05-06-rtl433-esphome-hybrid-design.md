# RTL_433 ESPHome Hybrid Gateway Design

Date: 2026-05-06

## Context

The current garage freezer/fridge receiver is an OpenMQTTGateway device named
`OMG_Garage`. Home Assistant reports it as an MQTT device from
`OMG_community`, firmware `v1.8.1`, with model flags
`["HELTEC_SSD1306","WebUI","rtl_433"]`. This points to a Heltec WiFi LoRa 32
V2-style ESP32 board with an SX127x radio and SSD1306 display.

The current MQTT-discovered thermometer devices are:

| Logical sensor | Current raw device key | Current entity |
| --- | --- | --- |
| Garage Combo - Fridge | `LaCrosse-TX141THBv2-0-203` | `sensor.garage_combo_fridge` |
| Garage Combo - Freezer | `TFA-303221-2-88` | `sensor.garage_combo_freezer` |
| Garage Freezer 1 | `Acurite-986-1R-11932` | `sensor.garage_freezer_1` |
| Garage Freezer 2 | `Acurite-986-2F-31274` | `sensor.garage_freezer_2` |

The main pain point is not only gateway instability. When batteries are
changed, sensor IDs can change, which forces the user to rediscover devices and
update Home Assistant entities. The replacement must keep Home Assistant clean
despite many chatty unknown `rtl_433` devices nearby.

## Goals

- Replace OpenMQTTGateway with ESPHome on the existing LoRa32-class device.
- Use the `rtl_433_ESP` library for decoding.
- Publish four stable native ESPHome/Home Assistant sensor entities.
- Provide a bounded discovery workflow for finding replacement IDs after
  battery changes.
- Avoid creating normal HA entities for every unknown nearby `rtl_433` device.
- Preserve the final public entity IDs through Home Assistant renames during
  cutover.

## Non-Goals

- Build a general-purpose `rtl_433` gateway for every device in range.
- Auto-rebind unknown packets to logical freezer/fridge sensors.
- Remove the existing OpenMQTTGateway restart automations during initial
  firmware rollout.
- Create a separate Home Assistant custom integration unless the ESPHome-only
  implementation proves insufficient.

## Architecture

The firmware has three layers:

1. Radio and decoder layer: configures the SX127x radio and feeds received
   packets through `rtl_433_ESP`.
2. Mapping layer: normalizes decoded packet fields and matches them to four
   configured logical sensors.
3. Discovery layer: tracks unknown packet candidates in a bounded table for
   battery-change rebinding.

Normal Home Assistant output is limited to the four freezer/fridge sensors:

- Garage Combo Fridge
- Garage Combo Freezer
- Garage Freezer 1
- Garage Freezer 2

Each logical sensor should expose temperature as the primary sensor. Where the
decoded protocol provides it, related diagnostics such as humidity, battery,
RSSI, last update, and stale status can also be exposed.

Gateway diagnostics should include uptime, Wi-Fi RSSI, free heap, last decoded
packet time, known packet count, unknown packet count, and decoder error count
if available.

## Packet Data Flow

Each decoded packet is normalized into an internal record:

- `model`
- `id`
- `channel` or subtype
- `temperature_f`
- `humidity`
- `battery`
- `rssi`
- `timestamp`

Processing rules:

- If the packet matches a configured logical mapping, update that logical
  sensor and its diagnostics.
- If it does not match and discovery mode is enabled, update or insert a
  candidate table row keyed by `(model, id, channel/subtype)`.
- If it does not match and discovery mode is disabled, ignore the packet except
  for lightweight counters.

## Mapping And Rebinding

Mappings have two tiers:

1. Default mappings compiled from YAML/firmware, using the current IDs found in
   Home Assistant.
2. Runtime overrides through ESPHome controls are the preferred implementation.
   The implementation plan should include a short technical spike for persistent
   text/select-style mapping overrides. If that spike proves the ESPHome API is
   not reliable enough for this use, YAML edit plus OTA reflash becomes the
   documented fallback for the first release.

The mapping format must be explicit:

`logical_sensor = model + channel/subtype + id`

Examples:

- `garage_combo_fridge = LaCrosse-TX141THBv2 / channel 0 / id 203`
- `garage_combo_freezer = TFA-303221 / channel 2 / id 88`

The firmware must not create normal entities for newly discovered devices.
Unknowns are diagnostics only.

## Discovery Candidate Table

A single "last unknown packet" is not sufficient because nearby devices can be
chatty. Discovery mode uses a bounded candidate table instead.

Candidate rows are grouped by `(model, id, channel/subtype)` and track:

- model
- id
- channel or subtype
- temperature
- humidity
- battery
- RSSI
- first seen
- last seen
- packet count
- whether it matched a configured logical sensor

Expose the top candidates as diagnostic text sensors, for example
`candidate_1` through `candidate_10`. Sort by recent activity by default. If
noise is too high, add a minimum RSSI threshold or model filter.

Discovery controls:

- Discovery mode switch.
- Clear candidates button.
- Optional minimum RSSI control.
- Optional model filter if it is practical in ESPHome.

Battery-change workflow:

1. Enable discovery mode.
2. Clear candidates.
3. Insert batteries or wake one sensor.
4. Watch candidate rows for the new model/id/channel with plausible
   temperature and strong RSSI.
5. Update the logical mapping.
6. Disable discovery mode.

The device must not auto-rebind; the user confirms the mapping.

## Reliability Behavior

- Stop the receive loop during OTA updates to improve update reliability.
- Keep candidate storage bounded by row count and age.
- Expose stale status for each logical sensor when no matching packet is seen
  for a configurable period.
- Prefer a stale diagnostic over overwriting the last known temperature.
- Preserve enough diagnostics to distinguish decoder/radio silence from Wi-Fi
  or Home Assistant connectivity problems.

## Rollout Plan

1. Build ESPHome firmware under a temporary device name to avoid collisions with
   existing MQTT entities.
2. Flash the device by USB or OTA, whichever is more reliable for the current
   board state.
3. Confirm the device joins Home Assistant as a new ESPHome node.
4. Compare native ESPHome entities against the existing MQTT/template entities
   for several update cycles.
5. After stable operation, rename/adopt the desired final entity IDs in Home
   Assistant.
6. Leave the current smart-plug restart automations in place until the ESPHome
   replacement has proven stable, then clean them up separately.

## Testing And Documentation

- Structure parsing and mapping logic so it can be unit-tested where practical.
- Add tests for matching known packets, rejecting unknown packets, updating
  candidate rows, clearing candidates, and stale-status transitions.
- Document board assumptions, radio frequency, pin mapping, known sensor
  mappings, diagnostics, and the battery-change rebinding workflow.
- Include current HA-discovered entity and device IDs in the README for
  migration reference.
