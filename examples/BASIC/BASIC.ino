// BASIC.ino —— 适配 huda_serial.py 上位机的最小示例
// 一边用 MultiSensorParser 解析采集模组的二进制帧，
// 一边以 "=== Frame #N ===" + "Sxx: x.xxxxxx" 文本格式输出到串口。

#include "MultiSensorParser.h"
#include "Arduino.h"

MultiSensorParser sensors;

void setup()
{
    // 与采集模组、Python 脚本默认波特率保持一致：1000000
    sensors.begin(Serial, 1000000);
}

void loop()
{
    sensors.update();

    float values[MultiSensorParser::SENSOR_COUNT];
    if (sensors.readValues(values))
    {
        // 帧头：huda_serial.py 用 "=== Frame" 作为新帧标记
        Serial.print(F("=== Frame #"));
        Serial.print(sensors.getFrameCount());
        Serial.println(F(" ==="));

        // 每行格式必须是 "Sxx: 数值"，xx 两位补零，6 位小数
        for (uint8_t i = 0; i < MultiSensorParser::SENSOR_COUNT; i++)
        {
            Serial.print(F("S"));
            if (i + 1 < 10) Serial.print('0');
            Serial.print(i + 1);
            Serial.print(F(": "));
            Serial.println(values[i], 6);
        }
    }
}
