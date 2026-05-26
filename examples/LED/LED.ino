#include "MultiSensorParser.h"
#include "Arduino.h"

MultiSensorParser sensors;

// 任意 1 号通道超过阈值就点亮 LED
const float THRESHOLD = 200.0f;
const uint8_t WATCH_CHANNEL = 0; // 监测第 1 个通道（index 从 0 开始）

void setup()
{
    sensors.begin(Serial, 1000000);

    pinMode(13, OUTPUT);
    digitalWrite(13, LOW);
}

void loop()
{
    sensors.update();

    float v = sensors.getLatestValue(WATCH_CHANNEL);
    if (v < THRESHOLD) {
        digitalWrite(13, HIGH);
    } else {
        digitalWrite(13, LOW);
    }
}
