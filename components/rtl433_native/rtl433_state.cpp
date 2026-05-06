#include "rtl433_state.h"

#include <cmath>
#include <sstream>

namespace rtl433_native {

std::optional<SensorKey> parse_sensor_key(const std::string &value) {
  std::stringstream stream(value);
  std::string model;
  std::string channel;
  std::string id;
  std::string extra;

  if (!std::getline(stream, model, '/') || !std::getline(stream, channel, '/') ||
      !std::getline(stream, id, '/') || std::getline(stream, extra, '/')) {
    return std::nullopt;
  }
  if (model.empty() || channel.empty() || id.empty()) {
    return std::nullopt;
  }
  return SensorKey{model, channel, id};
}

std::string format_sensor_key(const SensorKey &key) {
  return key.model + "/" + key.channel + "/" + key.id;
}

bool matches_key(const DecodedPacket &packet, const SensorKey &key) {
  return packet.model == key.model && packet.channel == key.channel && packet.id == key.id;
}

void GatewayState::set_mapping(const std::string &logical_key, const std::string &sensor_key) {
  auto parsed = parse_sensor_key(sensor_key);
  if (!parsed.has_value()) {
    return;
  }
  mappings_[logical_key] = *parsed;
  logical_states_.try_emplace(logical_key);
}

const LogicalSensorState *GatewayState::logical_sensor(const std::string &logical_key) const {
  auto item = logical_states_.find(logical_key);
  if (item == logical_states_.end()) {
    return nullptr;
  }
  return &item->second;
}

PacketResult GatewayState::process_packet(const DecodedPacket &packet) {
  if (packet.model.empty() || packet.id.empty()) {
    return PacketResult::REJECTED_INVALID;
  }

  for (const auto &[logical_key, sensor_key] : mappings_) {
    if (!matches_key(packet, sensor_key)) {
      continue;
    }
    auto &state = logical_states_[logical_key];
    state.has_value = true;
    state.temperature_f = packet.temperature_f;
    state.humidity = packet.humidity;
    state.battery = packet.battery;
    state.rssi = packet.rssi;
    state.last_seen_ms = packet.seen_ms;
    return PacketResult::MATCHED_KNOWN;
  }

  return PacketResult::IGNORED_UNKNOWN;
}

}  // namespace rtl433_native
