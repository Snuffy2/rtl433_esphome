#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include "../../components/rtl433_native/rtl433_state.h"

namespace {

namespace rtl433 = esphome::rtl433_native;

void require(bool condition, const std::string &message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

bool keys_include(const std::vector<std::string> &keys, const std::string &logical_key) {
  return std::find(keys.begin(), keys.end(), logical_key) != keys.end();
}

rtl433::DecodedPacket packet_for_key(
    const std::string &model, const std::string &channel, const std::string &id, uint32_t seen_ms) {
  rtl433::DecodedPacket packet;
  packet.model = model;
  packet.channel = channel;
  packet.id = id;
  packet.seen_ms = seen_ms;
  return packet;
}

rtl433::LogicalSensorState restored_state(float temperature_f, uint32_t last_seen_ms) {
  rtl433::LogicalSensorState state;
  state.has_value = true;
  state.temperature_f = temperature_f;
  state.last_seen_ms = last_seen_ms;
  return state;
}

void test_key_parsing() {
  auto key = rtl433::parse_sensor_key("LaCrosse-TX141THBv2/0/203");
  require(key.has_value(), "expected valid LaCrosse key");
  require(key->model == "LaCrosse-TX141THBv2", "wrong parsed model");
  require(key->channel == "0", "wrong parsed channel");
  require(key->id == "203", "wrong parsed id");
  require(!rtl433::parse_sensor_key("LaCrosse-TX141THBv2/203").has_value(),
          "expected malformed key to fail");
}

void test_known_packet_updates_logical_sensor() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 1000);
  packet.temperature_f = 34.16f;
  packet.humidity = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected known packet match");

  const auto *logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state");
  require(std::fabs(logical->temperature_f - 34.16f) < 0.001f, "wrong temperature");
  require(logical->last_seen_ms == 1000, "wrong last seen timestamp");
}

void test_repeated_packet_refreshes_last_seen_without_reporting_value_change() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 1000);
  packet.temperature_f = 34.16f;
  packet.humidity = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;

  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected first known packet match");
  require(keys_include(state.changed_logical_keys(), "garage_combo_fridge"),
          "first packet should be persistence-worthy");

  packet.seen_ms = 2000;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected repeated known packet match");
  require(!keys_include(state.changed_logical_keys(), "garage_combo_fridge"),
          "same-value packet should not be persistence-worthy");

  const auto *logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state");
  require(logical->last_seen_ms == 2000, "same-value packet should still refresh last seen");

  packet.rssi = -67;
  packet.seen_ms = 2500;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected RSSI-only known packet match");
  require(!keys_include(state.changed_logical_keys(), "garage_combo_fridge"),
          "RSSI-only packet should not be persistence-worthy");

  logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state after RSSI-only packet");
  require(logical->rssi == -67, "RSSI-only packet should still update live RSSI");

  packet.temperature_f = 34.52f;
  packet.seen_ms = 3000;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected changed known packet match");
  require(keys_include(state.changed_logical_keys(), "garage_combo_fridge"),
          "changed sensor value should be persistence-worthy");
  logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state after changed packet");
  require(std::fabs(logical->temperature_f - 34.52f) < 0.001f, "changed packet should update temperature");
  require(logical->last_seen_ms == 3000, "changed packet should update last seen");
}

void test_same_millisecond_packets_report_only_current_matches() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88");

  rtl433::DecodedPacket fridge_packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 5000);
  fridge_packet.temperature_f = 34.16f;
  fridge_packet.humidity = 10.0f;
  fridge_packet.battery = 100.0f;
  fridge_packet.rssi = -70;

  require(state.process_packet(fridge_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected first same-ms packet match");
  require(keys_include(state.matched_logical_keys(), "garage_combo_fridge"), "expected first packet to match fridge");
  require(!keys_include(state.matched_logical_keys(), "garage_combo_freezer"), "first packet should not match freezer");

  rtl433::DecodedPacket freezer_packet = packet_for_key("TFA-303221", "2", "88", 5000);
  freezer_packet.temperature_f = 0.5f;
  freezer_packet.humidity = 44.0f;
  freezer_packet.battery = 100.0f;
  freezer_packet.rssi = -67;

  require(state.process_packet(freezer_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected second same-ms packet match");
  require(keys_include(state.matched_logical_keys(), "garage_combo_freezer"), "expected second packet to match freezer");
  require(!keys_include(state.matched_logical_keys(), "garage_combo_fridge"),
          "same-ms second packet should not report the previous logical key");
}

void test_synonym_key_updates_logical_sensor() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "1", "88", 2500);
  packet.temperature_f = 0.5f;
  packet.humidity = 44.0f;
  packet.battery = 100.0f;
  packet.rssi = -67;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected synonym packet match");

  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical sensor state");
  require(logical->has_value, "expected synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 0.5f) < 0.001f, "wrong synonym temperature");
  require(logical->last_seen_ms == 2500, "wrong synonym last seen timestamp");
}

void test_mapping_list_updates_from_primary_and_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::DecodedPacket primary_packet = packet_for_key("TFA-303221", "2", "88", 1000);
  primary_packet.temperature_f = 12.25f;
  require(state.process_packet(primary_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected primary mapping list key to match");

  rtl433::DecodedPacket synonym_packet = packet_for_key("LaCrosse-TX141THBv2", "1", "88", 2000);
  synonym_packet.temperature_f = 13.5f;
  require(state.process_packet(synonym_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected synonym mapping list key to match");

  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical sensor state");
  require(logical->has_value, "expected mapping list packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 13.5f) < 0.001f, "wrong mapping list temperature");
  require(logical->last_seen_ms == 2000, "wrong mapping list last seen timestamp");
}

void test_spaced_mapping_list_updates_from_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", " TFA-303221/2/88 ; LaCrosse-TX141THBv2/1/88 ");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "1", "88", 3000);
  packet.temperature_f = 14.75f;

  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected whitespace-padded synonym mapping to match");
  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical state for spaced mapping");
  require(logical->has_value, "expected spaced synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 14.75f) < 0.001f, "wrong spaced mapping temperature");
}

void test_slash_spaced_mapping_list_updates_from_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221 / 2 / 88 ; LaCrosse-TX141THBv2 / 1 / 88");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "1", "88", 3500);
  packet.temperature_f = 15.75f;

  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected slash-padded synonym mapping to match");
  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical state for slash-spaced mapping");
  require(logical->has_value, "expected slash-spaced synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 15.75f) < 0.001f, "wrong slash-spaced mapping temperature");
}

void test_remapping_clears_old_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket original_packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 1000);
  original_packet.temperature_f = 34.16f;

  require(state.process_packet(original_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected initial packet match");

  const auto *before = state.logical_sensor("garage_combo_fridge");
  require(before != nullptr, "expected logical sensor state before remap");
  require(before->has_value, "expected value after first update");

  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/1/204");

  const auto *after_remap = state.logical_sensor("garage_combo_fridge");
  require(after_remap != nullptr, "expected logical sensor state after remap");
  require(!after_remap->has_value, "expected remap to clear old reading");
  require(after_remap->last_seen_ms == 0, "expected remap to clear old timestamp");

  require(state.process_packet(original_packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "expected old packet key to no longer match");
  const auto *after_old_packet = state.logical_sensor("garage_combo_fridge");
  require(after_old_packet != nullptr, "expected logical sensor state after old packet");
  require(!after_old_packet->has_value, "expected stale state to remain cleared after non-match");
}

void test_reapplying_same_mapping_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_freezer_2", "Acurite-986/2F/31274");

  rtl433::LogicalSensorState restored = restored_state(11.0f, 2000);
  restored.battery = 100.0f;
  restored.rssi = -87;
  state.restore_logical_state("garage_freezer_2", restored);

  state.set_mapping("garage_freezer_2", "Acurite-986/2F/31274");

  const auto *after = state.logical_sensor("garage_freezer_2");
  require(after != nullptr, "expected logical sensor state after same mapping");
  require(after->has_value, "expected same mapping to preserve restored reading");
  require(after->last_seen_ms == 2000, "expected same mapping to preserve last seen timestamp");
  require(!state.is_stale("garage_freezer_2", 3000), "expected restored reading to remain fresh");
}

void test_reordered_synonyms_preserve_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88;Acurite-986/2F/31274");

  rtl433::LogicalSensorState restored = restored_state(9.5f, 4000);
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;Acurite-986/2F/31274;LaCrosse-TX141THBv2/1/88");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after reordered synonyms");
  require(after->has_value, "expected reordered synonyms to preserve restored reading");
  require(after->last_seen_ms == 4000, "expected reordered synonyms to preserve last seen timestamp");
}

void test_reordered_primary_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::LogicalSensorState restored = restored_state(8.25f, 5000);
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/1/88;TFA-303221/2/88");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after reordered primary");
  require(after->has_value, "expected reordered primary to preserve restored reading");
  require(after->last_seen_ms == 5000, "expected reordered primary to preserve last seen timestamp");
}

void test_spaced_reordered_mapping_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::LogicalSensorState restored = restored_state(8.25f, 5000);
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", " LaCrosse-TX141THBv2/1/88 ; TFA-303221/2/88 ");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after spaced mapping");
  require(after->has_value, "expected spaced reordered mapping to preserve restored reading");
  require(after->last_seen_ms == 5000, "expected spaced mapping to preserve last seen timestamp");
}

void test_invalid_mapping_input_preserves_state_and_mapping() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 0);
  packet.temperature_f = 34.16f;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected known match");

  state.set_mapping("garage_combo_fridge", "not_a_valid_key");
  const auto *after_invalid = state.logical_sensor("garage_combo_fridge");
  require(after_invalid != nullptr, "expected invalid mapping to preserve logical state");
  require(after_invalid->has_value, "expected invalid mapping to preserve value");
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected old mapping to remain active after invalid mapping input");
}

void test_mapping_change_reporting() {
  rtl433::GatewayState state;

  require(state.set_mapping("garage_freezer_1", "Acurite-986/1R/11932"),
          "expected initial mapping to report a change");
  require(!state.set_mapping("garage_freezer_1", "Acurite-986/1R/11932"),
          "expected identical mapping to report no change");
  require(!state.set_mapping("garage_freezer_1", "not_a_valid_key"),
          "expected invalid mapping to report no change");
  require(state.set_mapping("garage_freezer_1", "Acurite-986/1R/55555"),
          "expected remapping to report a change");
}

void test_mapping_hash_uses_full_long_mapping() {
  std::string long_mapping_a = "Acurite-986/2F/35570";
  std::string long_mapping_b = "Acurite-986/2F/35570";
  for (int index = 0; index < 30; ++index) {
    long_mapping_a += ";LongModel/" + std::to_string(index) + "/1234567890";
    long_mapping_b += ";LongModel/" + std::to_string(index) + "/1234567890";
  }
  long_mapping_b += ";LongModel/31/changed-after-prefix";

  require(long_mapping_a.size() > 240, "expected long mapping to exceed text UI limit");
  require(long_mapping_b.size() > 240, "expected changed long mapping to exceed text UI limit");
  require(rtl433::sensor_mapping_hash(long_mapping_a) != rtl433::sensor_mapping_hash(long_mapping_b),
          "mapping hash should include bytes past the text UI limit");
}

void test_mapping_hash_is_cached_for_runtime_mapping() {
  rtl433::GatewayState state;
  require(!state.mapping_hash("garage_freezer_2").has_value(), "missing mapping should not have a hash");

  state.set_mapping("garage_freezer_2", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");
  const auto first_hash = state.mapping_hash("garage_freezer_2");
  require(first_hash.has_value(), "configured mapping should have a hash");

  state.set_mapping("garage_freezer_2", "LaCrosse-TX141THBv2/1/88;TFA-303221/2/88");
  const auto reordered_hash = state.mapping_hash("garage_freezer_2");
  require(reordered_hash.has_value(), "reordered mapping should have a hash");
  require(*first_hash == *reordered_hash, "equivalent mapping order should keep the same cached hash");

  state.set_mapping("garage_freezer_2", "Acurite-986/2F/35570");
  const auto remapped_hash = state.mapping_hash("garage_freezer_2");
  require(remapped_hash.has_value(), "remapped sensor should have a hash");
  require(*remapped_hash != *first_hash, "changed mapping should update the cached hash");
}

void test_persist_state_decision_throttles_unchanged_values() {
  require(rtl433::should_persist_logical_state(true, 2000, 1999, 60000),
          "changed values should always persist");
  require(rtl433::should_persist_logical_state(false, 2000, 0, 60000),
          "first unchanged value should persist");
  require(!rtl433::should_persist_logical_state(false, 59000, 1000, 60000),
          "unchanged values should wait for the throttle interval");
  require(rtl433::should_persist_logical_state(false, 61000, 1000, 60000),
          "unchanged values should persist at the throttle interval");
  require(!rtl433::should_persist_logical_state(false, 0x00000010, 0xFFFFFFF0, 60000),
          "wrapped unchanged values should still wait for the throttle interval");
}

void test_remap_accepts_next_packet_even_with_same_values() {
  rtl433::GatewayState state;
  state.set_mapping("garage_freezer_2", "Acurite-986/2F/35570");

  rtl433::DecodedPacket packet = packet_for_key("Acurite-986", "2F", "35570", 1000);
  packet.temperature_f = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected original mapping to match");

  state.set_mapping("garage_freezer_2", "Acurite-986/2F/35571");
  packet.id = "35571";
  packet.seen_ms = 2000;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected remapped packet to match");
  const auto *logical = state.logical_sensor("garage_freezer_2");
  require(logical != nullptr, "expected logical sensor state after remapped packet");
  require(logical->has_value, "expected remapped packet to repopulate logical state");
  require(logical->last_seen_ms == 2000, "expected remapped packet to refresh last seen");
}

void test_duplicate_mappings_update_both() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 1500);
  packet.temperature_f = 55.55f;
  packet.humidity = 11.0f;
  packet.battery = 99.0f;
  packet.rssi = -55;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected duplicate matches to succeed");

  const auto *fridge = state.logical_sensor("garage_combo_fridge");
  const auto *freezer = state.logical_sensor("garage_combo_freezer");
  require(fridge != nullptr, "expected fridge logical state");
  require(freezer != nullptr, "expected freezer logical state");
  require(fridge->has_value && freezer->has_value, "expected both logical sensors to update");
  require(std::fabs(fridge->temperature_f - 55.55f) < 0.001f, "wrong fridge temperature");
  require(std::fabs(freezer->temperature_f - 55.55f) < 0.001f, "wrong freezer temperature");
}

void test_invalid_packet_is_rejected() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket invalid_model;
  invalid_model.id = "203";
  invalid_model.channel = "0";
  require(state.process_packet(invalid_model) == rtl433::PacketResult::REJECTED_INVALID,
          "expected empty model packet to be rejected");

  rtl433::DecodedPacket invalid_id;
  invalid_id.model = "LaCrosse-TX141THBv2";
  invalid_id.channel = "0";
  require(state.process_packet(invalid_id) == rtl433::PacketResult::REJECTED_INVALID,
          "expected empty id packet to be rejected");
}

void test_unmatched_packet_is_ignored() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "1", "999", 0);
  require(state.process_packet(packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "expected unmatched packet to be ignored");
}

void test_unknowns_only_record_when_discovery_enabled() {
  rtl433::GatewayState state;
  state.set_candidate_limit(10);

  rtl433::DecodedPacket packet = packet_for_key("Acurite-986", "1R", "11932", 2000);
  packet.temperature_f = 75.0f;
  packet.battery = 100.0f;
  packet.rssi = -88;

  require(state.process_packet(packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "unknown packet should be ignored while discovery is disabled");
  require(state.candidates().empty(), "candidate table should be empty");

  state.set_discovery_enabled(true);
  require(state.process_packet(packet) == rtl433::PacketResult::RECORDED_CANDIDATE,
          "unknown packet should be recorded while discovery is enabled");
  require(state.candidates().size() == 1, "candidate table should have one row");
  require(state.candidates().front().packet_count == 1, "candidate count should start at one");
}

void test_candidates_are_grouped_capped_and_clearable() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_candidate_limit(2);

  for (int index = 0; index < 4; ++index) {
    const std::string channel = index == 2 ? "1" : std::to_string(index);
    const std::string id = index == 2 ? "101" : std::to_string(100 + index);
    rtl433::DecodedPacket packet = packet_for_key("Noise", channel, id, 1000 + static_cast<uint32_t>(index));
    packet.temperature_f = static_cast<float>(index);
    packet.rssi = -60 - index;
    state.process_packet(packet);
  }

  require(state.candidates().size() == 2, "candidate table should honor limit");
  require(state.candidates().front().last_seen_ms == 1003, "newest candidate should sort first");
  for (const auto &candidate : state.candidates()) {
    if (candidate.key.channel == "1" && candidate.key.id == "101") {
      require(candidate.packet_count == 2, "duplicate packet keys should group into one row");
      require(candidate.last_seen_ms == 1002, "grouped row should hold the latest seen timestamp");
    }
  }

  state.clear_candidates();
  require(state.candidates().empty(), "clear should empty candidate table");
}

void test_duplicate_mappings_record_matched_candidate_once() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet = packet_for_key("LaCrosse-TX141THBv2", "0", "203", 1500);
  packet.temperature_f = 55.55f;
  packet.humidity = 11.0f;
  packet.battery = 99.0f;
  packet.rssi = -55;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected duplicate matches to succeed");

  const auto *fridge = state.logical_sensor("garage_combo_fridge");
  const auto *freezer = state.logical_sensor("garage_combo_freezer");
  require(fridge != nullptr && freezer != nullptr, "expected both logical sensor states");
  require(fridge->has_value && freezer->has_value, "expected both logical sensors to update");
  require(fridge->temperature_f == freezer->temperature_f, "logical sensor temperatures should match");

  require(state.candidates().size() == 1, "duplicate mapped packet should create one matched candidate row");
  require(state.candidates().front().packet_count == 1, "duplicate mapped packet should count as one packet");
}

void test_mapping_override_replaces_default_key() {
  rtl433::GatewayState state;
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/11932");
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/55555");

  rtl433::DecodedPacket old_packet = packet_for_key("Acurite-986", "1R", "11932", 1000);
  old_packet.temperature_f = 75.0f;
  require(state.process_packet(old_packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "old mapping should no longer match");

  rtl433::DecodedPacket new_packet = old_packet;
  new_packet.id = "55555";
  new_packet.temperature_f = 10.0f;
  new_packet.seen_ms = 2000;
  require(state.process_packet(new_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "new mapping should match");
}

void test_stale_detection_uses_last_seen() {
  rtl433::GatewayState state;
  state.set_stale_after_ms(600000);
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88");

  rtl433::DecodedPacket packet = packet_for_key("TFA-303221", "2", "88", 1000);
  packet.temperature_f = 1.22f;
  state.process_packet(packet);

  require(!state.is_stale("garage_combo_freezer", 601000), "exact threshold should not be stale");
  require(!state.is_stale("garage_combo_freezer", 600999), "sensor should not be stale yet");
  require(state.is_stale("garage_combo_freezer", 601001), "sensor should be stale after threshold");
}

void test_stale_detection_wraps_with_uint32_delta() {
  rtl433::GatewayState state;
  state.set_stale_after_ms(1000);
  state.set_mapping("garage_combo_freezer", "Noise/0/1");

  rtl433::DecodedPacket packet = packet_for_key("Noise", "0", "1", 0xFFFFFF00);
  state.process_packet(packet);

  require(!state.is_stale("garage_combo_freezer", 0xFFFFFF80), "post-wrap packets before threshold should not be stale");
  require(state.is_stale("garage_combo_freezer", 0x00000500), "post-wrap packets after threshold should be stale");
}

void test_candidate_order_is_deterministic_for_equal_seen_time() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);

  rtl433::DecodedPacket apple = packet_for_key("Apple", "1", "10", 5000);
  state.process_packet(apple);

  rtl433::DecodedPacket zebra = packet_for_key("Zebra", "0", "1", 5000);
  state.process_packet(zebra);

  require(state.candidates().size() == 2, "candidate table should capture both equal-time rows");
  require(state.candidates().front().key.model == "Apple", "earlier alpha model should sort first for equal last_seen");
  require(state.candidates().front().key.channel == "1", "expected deterministic model order");
  require(state.candidates()[1].key.model == "Zebra", "later alpha model should sort after with equal last_seen");
}

void test_candidates_pruned_by_age() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_stale_after_ms(1000);

  rtl433::DecodedPacket old_candidate = packet_for_key("OldSensor", "0", "111", 1000);
  state.process_packet(old_candidate);

  rtl433::DecodedPacket recent_candidate = packet_for_key("NewSensor", "0", "222", 3000);
  state.process_packet(recent_candidate);

  require(state.candidates().size() == 1, "candidate age window should remove stale rows");
  require(state.candidates().front().key.model == "NewSensor", "only the recent candidate should remain");
}

void test_candidate_age_pruning_is_uint32_wrap_safe() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_stale_after_ms(200);

  rtl433::DecodedPacket pre_wrap_candidate = packet_for_key("Rollover", "0", "001", 0xFFFFFF80);
  state.process_packet(pre_wrap_candidate);

  rtl433::DecodedPacket post_wrap_candidate = packet_for_key("Fresh", "0", "002", 0x00000110);
  state.process_packet(post_wrap_candidate);

  require(state.candidates().size() == 1, "uint32 wrap should not prevent age pruning");
  require(state.candidates().front().key.id == "002", "newer wrapped candidate should be retained");
}

void test_last_updated_resolution_does_not_create_future_timestamp() {
  uint32_t adjusted = 1700000000;
  for (uint32_t index = 0; index < 90; ++index) {
    adjusted = rtl433::resolve_last_updated_timestamp(1700000000, adjusted);
  }

  require(adjusted == 1700000000, "last_updated resolution should not move past wall clock time");
}

void test_last_updated_resolution_preserves_previous_when_clock_is_invalid() {
  const uint32_t adjusted = rtl433::resolve_last_updated_timestamp(0, 1700000000);

  require(adjusted == 1700000000, "invalid current timestamp should preserve previous last_updated value");
}

void test_projected_timestamp_uses_cached_sync_epoch() {
  const uint32_t resolved = rtl433::resolve_projected_timestamp(1700000000, 1000, 61000);

  require(resolved == 1700000060, "invalid clock timestamp should fall back to cached projected timestamp");
}

void test_projected_timestamp_returns_zero_without_cache() {
  const uint32_t resolved = rtl433::resolve_projected_timestamp(0, 1000, 61000);

  require(resolved == 0, "missing clock timestamp and cache should remain unavailable");
}

void test_restored_last_seen_marks_old_saved_reading_stale() {
  const uint32_t stale_after_ms = 3600000;
  const uint32_t now_ms = 43200000;
  const uint32_t current_timestamp = 1781395200;
  const uint32_t saved_last_updated = current_timestamp - 86400;

  const uint32_t restored_last_seen =
      rtl433::resolve_restored_last_seen_ms(saved_last_updated, current_timestamp, now_ms, stale_after_ms);

  require(static_cast<uint32_t>(now_ms - restored_last_seen) > stale_after_ms,
          "old persisted readings should restore as stale");
}

void test_restored_last_seen_preserves_recent_saved_age() {
  const uint32_t stale_after_ms = 3600000;
  const uint32_t now_ms = 43200000;
  const uint32_t current_timestamp = 1781395200;
  const uint32_t saved_last_updated = current_timestamp - 600;

  const uint32_t restored_last_seen =
      rtl433::resolve_restored_last_seen_ms(saved_last_updated, current_timestamp, now_ms, stale_after_ms);

  require(now_ms - restored_last_seen == 600000, "recent persisted readings should restore with real age");
}

void test_restored_last_seen_falls_back_to_fresh_without_valid_clock_age() {
  const uint32_t stale_after_ms = 3600000;
  const uint32_t now_ms = 43200000;
  const uint32_t current_timestamp = 1781395200;

  require(rtl433::resolve_restored_last_seen_ms(0, current_timestamp, now_ms, stale_after_ms) == now_ms,
          "missing saved timestamp should restore with previous fresh behavior");
  require(rtl433::resolve_restored_last_seen_ms(current_timestamp - 600, 0, now_ms, stale_after_ms) == now_ms,
          "missing current timestamp should restore with previous fresh behavior");
  require(
      rtl433::resolve_restored_last_seen_ms(current_timestamp + 1, current_timestamp, now_ms, stale_after_ms) == now_ms,
      "future saved timestamp should restore with previous fresh behavior");
}

}  // namespace

int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  test_repeated_packet_refreshes_last_seen_without_reporting_value_change();
  test_same_millisecond_packets_report_only_current_matches();
  test_synonym_key_updates_logical_sensor();
  test_mapping_list_updates_from_primary_and_synonym();
  test_spaced_mapping_list_updates_from_synonym();
  test_slash_spaced_mapping_list_updates_from_synonym();
  test_remapping_clears_old_reading();
  test_reapplying_same_mapping_preserves_restored_reading();
  test_reordered_synonyms_preserve_restored_reading();
  test_reordered_primary_preserves_restored_reading();
  test_spaced_reordered_mapping_preserves_restored_reading();
  test_invalid_mapping_input_preserves_state_and_mapping();
  test_mapping_change_reporting();
  test_mapping_hash_uses_full_long_mapping();
  test_mapping_hash_is_cached_for_runtime_mapping();
  test_persist_state_decision_throttles_unchanged_values();
  test_remap_accepts_next_packet_even_with_same_values();
  test_duplicate_mappings_update_both();
  test_invalid_packet_is_rejected();
  test_unmatched_packet_is_ignored();
  test_unknowns_only_record_when_discovery_enabled();
  test_candidates_are_grouped_capped_and_clearable();
  test_duplicate_mappings_record_matched_candidate_once();
  test_mapping_override_replaces_default_key();
  test_stale_detection_uses_last_seen();
  test_stale_detection_wraps_with_uint32_delta();
  test_candidate_order_is_deterministic_for_equal_seen_time();
  test_candidates_pruned_by_age();
  test_candidate_age_pruning_is_uint32_wrap_safe();
  test_last_updated_resolution_does_not_create_future_timestamp();
  test_last_updated_resolution_preserves_previous_when_clock_is_invalid();
  test_projected_timestamp_uses_cached_sync_epoch();
  test_projected_timestamp_returns_zero_without_cache();
  test_restored_last_seen_marks_old_saved_reading_stale();
  test_restored_last_seen_preserves_recent_saved_age();
  test_restored_last_seen_falls_back_to_fresh_without_valid_clock_age();
  return 0;
}
