#include "rtl433_native.h"
#include "ledc_compat.h"

#include <Arduino.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

#include "esphome/components/json/json_util.h"
#include "esphome/core/log.h"
#include "esphome/core/time.h"

namespace esphome::rtl433_native {

namespace {

const char *const TAG = "rtl433_native";

float json_float_or_nan(JsonObject root, const char *key) {
  if (root[key].is<float>()) {
    return root[key].as<float>();
  }
  if (root[key].is<double>()) {
    return static_cast<float>(root[key].as<double>());
  }
  if (root[key].is<int>()) {
    return static_cast<float>(root[key].as<int>());
  }
  return std::numeric_limits<float>::quiet_NaN();
}

float celsius_to_fahrenheit(float value) { return value * 9.0f / 5.0f + 32.0f; }

uint32_t preference_key(const std::string &logical_key) {
  uint32_t hash = 2166136261UL;
  for (char value : logical_key) {
    hash ^= static_cast<uint8_t>(value);
    hash *= 16777619UL;
  }
  return hash ^ 0xA4330E01UL;
}

uint32_t mapping_preference_key(const std::string &logical_key) {
  return preference_key("mapping:" + logical_key) ^ 0x1A77B433UL;
}

uint32_t saved_state_mapping_preference_key(const std::string &logical_key) {
  return preference_key("state_mapping:" + logical_key) ^ 0x5147B433UL;
}

}  // namespace

Gateway *Gateway::instance_ = nullptr;

Gateway::Gateway() { instance_ = this; }

void Gateway::setup() {
  pinMode(this->led_pin_, OUTPUT);
  digitalWrite(this->led_pin_, LOW);
#ifdef USE_OTA_STATE_LISTENER
  ota::get_global_ota_callback()->add_global_state_listener(this);
#endif
  this->time_->add_on_time_sync_callback([this]() { this->sync_time_base(); });
  this->sync_time_base();
  if (this->packet_count_sensor_ != nullptr) {
    this->packet_count_sensor_->publish_state(0);
  }
  if (this->known_packet_count_sensor_ != nullptr) {
    this->known_packet_count_sensor_->publish_state(0);
  }
  if (this->unknown_packet_count_sensor_ != nullptr) {
    this->unknown_packet_count_sensor_->publish_state(0);
  }
  this->rf_.initReceiver(RF_MODULE_RECEIVER_GPIO, RF_MODULE_FREQUENCY);
  this->rf_.setCallback(&Gateway::process_dispatch, this->buffer_, sizeof(this->buffer_));
  this->rf_.enableReceiver();
}

void Gateway::loop() {
  if (!this->restored_states_) {
    this->restored_states_ = true;
    this->restore_saved_states();
  }
  this->rf_.loop();
  this->publish_stale_states();
}

void Gateway::dump_config() {
  ESP_LOGCONFIG(TAG, "RTL433 native gateway");
  ESP_LOGCONFIG(TAG, "  Version: %s", this->version_.c_str());
  ESP_LOGCONFIG(TAG, "  Candidate limit: %u",
                static_cast<unsigned>(this->state_.candidate_limit()));
}

#ifdef USE_OTA_STATE_LISTENER
void Gateway::on_ota_global_state(ota::OTAState state, float progress, uint8_t error,
                                  ota::OTAComponent *component) {
  (void) progress;
  (void) error;
  (void) component;
  if (state == ota::OTA_STARTED) {
    this->stop();
  }
}
#endif

void Gateway::stop() { this->rf_.disableReceiver(); }

void Gateway::status() {
  this->rf_.getStatus();
  this->rf_.getModuleStatus();
}

void Gateway::clear_candidates() {
  this->state_.clear_candidates();
  this->publish_candidates();
}

void Gateway::set_discovery_enabled(bool enabled) {
  this->state_.set_discovery_enabled(enabled);
  if (this->discovery_enabled_sensor_ != nullptr) {
    this->discovery_enabled_sensor_->publish_state(enabled);
  }
}

void Gateway::add_mapping(const std::string &logical_key, const std::string &mapping) {
  this->state_.set_mapping(logical_key, mapping);
  this->entities_.try_emplace(logical_key);
  if (std::find(this->logical_keys_.begin(), this->logical_keys_.end(), logical_key) ==
      this->logical_keys_.end()) {
    this->logical_keys_.push_back(logical_key);
  }
}

void Gateway::set_override(const std::string &logical_key, const std::string &sensor_key) {
  this->entities_.try_emplace(logical_key);
  const bool mapping_changed = this->state_.set_mapping(logical_key, sensor_key);
  if (mapping_changed) {
    if (!this->restored_states_) {
      this->remapped_before_restore_.insert(logical_key);
    }
    this->pending_clock_age_restore_.erase(logical_key);
  }
}

void Gateway::set_candidate_limit(std::size_t limit) { this->state_.set_candidate_limit(limit); }

void Gateway::set_stale_after_ms(uint32_t stale_after_ms) {
  this->state_.set_stale_after_ms(stale_after_ms);
}

void Gateway::set_temperature_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].temperature = sensor;
}

void Gateway::set_humidity_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].humidity = sensor;
}

void Gateway::set_battery_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor) {
  this->entities_[logical_key].battery = sensor;
}

void Gateway::set_rssi_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].rssi = sensor;
}

void Gateway::set_stale_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor) {
  this->entities_[logical_key].stale = sensor;
}

void Gateway::set_last_updated_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].last_updated = sensor;
}

void Gateway::set_candidate_text_sensor(std::size_t index, text_sensor::TextSensor *sensor) {
  if (index < this->candidate_sensors_.size()) {
    this->candidate_sensors_[index] = sensor;
  }
}

void Gateway::set_last_packet_sensor(text_sensor::TextSensor *sensor) {
  this->last_packet_sensor_ = sensor;
}

void Gateway::set_packet_count_sensor(sensor::Sensor *sensor) { this->packet_count_sensor_ = sensor; }

void Gateway::set_known_packet_count_sensor(sensor::Sensor *sensor) {
  this->known_packet_count_sensor_ = sensor;
}

void Gateway::set_unknown_packet_count_sensor(sensor::Sensor *sensor) {
  this->unknown_packet_count_sensor_ = sensor;
}

void Gateway::set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor) {
  this->discovery_enabled_sensor_ = sensor;
  if (this->discovery_enabled_sensor_ != nullptr) {
    this->discovery_enabled_sensor_->publish_state(this->state_.discovery_enabled());
  }
}

void DiscoverySwitch::setup() {
  bool enabled = false;
  optional<bool> initial_state = this->get_initial_state_with_restore_mode();
  if (initial_state.has_value()) {
    enabled = initial_state.value();
  }
  if (this->parent_ != nullptr) {
    this->parent_->set_discovery_enabled(enabled);
  }
  this->publish_state(enabled);
}

void DiscoverySwitch::write_state(bool state) {
  if (this->parent_ != nullptr) {
    this->parent_->set_discovery_enabled(state);
  }
  this->publish_state(state);
}

void ClearCandidatesButton::press_action() {
  if (this->parent_ != nullptr) {
    this->parent_->clear_candidates();
  }
}

void StatusButton::press_action() {
  if (this->parent_ != nullptr) {
    this->parent_->status();
  }
}

void Gateway::process_dispatch(char *message) {
  if (Gateway::instance_ != nullptr) {
    Gateway::instance_->process_message(message);
  }
}

void Gateway::process_message(char *message) {
  ESP_LOGD(TAG, "Received rtl_433 message: %s", message);
  json::parse_json(message, [this](JsonObject root) {
    const char *model = root["model"] | "";
    if (std::string(model) == "status") {
      return true;
    }

    ::esphome::rtl433_native::DecodedPacket packet;
    packet.model = model;
    if (root["id"].is<const char *>()) {
      packet.id = root["id"].as<const char *>();
    } else if (root["id"].is<int>()) {
      packet.id = std::to_string(root["id"].as<int>());
    } else if (root["id"].is<unsigned int>()) {
      packet.id = std::to_string(root["id"].as<unsigned int>());
    } else if (root["id"].is<uint32_t>()) {
      packet.id = std::to_string(root["id"].as<uint32_t>());
    }

    if (root["channel"].is<const char *>()) {
      packet.channel = root["channel"].as<const char *>();
    } else if (root["channel"].is<int>()) {
      packet.channel = std::to_string(root["channel"].as<int>());
    } else if (root["subtype"].is<int>()) {
      packet.channel = std::to_string(root["subtype"].as<int>());
    } else if (root["subtype"].is<const char *>()) {
      packet.channel = root["subtype"].as<const char *>();
    } else {
      packet.channel = "0";
    }

    float temperature = json_float_or_nan(root, "temperature_F");
    if (!std::isnan(temperature)) {
      packet.temperature_f = temperature;
    } else if (!std::isnan(temperature = json_float_or_nan(root, "temperature_1_F"))) {
      packet.temperature_f = temperature;
    } else if (!std::isnan(temperature = json_float_or_nan(root, "temperature_C"))) {
      packet.temperature_f = celsius_to_fahrenheit(temperature);
    } else if (!std::isnan(temperature = json_float_or_nan(root, "temperature_1_C"))) {
      packet.temperature_f = celsius_to_fahrenheit(temperature);
    } else {
      packet.temperature_f = std::numeric_limits<float>::quiet_NaN();
    }
    packet.humidity = root["humidity"] | NAN;
    if (root["battery_ok"].is<bool>()) {
      packet.battery = root["battery_ok"].as<bool>() ? 100.0f : 0.0f;
    } else if (root["battery_ok"].is<int>()) {
      packet.battery = root["battery_ok"].as<int>() ? 100.0f : 0.0f;
    } else if (root["battery_ok"].is<float>()) {
      packet.battery = root["battery_ok"].as<float>() ? 100.0f : 0.0f;
    }

    packet.rssi = root["rssi"] | 0;
    packet.seen_ms = millis();

    const ::esphome::rtl433_native::PacketResult result = this->state_.process_packet(packet);
    if (result == ::esphome::rtl433_native::PacketResult::REJECTED_INVALID) {
      ESP_LOGW(TAG, "Rejected invalid rtl_433 packet: %s", packet.model.c_str());
      return true;
    }

    this->packet_count_ += 1;
    if (this->packet_count_sensor_ != nullptr) {
      this->packet_count_sensor_->publish_state(this->packet_count_);
    }
    if (result == ::esphome::rtl433_native::PacketResult::MATCHED_KNOWN) {
      this->known_packet_count_ += 1;
      if (this->known_packet_count_sensor_ != nullptr) {
        this->known_packet_count_sensor_->publish_state(this->known_packet_count_);
      }
    }

    if (this->last_packet_sensor_ != nullptr) {
      this->last_packet_sensor_->publish_state(
          ::esphome::rtl433_native::format_sensor_key({packet.model, packet.channel, packet.id}));
    }

    if (result == ::esphome::rtl433_native::PacketResult::MATCHED_KNOWN) {
      const uint32_t last_updated = this->current_timestamp();
      for (const auto &entry : this->entities_) {
        const auto &logical_key = entry.first;
        const auto *logical = this->state_.logical_sensor(logical_key);
        if (logical != nullptr && logical->last_seen_ms == packet.seen_ms) {
          this->pending_clock_age_restore_.erase(logical_key);
          this->save_state(logical_key, last_updated);
          this->publish_state(logical_key);
        }
      }
    } else if (result == ::esphome::rtl433_native::PacketResult::RECORDED_CANDIDATE ||
               result == ::esphome::rtl433_native::PacketResult::IGNORED_UNKNOWN) {
      this->unknown_packet_count_ += 1;
      if (this->unknown_packet_count_sensor_ != nullptr) {
        this->unknown_packet_count_sensor_->publish_state(this->unknown_packet_count_);
      }
    }

    this->publish_candidates();
    return true;
  });
}

void Gateway::restore_saved_states() {
  bool restored_any = false;
  for (const auto &logical_key : this->logical_keys_) {
    auto preference = global_preferences->make_preference<SavedLogicalState>(preference_key(logical_key), true);
    SavedLogicalState saved;
    this->preferences_[logical_key] = preference;
    if (!preference.load(&saved) || !saved.has_value) {
      continue;
    }
    if (this->remapped_before_restore_.find(logical_key) != this->remapped_before_restore_.end()) {
      auto mapping_preference =
          global_preferences->make_preference<SavedLogicalMapping>(saved_state_mapping_preference_key(logical_key), true);
      SavedLogicalMapping saved_mapping;
      if (!mapping_preference.load(&saved_mapping) || !saved_mapping.has_value || saved_mapping.value[0] == '\0' ||
          !this->state_.mapping_matches(logical_key, saved_mapping.value)) {
        continue;
      }
    }

    LogicalSensorState restored;
    restored.has_value = true;
    restored.temperature_f = saved.temperature_f;
    restored.humidity = saved.humidity;
    restored.battery = saved.battery;
    restored.rssi = saved.rssi;
    const uint32_t restore_timestamp = this->current_timestamp();
    restored.last_seen_ms = resolve_restored_last_seen_ms(
        saved.last_updated, restore_timestamp, millis(), this->state_.stale_after_ms());
    this->state_.restore_logical_state(logical_key, restored);
    this->last_updated_values_[logical_key] = saved.last_updated;
    if (saved.last_updated > 0 && restore_timestamp == 0) {
      this->pending_clock_age_restore_.insert(logical_key);
    }
    this->publish_state(logical_key);
    restored_any = true;
  }

  if (restored_any) {
    this->set_timeout("publish_restored_states", 2000, [this]() {
      for (const auto &logical_key : this->logical_keys_) {
        this->publish_state(logical_key);
      }
    });
  }
  this->remapped_before_restore_.clear();
}

void Gateway::sync_time_base() {
  ESPTime now = this->time_->utcnow();
  if (!now.is_valid()) {
    return;
  }
  const uint32_t next_epoch = static_cast<uint32_t>(now.timestamp);
  this->time_sync_epoch_ = next_epoch;
  this->time_sync_ms_ = millis();
  this->reproject_pending_restored_states(next_epoch);
}

void Gateway::reproject_pending_restored_states(uint32_t current_timestamp) {
  const uint32_t now_ms = millis();
  auto item = this->pending_clock_age_restore_.begin();
  while (item != this->pending_clock_age_restore_.end()) {
    const std::string logical_key = *item;
    item = this->pending_clock_age_restore_.erase(item);

    const auto last_updated_item = this->last_updated_values_.find(logical_key);
    const auto *logical = this->state_.logical_sensor(logical_key);
    if (last_updated_item == this->last_updated_values_.end() || logical == nullptr || !logical->has_value) {
      continue;
    }

    LogicalSensorState restored = *logical;
    restored.last_seen_ms = resolve_restored_last_seen_ms(
        last_updated_item->second, current_timestamp, now_ms, this->state_.stale_after_ms());
    this->state_.restore_logical_state(logical_key, restored);
    this->publish_state(logical_key);
  }
}

uint32_t Gateway::current_timestamp() {
  ESPTime now = this->time_->utcnow();
  if (now.is_valid()) {
    return static_cast<uint32_t>(now.timestamp);
  }
  return resolve_projected_timestamp(this->time_sync_epoch_, this->time_sync_ms_, millis());
}

void Gateway::save_state(const std::string &logical_key, uint32_t last_updated) {
  const auto *logical = this->state_.logical_sensor(logical_key);
  if (logical == nullptr || !logical->has_value) {
    return;
  }

  auto preference_item = this->preferences_.find(logical_key);
  if (preference_item == this->preferences_.end()) {
    preference_item =
        this->preferences_
            .emplace(logical_key,
                     global_preferences->make_preference<SavedLogicalState>(preference_key(logical_key), true))
            .first;
  }

  SavedLogicalState saved;
  saved.has_value = true;
  saved.temperature_f = logical->temperature_f;
  saved.humidity = logical->humidity;
  saved.battery = logical->battery;
  saved.rssi = logical->rssi;
  const auto previous_last_updated = this->last_updated_values_.find(logical_key);
  const uint32_t previous_timestamp =
      previous_last_updated == this->last_updated_values_.end() ? 0 : previous_last_updated->second;
  const uint32_t adjusted_last_updated = resolve_last_updated_timestamp(last_updated, previous_timestamp);
  if (adjusted_last_updated > 0) {
    this->last_updated_values_[logical_key] = adjusted_last_updated;
  }
  const auto last_updated_item = this->last_updated_values_.find(logical_key);
  if (last_updated_item != this->last_updated_values_.end()) {
    saved.last_updated = last_updated_item->second;
  }
  preference_item->second.save(&saved);
  const auto mapping_value = this->state_.mapping_value(logical_key);
  if (mapping_value.has_value()) {
    SavedLogicalMapping saved_mapping;
    saved_mapping.has_value = true;
    std::strncpy(saved_mapping.value, mapping_value->c_str(), sizeof(saved_mapping.value) - 1);
    saved_mapping.value[sizeof(saved_mapping.value) - 1] = '\0';
    auto mapping_preference =
        global_preferences->make_preference<SavedLogicalMapping>(saved_state_mapping_preference_key(logical_key), true);
    mapping_preference.save(&saved_mapping);
  }
}

void Gateway::publish_stale_state(const std::string &logical_key, EntitySet &entities, uint32_t now_ms) {
  if (entities.stale == nullptr) {
    return;
  }
  const bool stale = this->state_.is_stale(logical_key, now_ms);
  if (!entities.stale_initialized || entities.last_stale != stale) {
    entities.last_stale = stale;
    entities.stale_initialized = true;
    entities.stale->publish_state(stale);
  }
}

void Gateway::publish_state(const std::string &logical_key) {
  const auto entities_item = this->entities_.find(logical_key);
  const auto *logical = this->state_.logical_sensor(logical_key);
  if (entities_item == this->entities_.end() || logical == nullptr || !logical->has_value) {
    return;
  }

  EntitySet &entities = entities_item->second;
  if (entities.temperature != nullptr && !std::isnan(logical->temperature_f)) {
    entities.temperature->publish_state(logical->temperature_f);
  }
  if (entities.humidity != nullptr && !std::isnan(logical->humidity)) {
    entities.humidity->publish_state(logical->humidity);
  }
  if (entities.battery != nullptr && !std::isnan(logical->battery)) {
    entities.battery->publish_state(logical->battery <= 0.0f);
  }
  if (entities.rssi != nullptr) {
    entities.rssi->publish_state(logical->rssi);
  }
  this->publish_stale_state(logical_key, entities, millis());
  const auto last_updated_item = this->last_updated_values_.find(logical_key);
  if (entities.last_updated != nullptr && last_updated_item != this->last_updated_values_.end() &&
      last_updated_item->second > 0) {
    entities.last_updated->publish_state(last_updated_item->second);
  }
}

void Gateway::publish_candidates() {
  const auto &candidates = this->state_.candidates();
  for (std::size_t index = 0; index < this->candidate_sensors_.size(); ++index) {
    auto *sensor = this->candidate_sensors_[index];
    if (sensor == nullptr) {
      continue;
    }
    const std::string next_value =
        (index < candidates.size()) ? ::esphome::rtl433_native::format_candidate(candidates[index]) : "";
    if (this->last_candidate_values_[index] == next_value) {
      continue;
    }
    this->last_candidate_values_[index] = next_value;
    sensor->publish_state(next_value);
  }
}

void Gateway::publish_stale_states() {
  const uint32_t now = millis();
  for (auto &[logical_key, entities] : this->entities_) {
    this->publish_stale_state(logical_key, entities, now);
  }
}

void MappingText::setup() {
  this->preference_ = global_preferences->make_preference<SavedMappingText>(
      mapping_preference_key(this->logical_key_), true);

  SavedMappingText saved;
  if (this->preference_.load(&saved) && saved.has_value && saved.value[0] != '\0') {
    this->apply_value(saved.value, false);
    return;
  }

  this->apply_value(this->initial_value_, false);
}

void MappingText::dump_config() {
  ESP_LOGCONFIG(TAG, "RTL433 mapping text");
  ESP_LOGCONFIG(TAG, "  Logical key: %s", this->logical_key_.c_str());
}

void MappingText::control(const std::string &value) { this->apply_value(value, true); }

void MappingText::apply_value(const std::string &value, bool save) {
  if (!parse_sensor_mapping(value).has_value()) {
    ESP_LOGW(TAG, "Rejected invalid mapping text for '%s': %s", this->logical_key_.c_str(), value.c_str());
    return;
  }

  this->publish_state(value);
  if (this->parent_ != nullptr) {
    this->parent_->set_override(this->logical_key_, value);
  }

  if (!save) {
    return;
  }

  SavedMappingText saved;
  saved.has_value = true;
  std::strncpy(saved.value, value.c_str(), sizeof(saved.value) - 1);
  saved.value[sizeof(saved.value) - 1] = '\0';
  this->preference_.save(&saved);
}

}  // namespace esphome::rtl433_native
