#include <Arduino_LED_Matrix.h>
#include "Arduino_RouterBridge.h"

Arduino_LED_Matrix matrix;

const uint8_t microphone_icon[104] = {
    0, 0, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 7, 7, 7, 7, 7, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
};

const uint8_t lightning_bolt[104] = {
    0, 0, 0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 7, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 7, 7, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 7, 7, 0, 0, 0, 0, 0, 0, 0,
};

bool lightning_active = false;
bool lightning_drawn = false;
unsigned long lightning_until = 0;
const unsigned long lightning_duration_ms = 5000;
unsigned long last_pulse_update = 0;
uint8_t pulse_brightness = 1;
int8_t pulse_direction = 1;

bool show_lightning_bolt() {
    lightning_active = true;
    lightning_drawn = false;
    lightning_until = millis() + lightning_duration_ms;
    return true;
}

void draw_pulse(uint8_t brightness) {
    uint8_t frame[104];
    for (uint8_t pixel = 0; pixel < 104; ++pixel) {
        frame[pixel] = microphone_icon[pixel] == 0 ? 0 : brightness;
    }
    matrix.draw(frame);
}

void draw_lightning_bolt() {
    uint8_t frame[104];
    for (uint8_t pixel = 0; pixel < 104; ++pixel) {
        frame[pixel] = lightning_bolt[pixel];
    }
    matrix.draw(frame);
}

void setup() {
    matrix.begin();
    matrix.setGrayscaleBits(3);
    Bridge.begin();
    Bridge.provide_safe("show_lightning_bolt", show_lightning_bolt);
}

void loop() {
    const unsigned long now = millis();
    if (lightning_active) {
        if (static_cast<int32_t>(now - lightning_until) < 0) {
            if (!lightning_drawn) {
                draw_lightning_bolt();
                lightning_drawn = true;
            }
            return;
        }
        lightning_active = false;
        lightning_drawn = false;
        last_pulse_update = now;
    }

    if (now - last_pulse_update >= 90) {
        last_pulse_update = now;
        draw_pulse(pulse_brightness);
        if (pulse_brightness == 7) {
            pulse_direction = -1;
        } else if (pulse_brightness == 1) {
            pulse_direction = 1;
        }
        pulse_brightness = static_cast<uint8_t>(pulse_brightness + pulse_direction);
    }
}
