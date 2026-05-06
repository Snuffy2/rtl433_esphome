# Garage RTL433 ESPHome Gateway

ESPHome replacement for the garage `OMG_Garage` OpenMQTTGateway receiver. The
firmware uses `rtl_433_ESP` on a Heltec WiFi LoRa 32 V2-style 433 MHz board and
publishes native Home Assistant entities for the known fridge/freezer sensors.

## Known Sensor Mappings

| Logical sensor | Mapping key | Current HA entity |
| --- | --- | --- |
| Garage Combo Fridge | `LaCrosse-TX141THBv2/0/203` | `sensor.garage_combo_fridge` |
| Garage Combo Freezer | `TFA-303221/2/88` | `sensor.garage_combo_freezer` |
| Garage Freezer 1 | `Acurite-986/1R/11932` | `sensor.garage_freezer_1` |
| Garage Freezer 2 | `Acurite-986/2F/31274` | `sensor.garage_freezer_2` |

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
6. Paste it into the matching mapping text entity.
7. Confirm the logical temperature entity updates.
8. Turn off `Garage RTL433 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never
automatically rebinds a freezer/fridge mapping.

## Initial Rollout

1. Flash as `garage-rtl433-native`, leaving `OMG_Garage` in place.
2. Compare the four native ESPHome entities with the existing MQTT/template
   entities for several update cycles. This comparison remains pending for a
   hardware/HA rollout gate and has not been completed in this batch.
3. Rename the native entities to the existing public entity IDs after the new
   values are stable.
4. Disable the OpenMQTTGateway smart-plug restart automations in a separate Home
   Assistant cleanup after the ESPHome device has proven reliable.
