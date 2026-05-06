#include "rtl433_native.h"

#include <cmath>
#include <limits>

#include "esphome/components/json/json_util.h"
#include "esphome/core/log.h"

namespace esphome::rtl433_native {

static const char *const TAG = "rtl433_native";

Gateway *Gateway::instance_ = nullptr;

Gateway::Gateway() { instance_ = this; }

void Gateway::setup() {
  this->rf_.initReceiver(RF_MODULE_RECEIVER_GPIO, RF_MODULE_FREQUENCY);
  this->rf_.setCallback(&Gateway::process_dispatch, this->buffer_, sizeof(this->buffer_));
  this->rf_.enableReceiver();
}

void Gateway::loop() {
  this->rf_.loop();
  this->publish_stale_states();
}

void Gateway::dump_config() {
  ESP_LOGCONFIG(TAG, "RTL433 native gateway");
  ESP_LOGCONFIG(TAG, "  Candidate limit: %u",
                static_cast<unsigned>(this->state_.candidate_limit()));
}

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

void Gateway::add_mapping(const std::string &logical_key, const std::string &model,
                         const std::string &channel, const std::string &id) {
  this->state_.set_mapping(logical_key, model + "/" + channel + "/" + id);
  this->entities_.try_emplace(logical_key);
}

void Gateway::set_override(const std::string &logical_key, const std::string &sensor_key) {
  this->entities_.try_emplace(logical_key);
  this->state_.set_mapping(logical_key, sensor_key);
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

void Gateway::set_battery_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].battery = sensor;
}

void Gateway::set_rssi_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].rssi = sensor;
}

void Gateway::set_stale_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor) {
  this->entities_[logical_key].stale = sensor;
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

void Gateway::set_unknown_packet_count_sensor(sensor::Sensor *sensor) {
  this->unknown_packet_count_sensor_ = sensor;
}

void Gateway::set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor) {
  this->discovery_enabled_sensor_ = sensor;
  if (this->discovery_enabled_sensor_ != nullptr) {
    this->discovery_enabled_sensor_->publish_state(this->state_.discovery_enabled());
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

    ::rtl433_native::DecodedPacket packet;
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

    if (root["temperature_F"].is<float>()) {
      packet.temperature_f = root["temperature_F"].as<float>();
    } else if (root["temperature_1_F"].is<float>()) {
      packet.temperature_f = root["temperature_1_F"].as<float>();
    } else if (root["temperature_F"].is<int>()) {
      packet.temperature_f = static_cast<float>(root["temperature_F"].as<int>());
    } else if (root["temperature_1_F"].is<int>()) {
      packet.temperature_f = static_cast<float>(root["temperature_1_F"].as<int>());
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

    const ::rtl433_native::PacketResult result = this->state_.process_packet(packet);
    if (result == ::rtl433_native::PacketResult::REJECTED_INVALID) {
      ESP_LOGW(TAG, "Rejected invalid rtl_433 packet: %s", packet.model.c_str());
      return true;
    }

    this->packet_count_ += 1;
    if (this->packet_count_sensor_ != nullptr) {
      this->packet_count_sensor_->publish_state(this->packet_count_);
    }

    if (this->last_packet_sensor_ != nullptr) {
      this->last_packet_sensor_->publish_state(
          ::rtl433_native::format_sensor_key({packet.model, packet.channel, packet.id}));
    }

    if (result == ::rtl433_native::PacketResult::MATCHED_KNOWN) {
      for (const auto &entry : this->entities_) {
        const auto &logical_key = entry.first;
        const auto *logical = this->state_.logical_sensor(logical_key);
        if (logical != nullptr && logical->last_seen_ms == packet.seen_ms) {
          this->publish_state(logical_key);
        }
      }
    } else if (result == ::rtl433_native::PacketResult::RECORDED_CANDIDATE ||
               result == ::rtl433_native::PacketResult::IGNORED_UNKNOWN) {
      this->unknown_packet_count_ += 1;
      if (this->unknown_packet_count_sensor_ != nullptr) {
        this->unknown_packet_count_sensor_->publish_state(this->unknown_packet_count_);
      }
    }

    this->publish_candidates();
    return true;
  });
}

void Gateway::publish_state(const std::string &logical_key) {
  const auto entities_item = this->entities_.find(logical_key);
  const auto *logical = this->state_.logical_sensor(logical_key);
  if (entities_item == this->entities_.end() || logical == nullptr || !logical->has_value) {
    return;
  }

  const EntitySet &entities = entities_item->second;
  if (entities.temperature != nullptr && !std::isnan(logical->temperature_f)) {
    entities.temperature->publish_state(logical->temperature_f);
  }
  if (entities.humidity != nullptr && !std::isnan(logical->humidity)) {
    entities.humidity->publish_state(logical->humidity);
  }
  if (entities.battery != nullptr && !std::isnan(logical->battery)) {
    entities.battery->publish_state(logical->battery);
  }
  if (entities.rssi != nullptr) {
    entities.rssi->publish_state(logical->rssi);
  }
  if (entities.stale != nullptr) {
    entities.stale->publish_state(false);
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
        (index < candidates.size()) ? ::rtl433_native::format_candidate(candidates[index]) : "";
    if (this->last_candidate_values_[index] == next_value) {
      continue;
    }
    this->last_candidate_values_[index] = next_value;
    if (index < candidates.size()) {
      sensor->publish_state(next_value);
    } else {
      sensor->publish_state(next_value);
    }
  }
}

void Gateway::publish_stale_states() {
  const uint32_t now = millis();
  for (auto &[logical_key, entities] : this->entities_) {
    if (entities.stale != nullptr) {
      const bool stale = this->state_.is_stale(logical_key, now);
      if (!entities.stale_initialized || entities.last_stale != stale) {
        entities.last_stale = stale;
        entities.stale_initialized = true;
        entities.stale->publish_state(stale);
      }
    }
  }
}

}  // namespace esphome::rtl433_native
