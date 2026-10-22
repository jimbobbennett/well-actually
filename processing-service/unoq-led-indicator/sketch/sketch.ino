#include <Arduino_LED_Matrix.h>

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

void draw_pulse(uint8_t brightness) {
    uint8_t frame[104];
    for (uint8_t pixel = 0; pixel < 104; ++pixel) {
        frame[pixel] = microphone_icon[pixel] == 0 ? 0 : brightness;
    }
    matrix.draw(frame);
}

void setup() {
    matrix.begin();
    matrix.setGrayscaleBits(3);
}

void loop() {
    for (uint8_t brightness = 1; brightness <= 7; ++brightness) {
        draw_pulse(brightness);
        delay(90);
    }
    for (int brightness = 6; brightness >= 1; --brightness) {
        draw_pulse(static_cast<uint8_t>(brightness));
        delay(90);
    }
}
