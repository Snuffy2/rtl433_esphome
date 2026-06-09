# Garage RTL433 ESPHome Gateway

ESPHome replacement for an OpenMQTTGateway receiver. The firmware uses `rtl_433_ESP` on a Heltec WiFi LoRa 32 V2-style 433 MHz board and publishes native Home Assistant entities for the known sensors.

## Known Sensor Mappings

| Logical sensor | Mapping | Current HA entity |
| --- | --- | --- |
| Garage Combo Fridge | `LaCrosse-TX141THBv2/0/203;TFA-303221/1/203` | `sensor.garage_combo_fridge` |
| Garage Combo Freezer | `TFA-303221/2/88;LaCrosse-TX141THBv2/1/88` | `sensor.garage_combo_freezer` |
| Garage Freezer 1 | `Acurite-986/1R/11932` | `sensor.garage_freezer_1` |
| Garage Freezer 2 | `Acurite-986/2F/31274` | `sensor.garage_freezer_2` |

Use semicolon-delimited mappings when rtl_433 reports the same physical
transmitter under more than one decoder key. Each entry uses the
`model/channel/id` format shown in discovery candidates.

## Build

```bash
uv venv .venv
uv sync --group dev
./.venv/bin/python -m esphome config garage-rtl433.yaml
./.venv/bin/python -m esphome compile garage-rtl433.yaml
```

## Discovery Workflow After Battery Changes

1. Turn on `Garage RTL433 Discovery Mode`.
2. Press `Garage RTL433 Clear Candidates`.
3. Insert batteries into one sensor or force it to transmit.
4. Watch `Garage RTL433 Candidate 1` through `Garage RTL433 Candidate 10`.
5. Copy the candidate key in `model/channel/id` format.
6. Paste it into the matching mapping text entity. Use semicolons to list
   multiple keys for the same physical sensor.
7. Confirm the logical temperature entity updates.
8. Turn off `Garage RTL433 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never
automatically rebinds a freezer/fridge mapping.
