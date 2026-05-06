#pragma once

#include <stdint.h>

// Provide compatibility wrappers for older RadioLib versions that call legacy
// LEDC APIs removed from newer ESP32 Arduino cores.
static inline void ledcAttachPin(uint8_t pin, uint8_t channel) {
  (void) pin;
  (void) channel;
}

static inline void ledcDetachPin(uint8_t pin) {
  (void) pin;
}
