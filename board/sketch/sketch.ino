// SPDX-License-Identifier: MPL-2.0
// Arduino UNO Q - STM32 MCU Sketch for SensorLab Matrix & Sensor Bridge

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <vector>

Arduino_LED_Matrix matrix;

const uint8_t FRAME_ROWS = 8;                         // Matrix rows count
const uint8_t FRAME_COLS = 13;                        // Matrix columns count
const uint8_t FRAME_SIZE = FRAME_ROWS * FRAME_COLS;   // Total 8x13 LEDs

uint8_t frame[FRAME_SIZE] = {0};                      // Frame buffer

void setup() {
    // LED matrix initialize karo
    matrix.begin();
    matrix.setGrayscaleBits(3);                       // 3 bits brightness (0-7 values)
    matrix.clear();

    // Linux MPU ke sath bridge establish karo
    Bridge.begin();
    Bridge.provide("draw", draw);
}

void loop() {
    // Current frame buffer display pe continuously draw karo
    matrix.draw(frame);
    delay(10);
}

// Python side se jab naya frame aaye toh buffer update karo
void draw(std::vector<uint8_t> newFrame) {
    size_t len = min(newFrame.size(), (size_t)FRAME_SIZE);
    memcpy(frame, newFrame.data(), len);
}
