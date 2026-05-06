# Project Memory

## 2026-05-06

- Project started as an ESPHome replacement for the garage `OMG_Garage`
  OpenMQTTGateway device.
- Home Assistant reported `OMG_Garage` as MQTT manufacturer `OMG_community`,
  firmware `v1.8.1`, model flags `["HELTEC_SSD1306","WebUI","rtl_433"]`,
  area `garage`, identifier `7C9EBD5ACFF8`.
- Current logical freezer/fridge mappings discovered from HA:
  - Garage Combo - Fridge: `LaCrosse-TX141THBv2-0-203`,
    `sensor.garage_combo_fridge`.
  - Garage Combo - Freezer: `TFA-303221-2-88`,
    `sensor.garage_combo_freezer`.
  - Garage Freezer 1: `Acurite-986-1R-11932`,
    `sensor.garage_freezer_1`.
  - Garage Freezer 2: `Acurite-986-2F-31274`,
    `sensor.garage_freezer_2`.
- Design direction approved: hybrid ESPHome native entities using
  `rtl_433_ESP`, with strict known-sensor mappings plus a bounded candidate
  table for discovering replacement IDs after battery changes.
- Implementation plan written at
  `docs/superpowers/plans/2026-05-06-rtl433-esphome-hybrid.md`.
