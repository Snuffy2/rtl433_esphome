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

bool is_blank_mapping_text(const std::string &value) {
  return std::all_of(value.begin(), value.end(), [](char item) {
    return item == ' ' || item == '\t' || item == '\n' || item == '\r' || item == '\f' ||
           item == '\v';
  });
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
  this->candidate_publish_pending_ = false;
  this->publish_candidates();
}

void Gateway::set_discovery_enabled(bool enabled) {
  this->state_.set_discovery_enabled(enabled);
}

void Gateway::register_logical_key(const std::string &logical_key) {
  this->entities_.try_emplace(logical_key);
  if (std::find(this->logical_keys_.begin(), this->logical_keys_.end(), logical_key) ==
      this->logical_keys_.end()) {
    this->logical_keys_.push_back(logical_key);
  }
}

void Gateway::add_mapping(const std::string &logical_key, const std::string &mapping) {
  this->register_logical_key(logical_key);
  this->state_.set_mapping(logical_key, mapping);
}

void Gateway::set_override(const std::string &logical_key, const std::string &sensor_key) {
  this->register_logical_key(logical_key);
  const bool mapping_changed = this->state_.set_mapping(logical_key, sensor_key);
  if (mapping_changed) {
    this->pending_clock_age_restore_.erase(logical_key);
    this->last_updated_values_.erase(logical_key);
    this->last_saved_state_mapping_hashes_.erase(logical_key);
    this->last_state_save_ms_.erase(logical_key);
    this->publish_stale_states();
  }
}

void Gateway::set_candidate_limit(std::size_t limit) { this->state_.set_candidate_limit(limit); }

void Gateway::set_stale_after_ms(uint32_t stale_after_ms) {
  this->state_.set_stale_after_ms(stale_after_ms);
  this->publish_stale_states();
  this->schedule_stale_state_publish();
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
  ESP_LOGV(TAG, "Received rtl_433 message: %s", message);
  json::parse_json(message, [this](JsonObject root) {
    const char *model = root["model"] | "";
    if (std::strcmp(model, "status") == 0) {
      return true;
    }

    ::esphome::rtl433_native::DecodedPacket packet;
    packet.model = model;
    const auto id_value = root["id"];
    if (id_value.is<const char *>()) {
      packet.id = id_value.as<const char *>();
    } else if (id_value.is<int>()) {
      packet.id = std::to_string(id_value.as<int>());
    } else if (id_value.is<unsigned int>()) {
      packet.id = std::to_string(id_value.as<unsigned int>());
    } else if (id_value.is<uint32_t>()) {
      packet.id = std::to_string(id_value.as<uint32_t>());
    }

    const auto channel_value = root["channel"];
    const auto subtype_value = root["subtype"];
    if (channel_value.is<const char *>()) {
      packet.channel = channel_value.as<const char *>();
    } else if (channel_value.is<int>()) {
      packet.channel = std::to_string(channel_value.as<int>());
    } else if (subtype_value.is<int>()) {
      packet.channel = std::to_string(subtype_value.as<int>());
    } else if (subtype_value.is<const char *>()) {
      packet.channel = subtype_value.as<const char *>();
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
    const auto humidity_value = root["humidity"];
    packet.humidity = humidity_value | NAN;
    const auto battery_ok_value = root["battery_ok"];
    if (battery_ok_value.is<bool>()) {
      packet.battery = battery_ok_value.as<bool>() ? 100.0f : 0.0f;
    } else if (battery_ok_value.is<int>()) {
      packet.battery = battery_ok_value.as<int>() ? 100.0f : 0.0f;
    } else if (battery_ok_value.is<float>()) {
      packet.battery = battery_ok_value.as<float>() ? 100.0f : 0.0f;
    }

    const auto rssi_value = root["rssi"];
    packet.rssi = rssi_value | 0;
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
      const std::string next_packet_value =
          ::esphome::rtl433_native::format_sensor_key({packet.model, packet.channel, packet.id});
      this->last_packet_sensor_->publish_state(next_packet_value);
    }

    if (result == ::esphome::rtl433_native::PacketResult::MATCHED_KNOWN) {
      const uint32_t last_updated = this->current_timestamp();
      const auto &matched_logical_keys = this->state_.matched_logical_keys();
      const auto &changed_logical_keys = this->state_.changed_logical_keys();
      for (const auto &logical_key : matched_logical_keys) {
        this->pending_clock_age_restore_.erase(logical_key);
        this->update_last_updated(logical_key, last_updated);
        const bool value_changed =
            std::find(changed_logical_keys.begin(), changed_logical_keys.end(), logical_key) !=
            changed_logical_keys.end();
        const auto previous_save = this->last_state_save_ms_.find(logical_key);
        const uint32_t previous_save_ms =
            previous_save == this->last_state_save_ms_.end() ? 0 : previous_save->second;
        if (should_persist_logical_state(value_changed, packet.seen_ms, previous_save_ms,
                                         unchanged_state_save_interval_ms(this->state_.stale_after_ms()))) {
          this->save_state(logical_key);
          this->last_state_save_ms_[logical_key] = packet.seen_ms;
        }
        this->publish_state(logical_key);
      }
    } else if (result == ::esphome::rtl433_native::PacketResult::RECORDED_CANDIDATE ||
               result == ::esphome::rtl433_native::PacketResult::IGNORED_UNKNOWN) {
      this->unknown_packet_count_ += 1;
      if (this->unknown_packet_count_sensor_ != nullptr) {
        this->unknown_packet_count_sensor_->publish_state(this->unknown_packet_count_);
      }
    }

    this->queue_candidate_publish();
    this->schedule_stale_state_publish();
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
    auto mapping_preference =
        global_preferences->make_preference<SavedLogicalMapping>(saved_state_mapping_preference_key(logical_key), true);
    SavedLogicalMapping saved_mapping;
    const bool saved_mapping_available =
        mapping_preference.load(&saved_mapping) && saved_mapping.has_value &&
        saved_mapping.mapping_hash != 0;
    const auto current_mapping_hash = this->state_.mapping_hash(logical_key);
    const bool saved_mapping_matches =
        saved_mapping_available && current_mapping_hash.has_value() &&
        *current_mapping_hash == saved_mapping.mapping_hash;
    if (saved_mapping_available) {
      this->last_saved_state_mapping_hashes_[logical_key] = saved_mapping.mapping_hash;
    }
    if (!saved_mapping_available || !saved_mapping_matches) {
      continue;
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

  this->publish_stale_states();
  if (restored_any) {
    this->set_timeout("publish_restored_states", 2000, [this]() {
      for (const auto &logical_key : this->logical_keys_) {
        this->publish_state(logical_key);
      }
    });
  }
  this->schedule_stale_state_publish();
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
  this->schedule_stale_state_publish();
}

uint32_t Gateway::current_timestamp() {
  ESPTime now = this->time_->utcnow();
  if (now.is_valid()) {
    return static_cast<uint32_t>(now.timestamp);
  }
  return resolve_projected_timestamp(this->time_sync_epoch_, this->time_sync_ms_, millis());
}

void Gateway::update_last_updated(const std::string &logical_key, uint32_t last_updated) {
  const auto previous_last_updated = this->last_updated_values_.find(logical_key);
  const uint32_t previous_timestamp =
      previous_last_updated == this->last_updated_values_.end() ? 0 : previous_last_updated->second;
  const uint32_t adjusted_last_updated = resolve_last_updated_timestamp(last_updated, previous_timestamp);
  if (adjusted_last_updated > 0) {
    this->last_updated_values_[logical_key] = adjusted_last_updated;
  }
}

void Gateway::queue_candidate_publish() {
  if (this->candidate_publish_pending_) {
    return;
  }
  this->candidate_publish_pending_ = true;
  this->set_timeout("publish_candidates", 50, [this]() { this->flush_pending_candidate_publish(); });
}

void Gateway::flush_pending_candidate_publish() {
  if (!this->candidate_publish_pending_) {
    return;
  }
  this->candidate_publish_pending_ = false;
  this->publish_candidates();
}

void Gateway::save_state(const std::string &logical_key) {
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
  const auto last_updated_item = this->last_updated_values_.find(logical_key);
  if (last_updated_item != this->last_updated_values_.end()) {
    saved.last_updated = last_updated_item->second;
  }
  preference_item->second.save(&saved);
  const auto mapping_hash = this->state_.mapping_hash(logical_key);
  const auto previous_mapping_item = this->last_saved_state_mapping_hashes_.find(logical_key);
  const uint32_t previous_mapping_hash =
      previous_mapping_item == this->last_saved_state_mapping_hashes_.end() ? 0 : previous_mapping_item->second;
  if (mapping_hash.has_value() && *mapping_hash != previous_mapping_hash) {
    SavedLogicalMapping saved_mapping;
    saved_mapping.has_value = true;
    saved_mapping.mapping_hash = *mapping_hash;
    auto mapping_preference =
        global_preferences->make_preference<SavedLogicalMapping>(saved_state_mapping_preference_key(logical_key), true);
    mapping_preference.save(&saved_mapping);
    this->last_saved_state_mapping_hashes_[logical_key] = *mapping_hash;
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

void Gateway::schedule_stale_state_publish() {
  const auto delay_ms = this->state_.next_stale_state_publish_delay_ms(millis());
  if (!delay_ms.has_value()) {
    return;
  }
  this->set_timeout("publish_stale_states", *delay_ms, [this]() {
    this->publish_stale_states();
    this->schedule_stale_state_publish();
  });
}

void MappingText::setup() {
  this->preference_ = global_preferences->make_preference<SavedMappingText>(
      mapping_preference_key(this->logical_key_), true);

  SavedMappingText saved;
  if (this->preference_.load(&saved) && saved.has_value) {
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
  if (is_blank_mapping_text(value)) {
    this->publish_state("");
    if (this->parent_ != nullptr) {
      this->parent_->set_override(this->logical_key_, "");
    }
    if (save) {
      SavedMappingText saved;
      saved.has_value = true;
      saved.value[0] = '\0';
      this->preference_.save(&saved);
    }
    return;
  }

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
