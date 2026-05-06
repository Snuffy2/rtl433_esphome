#include "rtl433_state.h"

#include <algorithm>
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

std::string format_candidate(const CandidateRow &candidate) {
  std::string value = format_sensor_key(candidate.key);
  value += " temp=" + std::to_string(candidate.temperature_f);
  value += " hum=" + std::to_string(candidate.humidity);
  value += " batt=" + std::to_string(candidate.battery);
  value += " rssi=" + std::to_string(candidate.rssi);
  value += " first=" + std::to_string(candidate.first_seen_ms);
  value += " last=" + std::to_string(candidate.last_seen_ms);
  value += " count=" + std::to_string(candidate.packet_count);
  value += candidate.matched_known ? " matched=1" : " matched=0";
  return value;
}

bool matches_key(const DecodedPacket &packet, const SensorKey &key) {
  return packet.model == key.model && packet.channel == key.channel && packet.id == key.id;
}

void GatewayState::set_mapping(const std::string &logical_key, const std::string &sensor_key) {
  auto parsed = parse_sensor_key(sensor_key);
  if (!parsed.has_value()) {
    mappings_.erase(logical_key);
    logical_states_.erase(logical_key);
    return;
  }
  mappings_[logical_key] = *parsed;
  logical_states_[logical_key] = LogicalSensorState{};
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

  bool matched = false;
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
    if (discovery_enabled_) {
      record_candidate(packet, true);
    }
    matched = true;
  }

  if (matched) {
    return PacketResult::MATCHED_KNOWN;
  }
  if (discovery_enabled_) {
    record_candidate(packet, false);
    return PacketResult::RECORDED_CANDIDATE;
  }
  return PacketResult::IGNORED_UNKNOWN;
}

bool GatewayState::is_stale(const std::string &logical_key, uint32_t now_ms) const {
  const auto *state = logical_sensor(logical_key);
  if (state == nullptr || !state->has_value) {
    return true;
  }
  return now_ms > state->last_seen_ms && now_ms - state->last_seen_ms > stale_after_ms_;
}

void GatewayState::record_candidate(const DecodedPacket &packet, bool matched_known) {
  SensorKey key{packet.model, packet.channel, packet.id};
  const std::string formatted = format_sensor_key(key);
  auto existing = std::find_if(candidates_.begin(), candidates_.end(), [&](const CandidateRow &row) {
    return format_sensor_key(row.key) == formatted;
  });

  if (existing == candidates_.end()) {
    CandidateRow row;
    row.key = key;
    row.first_seen_ms = packet.seen_ms;
    candidates_.push_back(row);
    existing = std::prev(candidates_.end());
  }

  existing->temperature_f = packet.temperature_f;
  existing->humidity = packet.humidity;
  existing->battery = packet.battery;
  existing->rssi = packet.rssi;
  existing->last_seen_ms = packet.seen_ms;
  existing->packet_count += 1;
  existing->matched_known = matched_known;

  std::sort(candidates_.begin(), candidates_.end(), [](const CandidateRow &left, const CandidateRow &right) {
    return left.last_seen_ms > right.last_seen_ms;
  });

  if (candidates_.size() > candidate_limit_) {
    candidates_.resize(candidate_limit_);
  }
}

}  // namespace rtl433_native
