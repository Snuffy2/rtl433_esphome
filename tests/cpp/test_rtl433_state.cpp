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

}  // namespace

int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  return 0;
}
