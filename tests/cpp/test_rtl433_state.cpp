#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include "components/rtl433_native/rtl433_state.h"

namespace {

void require(bool condition, const std::string &message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

void test_key_parsing() {
  auto key = rtl433_native::parse_sensor_key("LaCrosse-TX141THBv2/0/203");
  require(key.has_value(), "expected valid LaCrosse key");
  require(key->model == "LaCrosse-TX141THBv2", "wrong parsed model");
  require(key->channel == "0", "wrong parsed channel");
  require(key->id == "203", "wrong parsed id");
  require(!rtl433_native::parse_sensor_key("LaCrosse-TX141THBv2/203").has_value(),
          "expected malformed key to fail");
}

void test_known_packet_updates_logical_sensor() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 34.16f;
  packet.humidity = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;
  packet.seen_ms = 1000;

  auto result = state.process_packet(packet);
  require(result == rtl433_native::PacketResult::MATCHED_KNOWN, "expected known packet match");

  const auto *logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state");
  require(std::fabs(logical->temperature_f - 34.16f) < 0.001f, "wrong temperature");
  require(logical->last_seen_ms == 1000, "wrong last seen timestamp");
}

void test_remapping_clears_old_reading() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket original_packet;
  original_packet.model = "LaCrosse-TX141THBv2";
  original_packet.channel = "0";
  original_packet.id = "203";
  original_packet.temperature_f = 34.16f;
  original_packet.seen_ms = 1000;

  require(state.process_packet(original_packet) == rtl433_native::PacketResult::MATCHED_KNOWN,
          "expected initial packet match");

  const auto *before = state.logical_sensor("garage_combo_fridge");
  require(before != nullptr, "expected logical sensor state before remap");
  require(before->has_value, "expected value after first update");

  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/1/204");

  const auto *after_remap = state.logical_sensor("garage_combo_fridge");
  require(after_remap != nullptr, "expected logical sensor state after remap");
  require(!after_remap->has_value, "expected remap to clear old reading");
  require(after_remap->last_seen_ms == 0, "expected remap to clear old timestamp");

  require(state.process_packet(original_packet) == rtl433_native::PacketResult::IGNORED_UNKNOWN,
          "expected old packet key to no longer match");
  const auto *after_old_packet = state.logical_sensor("garage_combo_fridge");
  require(after_old_packet != nullptr, "expected logical sensor state after old packet");
  require(!after_old_packet->has_value, "expected stale state to remain cleared after non-match");
}

void test_invalid_mapping_input_clears_state_and_mapping() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 34.16f;
  require(state.process_packet(packet) == rtl433_native::PacketResult::MATCHED_KNOWN,
          "expected known match");

  state.set_mapping("garage_combo_fridge", "not_a_valid_key");
  require(state.logical_sensor("garage_combo_fridge") == nullptr,
          "expected invalid mapping to remove logical state");
  require(state.process_packet(packet) == rtl433_native::PacketResult::IGNORED_UNKNOWN,
          "expected stale mapping to be removed after invalid mapping input");
}

void test_duplicate_mappings_update_both() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 55.55f;
  packet.humidity = 11.0f;
  packet.battery = 99.0f;
  packet.rssi = -55;
  packet.seen_ms = 1500;

  auto result = state.process_packet(packet);
  require(result == rtl433_native::PacketResult::MATCHED_KNOWN, "expected duplicate matches to succeed");

  const auto *fridge = state.logical_sensor("garage_combo_fridge");
  const auto *freezer = state.logical_sensor("garage_combo_freezer");
  require(fridge != nullptr, "expected fridge logical state");
  require(freezer != nullptr, "expected freezer logical state");
  require(fridge->has_value && freezer->has_value, "expected both logical sensors to update");
  require(std::fabs(fridge->temperature_f - 55.55f) < 0.001f, "wrong fridge temperature");
  require(std::fabs(freezer->temperature_f - 55.55f) < 0.001f, "wrong freezer temperature");
}

void test_invalid_packet_is_rejected() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket invalid_model;
  invalid_model.id = "203";
  invalid_model.channel = "0";
  require(state.process_packet(invalid_model) == rtl433_native::PacketResult::REJECTED_INVALID,
          "expected empty model packet to be rejected");

  rtl433_native::DecodedPacket invalid_id;
  invalid_id.model = "LaCrosse-TX141THBv2";
  invalid_id.channel = "0";
  require(state.process_packet(invalid_id) == rtl433_native::PacketResult::REJECTED_INVALID,
          "expected empty id packet to be rejected");
}

void test_unmatched_packet_is_ignored() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "1";
  packet.id = "999";
  require(state.process_packet(packet) == rtl433_native::PacketResult::IGNORED_UNKNOWN,
          "expected unmatched packet to be ignored");
}

}  // namespace

int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  test_remapping_clears_old_reading();
  test_invalid_mapping_input_clears_state_and_mapping();
  test_duplicate_mappings_update_both();
  test_invalid_packet_is_rejected();
  test_unmatched_packet_is_ignored();
  return 0;
}
