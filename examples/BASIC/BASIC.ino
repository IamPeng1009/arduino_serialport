#include "MultiSensorParser.h"
#include "Arduino.h"

MultiSensorParser sensors;

void setup()
{
    sensors.begin(Serial, 1000000);
}

void loop()
{
    sensors.update();

    float values[MultiSensorParser::SENSOR_COUNT];
    if (sensors.readValues(values))
    {
        Serial.print(F("Frame #"));
        Serial.println(sensors.getFrameCount());

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
